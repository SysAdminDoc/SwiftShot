"""Crash-recovery journal, restore, quarantine, and startup-prompt tests."""

import io
import os
import zipfile
from pathlib import Path


def _dirty_editor(qapp, tmp_path, monkeypatch, color="blue"):
    from PyQt5.QtGui import QColor, QPixmap
    from editor import ImageEditor

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    pixmap = QPixmap(16, 12)
    pixmap.fill(QColor(color))
    editor = ImageEditor(pixmap)
    editor.layers[0].image.putpixel((0, 0), (10, 20, 30, 255))
    editor._mark_dirty()
    return editor


def _leave_journal_like_a_crash(editor):
    path = editor._recovery_journal_path
    editor._recovery_journal_path = None
    editor._set_dirty(False)
    editor.close()
    return path


def test_dirty_document_journal_is_bounded_atomic_and_source_safe(
        qapp, tmp_path, monkeypatch):
    from recovery import (
        RECOVERY_IDLE_MS, RECOVERY_MAX_INTERVAL_MS, scan_recovery_journals,
    )
    from safe_io import RECOVERY_PREVIEW_MEMBER, validate_project_archive

    editor = _dirty_editor(qapp, tmp_path, monkeypatch)
    source = tmp_path / "Original Project.swiftshot"
    source.write_bytes(b"last-good-source")
    editor.saved_path = str(source)
    try:
        assert editor._recovery_idle_timer.interval() == RECOVERY_IDLE_MS
        assert editor._recovery_max_timer.interval() == RECOVERY_MAX_INTERVAL_MS
        assert editor._recovery_idle_timer.isActive()
        assert editor._recovery_max_timer.isActive()
        assert editor._write_recovery_journal() is True

        journal = Path(editor._recovery_journal_path)
        assert journal != source
        assert journal.parent.name == "Recovery"
        assert source.read_bytes() == b"last-good-source"
        with zipfile.ZipFile(journal) as archive:
            metadata, names = validate_project_archive(archive, str(journal))
            raw_metadata = archive.read("project.json").decode("utf-8")
        assert RECOVERY_PREVIEW_MEMBER in names
        assert metadata["recovery"]["document_name"] == source.name
        assert metadata["recovery"]["saved_at"].endswith("Z")
        assert str(source.parent) not in raw_metadata

        entries, quarantined = scan_recovery_journals(
            str(tmp_path / "appdata" / "SwiftShot")
        )
        assert quarantined == []
        assert len(entries) == 1
        assert entries[0].document_name == source.name
        assert entries[0].preview_png.startswith(b"\x89PNG")
    finally:
        editor._set_dirty(False)
        editor.close()


def test_failed_journal_replace_preserves_last_good_snapshot(
        qapp, tmp_path, monkeypatch):
    import utils

    editor = _dirty_editor(qapp, tmp_path, monkeypatch)
    try:
        assert editor._write_recovery_journal() is True
        journal = Path(editor._recovery_journal_path)
        last_good = journal.read_bytes()
        editor.layers[0].image.putpixel((1, 1), (200, 100, 50, 255))
        editor._mark_dirty()
        real_replace = utils.os.replace

        def fail_journal_replace(source, destination):
            if Path(destination) == journal:
                raise OSError("injected recovery replace failure")
            return real_replace(source, destination)

        monkeypatch.setattr(utils.os, "replace", fail_journal_replace)
        assert editor._write_recovery_journal() is False
        assert journal.read_bytes() == last_good
        assert editor._dirty is True
        assert list(journal.parent.glob(f".{journal.name}.*.tmp")) == []
    finally:
        editor._set_dirty(False)
        editor.close()


def test_idle_timer_writes_changed_document_without_manual_save(
        qapp, tmp_path, monkeypatch):
    from PyQt5.QtCore import QEventLoop, QTimer

    editor = _dirty_editor(qapp, tmp_path, monkeypatch)
    try:
        editor._recovery_idle_timer.setInterval(10)
        editor._recovery_idle_timer.start()
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec_()

        assert editor._recovery_journal_path is not None
        assert os.path.isfile(editor._recovery_journal_path)
        assert editor._recovery_saved_revision == editor._recovery_revision
    finally:
        editor._set_dirty(False)
        editor.close()


def test_restore_is_unsaved_and_successful_save_removes_journal(
        qapp, tmp_path, monkeypatch):
    from editor import ImageEditor

    creator = _dirty_editor(qapp, tmp_path, monkeypatch, color="green")
    assert creator._write_recovery_journal() is True
    journal = _leave_journal_like_a_crash(creator)
    assert os.path.isfile(journal)

    restored = ImageEditor()
    try:
        assert restored.restore_recovery(journal) is True
        assert restored.saved_path is None
        assert restored.file_path is None
        assert restored._dirty is True
        assert restored._recovery_journal_path == journal
        assert "Recovered Untitled capture" in restored.windowTitle()
        assert restored.layers[0].image.getpixel((0, 0)) == (10, 20, 30, 255)

        output = tmp_path / "recovered.png"
        assert restored._save_to(str(output)) is True
        assert output.exists()
        assert restored._dirty is False
        assert not os.path.exists(journal)
    finally:
        restored._set_dirty(False)
        restored.close()


def test_confirmed_discard_removes_restored_journal(
        qapp, tmp_path, monkeypatch):
    from editor import ImageEditor, QMessageBox

    creator = _dirty_editor(qapp, tmp_path, monkeypatch)
    assert creator._write_recovery_journal() is True
    journal = _leave_journal_like_a_crash(creator)
    restored = ImageEditor()
    assert restored.restore_recovery(journal) is True
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.Discard),
    )

    assert restored.close() is True
    assert not os.path.exists(journal)


def test_corrupt_journal_is_quarantined_without_raising(tmp_path):
    from recovery import recovery_directory, scan_recovery_journals

    config_dir = tmp_path / "SwiftShot"
    directory = Path(recovery_directory(str(config_dir)))
    directory.mkdir(parents=True)
    corrupt = directory / "broken.swiftshot"
    corrupt.write_text('{"private": "raw crash content"', encoding="utf-8")

    entries, quarantined = scan_recovery_journals(str(config_dir))

    assert entries == []
    assert len(quarantined) == 1
    assert not corrupt.exists()
    quarantined_path = Path(quarantined[0])
    assert quarantined_path.parent.name == "Quarantine"
    assert quarantined_path.read_text(encoding="utf-8").startswith("{")


def test_startup_offers_each_recovery_only_once(qapp, monkeypatch):
    import recovery
    from app import SwiftShotApp
    from recovery import RecoveryEntry

    entry = RecoveryEntry(
        path="recovery.swiftshot",
        document_name="Draft.swiftshot",
        saved_at="2026-07-14T12:34:56Z",
        preview_png=b"preview",
    )
    controller = SwiftShotApp(qapp)
    offered = []
    monkeypatch.setattr(
        recovery, "scan_recovery_journals", lambda: ([entry], [])
    )
    monkeypatch.setattr(
        controller,
        "_recovery_decision",
        lambda candidate: offered.append(candidate) or "later",
    )

    controller._offer_recovery_journals()
    controller._offer_recovery_journals()

    assert offered == [entry]


def test_recovery_prompt_previews_image_name_timestamp_and_actions(qapp):
    from PIL import Image
    from app import SwiftShotApp
    from recovery import RecoveryEntry

    preview = io.BytesIO()
    Image.new("RGBA", (120, 80), (20, 60, 100, 255)).save(preview, "PNG")
    entry = RecoveryEntry(
        path="recovery.swiftshot",
        document_name="Draft.swiftshot",
        saved_at="2026-07-14T12:34:56Z",
        preview_png=preview.getvalue(),
    )
    controller = SwiftShotApp(qapp)

    box, restore_button, discard_button = controller._build_recovery_prompt(entry)
    try:
        assert "Draft.swiftshot" in box.text()
        assert "2026-07-14T12:34:56Z" in box.text()
        assert box.iconPixmap() is not None
        assert not box.iconPixmap().isNull()
        assert restore_button.text() == "Restore"
        assert discard_button.text() == "Discard"
        assert "Keep for Later" in {button.text() for button in box.buttons()}
    finally:
        box.close()
