import sys
from pathlib import Path

from PyQt5.QtGui import QColor, QPixmap


def _load_capture_history(fresh_config, tmp_path):
    cfg = fresh_config.config
    cfg.CAPTURE_HISTORY_ENABLED = True
    cfg.CAPTURE_HISTORY_DIR = str(tmp_path)
    cfg.CAPTURE_HISTORY_MAX = 10
    sys.modules.pop("capture_history", None)
    import capture_history
    return capture_history


def test_save_to_history_indexes_sqlite_and_dedupes(fresh_config, qapp, tmp_path):
    capture_history = _load_capture_history(fresh_config, tmp_path)

    pixmap = QPixmap(24, 16)
    pixmap.fill(QColor(12, 34, 56))

    first = capture_history.save_to_history(pixmap)
    second = capture_history.save_to_history(pixmap)
    capture_history.save_to_history(pixmap, ocr_text="invoice total due")
    entries = capture_history._history_entries(str(tmp_path))

    assert first == second
    assert Path(tmp_path, "history.sqlite3").exists()
    assert len(entries) == 1
    assert entries[0]["width"] == 24
    assert entries[0]["height"] == 16
    assert entries[0]["sha256"]
    assert entries[0]["thumbnail_blob"]

    date_prefix = entries[0]["created_at"][:10]
    assert capture_history._history_entries(str(tmp_path), date_prefix)
    assert capture_history._history_entries(str(tmp_path), "invoice")
    assert capture_history._history_entries(str(tmp_path), "2999-01-01") == []


def test_save_to_history_prunes_sqlite_and_files(fresh_config, qapp, tmp_path):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    capture_history.config.CAPTURE_HISTORY_MAX = 1

    first = QPixmap(20, 20)
    first.fill(QColor("red"))
    first_path = capture_history.save_to_history(first)

    second = QPixmap(20, 20)
    second.fill(QColor("blue"))
    second_path = capture_history.save_to_history(second)

    entries = capture_history._history_entries(str(tmp_path))

    assert len(entries) == 1
    assert entries[0]["path"] == second_path
    assert not Path(first_path).exists()
