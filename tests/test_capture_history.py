import sys
import json
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


def test_startup_quick_check_is_cached_after_success(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor("navy"))
    capture_history.save_to_history(pixmap)
    calls = []
    real_check = capture_history._run_quick_check

    def counted_check(path):
        calls.append(path)
        return real_check(path)

    monkeypatch.setattr(capture_history, "_run_quick_check", counted_check)
    first = capture_history.ensure_history_health(str(tmp_path), force=True)
    second = capture_history.ensure_history_health(str(tmp_path))

    assert first["status"] == "healthy"
    assert first["quick_check"] == "ok"
    assert second == first
    assert calls == [str(tmp_path / "history.sqlite3")]


def test_corrupt_database_is_quarantined_and_rebuilt_from_images(
        fresh_config, qapp, tmp_path):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    pixmap = QPixmap(18, 12)
    pixmap.fill(QColor("purple"))
    capture_path = Path(capture_history.save_to_history(pixmap))
    unreadable_image = tmp_path / "keep-even-if-unreadable.png"
    unreadable_image.write_bytes(b"not a PNG")
    database = tmp_path / "history.sqlite3"
    corrupt_bytes = b"corrupt history database with operator evidence"
    database.write_bytes(corrupt_bytes)
    sidecar = tmp_path / "history.sqlite3-wal"
    sidecar.write_bytes(b"corrupt sidecar")

    result = capture_history.ensure_history_health(str(tmp_path), force=True)

    assert result["status"] == "recovered"
    assert result["quick_check"] == "failed"
    assert result["recovered_file_count"] == 1
    assert capture_path.exists()
    assert unreadable_image.exists()
    quarantine = Path(result["quarantine_path"])
    assert (quarantine / "history.sqlite3").read_bytes() == corrupt_bytes
    assert (quarantine / "history.sqlite3-wal").read_bytes() == b"corrupt sidecar"
    assert database.exists()
    entries = capture_history._history_entries(str(tmp_path))
    assert [entry["path"] for entry in entries] == [str(capture_path)]

    report = json.loads(Path(
        capture_history._health_report_path(str(tmp_path))
    ).read_text(encoding="utf-8"))
    assert report == {
        "schema_version": 1,
        "status": "recovered",
        "checked_at": result["checked_at"],
        "sqlite_version": capture_history.sqlite3.sqlite_version,
        "quick_check": "failed",
        "quarantined_database": True,
        "recovered_file_count": 1,
    }


def test_timed_out_quick_check_preserves_database_without_rebuild(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor("orange"))
    capture_history.save_to_history(pixmap)
    database = tmp_path / "history.sqlite3"
    before = database.read_bytes()
    monkeypatch.setattr(
        capture_history,
        "_run_quick_check",
        lambda _path: (_ for _ in ()).throw(capture_history._HistoryCheckTimeout()),
    )

    result = capture_history.ensure_history_health(str(tmp_path), force=True)

    assert result["status"] == "check_timeout"
    assert database.read_bytes() == before
    assert not (tmp_path / "DatabaseQuarantine").exists()


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


def test_history_write_failure_does_not_create_row_or_partial_file(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    import utils

    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor("yellow"))
    real_replace = utils.os.replace

    def fail_png_replace(source, destination):
        if str(destination).endswith(".png"):
            raise OSError("injected replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(utils.os, "replace", fail_png_replace)

    assert capture_history.save_to_history(pixmap) is None
    assert capture_history._history_entries(str(tmp_path)) == []
    assert list(tmp_path.glob("*.png")) == []
    assert list(tmp_path.glob(".*.tmp")) == []


def test_history_index_failure_removes_published_file(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor("cyan"))

    def fail_thumbnail(_pixmap):
        raise OSError("injected database payload failure")

    monkeypatch.setattr(capture_history, "_thumbnail_blob", fail_thumbnail)

    assert capture_history.save_to_history(pixmap) is None
    assert capture_history._history_entries(str(tmp_path)) == []
    assert list(tmp_path.glob("*.png")) == []


def _indexed_paths(capture_history, history_dir):
    with capture_history._db(str(history_dir)) as conn:
        return {
            row["path"] for row in conn.execute("SELECT path FROM captures")
        }


def _seen_paths(capture_history, history_dir):
    with capture_history._db(str(history_dir)) as conn:
        return {
            row["path"] for row in conn.execute("SELECT path FROM seen_files")
        }


class _HistoryDialogStub:
    def __init__(self):
        self.reloads = 0

    def _load_history(self):
        self.reloads += 1


def test_single_delete_failure_keeps_file_row_and_seen_marker(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor("red"))
    filepath = capture_history.save_to_history(pixmap)
    with capture_history._db(str(tmp_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO seen_files (path, mtime) VALUES (?, ?)",
            (filepath, Path(filepath).stat().st_mtime),
        )

    warnings = []
    monkeypatch.setattr(
        capture_history.QMessageBox, "question",
        staticmethod(lambda *args: capture_history.QMessageBox.Yes),
    )
    monkeypatch.setattr(
        capture_history.QMessageBox, "warning",
        staticmethod(lambda *args: warnings.append(args)),
    )
    monkeypatch.setattr(
        capture_history, "_remove_history_file",
        lambda path: (False, "file is locked"),
    )
    dialog = _HistoryDialogStub()

    capture_history.CaptureHistoryDialog._on_delete(dialog, filepath)

    assert Path(filepath).exists()
    assert filepath in _indexed_paths(capture_history, tmp_path)
    assert filepath in _seen_paths(capture_history, tmp_path)
    assert dialog.reloads == 0
    assert warnings and "remains in capture history" in warnings[0][2]
    assert "file is locked" in warnings[0][2]


def test_single_delete_removes_file_row_and_seen_marker(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor("green"))
    filepath = capture_history.save_to_history(pixmap)
    with capture_history._db(str(tmp_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO seen_files (path, mtime) VALUES (?, ?)",
            (filepath, Path(filepath).stat().st_mtime),
        )
    monkeypatch.setattr(
        capture_history.QMessageBox, "question",
        staticmethod(lambda *args: capture_history.QMessageBox.Yes),
    )
    dialog = _HistoryDialogStub()

    capture_history.CaptureHistoryDialog._on_delete(dialog, filepath)

    assert not Path(filepath).exists()
    assert filepath not in _indexed_paths(capture_history, tmp_path)
    assert filepath not in _seen_paths(capture_history, tmp_path)
    assert dialog.reloads == 1


def test_clear_history_reports_partial_failure_and_keeps_failed_row(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    first = QPixmap(20, 20); first.fill(QColor("red"))
    second = QPixmap(20, 20); second.fill(QColor("blue"))
    failed_path = capture_history.save_to_history(first)
    removed_path = capture_history.save_to_history(second)
    real_remove = capture_history.os.remove

    def remove_with_locked_file(path):
        if path == failed_path:
            raise PermissionError("locked by another process")
        return real_remove(path)

    warnings = []
    monkeypatch.setattr(capture_history.os, "remove", remove_with_locked_file)
    monkeypatch.setattr(
        capture_history.QMessageBox, "question",
        staticmethod(lambda *args: capture_history.QMessageBox.Yes),
    )
    monkeypatch.setattr(
        capture_history.QMessageBox, "warning",
        staticmethod(lambda *args: warnings.append(args)),
    )
    dialog = _HistoryDialogStub()

    capture_history.CaptureHistoryDialog._clear_history(dialog)

    assert Path(failed_path).exists()
    assert not Path(removed_path).exists()
    assert _indexed_paths(capture_history, tmp_path) == {failed_path}
    assert dialog.reloads == 1
    assert warnings
    assert "Deleted 1 of 2" in warnings[0][2]
    assert Path(failed_path).name in warnings[0][2]
    assert "locked by another process" in warnings[0][2]


def test_retention_failure_keeps_old_reference_and_new_capture(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    capture_history.config.CAPTURE_HISTORY_MAX = 1
    first = QPixmap(20, 20); first.fill(QColor("red"))
    second = QPixmap(20, 20); second.fill(QColor("blue"))
    first_path = capture_history.save_to_history(first)
    real_remove = capture_history._remove_history_file

    def fail_first(path):
        if path == first_path:
            return False, "file is locked"
        return real_remove(path)

    monkeypatch.setattr(capture_history, "_remove_history_file", fail_first)
    second_path = capture_history.save_to_history(second)

    assert second_path and Path(second_path).exists()
    assert Path(first_path).exists()
    assert _indexed_paths(capture_history, tmp_path) == {first_path, second_path}


def test_delete_missing_file_still_purges_stale_row(
        fresh_config, qapp, tmp_path, monkeypatch):
    capture_history = _load_capture_history(fresh_config, tmp_path)
    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor("magenta"))
    filepath = capture_history.save_to_history(pixmap)
    Path(filepath).unlink()
    monkeypatch.setattr(
        capture_history.QMessageBox, "question",
        staticmethod(lambda *args: capture_history.QMessageBox.Yes),
    )
    dialog = _HistoryDialogStub()

    capture_history.CaptureHistoryDialog._on_delete(dialog, filepath)

    assert filepath not in _indexed_paths(capture_history, tmp_path)
    assert dialog.reloads == 1
