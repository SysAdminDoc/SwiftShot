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


def test_search_escapes_like_wildcards(fresh_config, qapp, tmp_path):
    """Searching '100%' must match literally, not as a LIKE wildcard."""
    capture_history = _load_capture_history(fresh_config, tmp_path)

    pixmap = QPixmap(10, 10)
    pixmap.fill(QColor("green"))
    capture_history.save_to_history(pixmap, ocr_text="CPU at 100% load")

    assert capture_history._history_entries(str(tmp_path), "100%")
    assert capture_history._history_entries(str(tmp_path), "100% load")
    # A literal '%' that appears nowhere must not act as match-anything
    assert capture_history._history_entries(str(tmp_path), "%zzz%") == []


def test_duplicate_content_file_not_rehashed_every_open(fresh_config, qapp, tmp_path):
    """A content-duplicate file (same sha256, different path) can't get a
    captures row, so it must be remembered in seen_files and not re-hashed on
    every panel open."""
    import shutil
    capture_history = _load_capture_history(fresh_config, tmp_path)

    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(9, 9, 9))
    original = capture_history.save_to_history(pixmap)
    dup = str(Path(tmp_path, "dup_copy.png"))
    shutil.copyfile(original, dup)          # identical bytes → same sha256

    calls = []
    real = capture_history._index_file
    capture_history._index_file = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    try:
        capture_history._history_entries(str(tmp_path))   # first open indexes dup
        first = len(calls)
        capture_history._history_entries(str(tmp_path))   # second open must not rehash
        capture_history._history_entries(str(tmp_path))
        assert len(calls) == first          # no further _index_file on re-open
    finally:
        capture_history._index_file = real


def test_update_history_ocr_survivor_gets_text_evicted_is_noop(fresh_config, qapp, tmp_path):
    """Async OCR keys by path: a surviving capture receives its text, and an
    update against an evicted row is a safe no-op (no crash, no wrong row)."""
    capture_history = _load_capture_history(fresh_config, tmp_path)

    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(3, 4, 5))
    survivor = capture_history.save_to_history(pixmap)

    capture_history.update_history_ocr(str(tmp_path), survivor, "receipt total")
    entries = capture_history._history_entries(str(tmp_path))
    assert entries[0]["ocr_text"] == "receipt total"

    # An update for a path that no longer has a row must not raise or corrupt.
    capture_history.update_history_ocr(str(tmp_path), str(tmp_path / "gone.png"), "x")
    still = capture_history._history_entries(str(tmp_path))
    assert len(still) == 1 and still[0]["ocr_text"] == "receipt total"


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
