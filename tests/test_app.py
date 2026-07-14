from PyQt5.QtGui import QColor, QPixmap


class _TrayIcon:
    def __init__(self):
        self.messages = []

    def showMessage(self, *args):
        self.messages.append(args)


class _CloseableEditor:
    def __init__(self, dirty=False, closes=True):
        self._dirty = dirty
        self.closes = closes
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        return self.closes


def _exit_controller(qapp, editors):
    from app import SwiftShotApp

    controller = SwiftShotApp.__new__(SwiftShotApp)
    controller.app = qapp
    controller.editors = editors
    controller._hotkey_listener = None
    controller._update_checker = None
    controller._ocr_workers = []
    controller._pin_windows = []
    controller.tray_icon = None
    controller._capture_generation = 0
    controller._countdown = None
    controller._overlay = None
    controller._window_picker = None
    controller._scrolling_dialog = None
    controller._stop_clipboard_watcher = lambda: None
    return controller


def test_exit_app_returns_false_when_editor_cancels(qapp, monkeypatch):
    import app as app_module

    editor = _CloseableEditor(closes=False)
    controller = _exit_controller(qapp, [editor])
    quit_calls = []
    monkeypatch.setattr(app_module.QApplication, "quit", lambda: quit_calls.append(True))

    assert controller.exit_app() is False
    assert editor.close_calls == 1
    assert quit_calls == []


def test_unattended_exit_refuses_dirty_editor_without_prompt(qapp, monkeypatch):
    import app as app_module

    editor = _CloseableEditor(dirty=True)
    controller = _exit_controller(qapp, [editor])
    quit_calls = []
    monkeypatch.setattr(app_module.QApplication, "quit", lambda: quit_calls.append(True))

    assert controller.exit_app(allow_prompts=False) is False
    assert editor.close_calls == 0
    assert quit_calls == []


def test_unattended_exit_closes_clean_session(qapp, monkeypatch):
    import app as app_module
    from config import config

    editor = _CloseableEditor(dirty=False)
    controller = _exit_controller(qapp, [editor])
    quit_calls = []
    monkeypatch.setattr(app_module.QApplication, "quit", lambda: quit_calls.append(True))
    monkeypatch.setattr(config, "save", lambda: None)

    assert controller.exit_app(allow_prompts=False) is True
    assert editor.close_calls == 1
    assert quit_calls == [True]


def test_exit_refuses_to_destroy_active_ocr_worker(qapp, monkeypatch):
    import app as app_module

    class RunningWorker:
        @staticmethod
        def isRunning():
            return True

    editor = _CloseableEditor(dirty=False)
    controller = _exit_controller(qapp, [editor])
    controller._ocr_workers = [RunningWorker()]
    messages = []
    quit_calls = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda _parent, title, message: messages.append((title, message)),
    )
    monkeypatch.setattr(
        app_module.QApplication, "quit", lambda: quit_calls.append(True))

    assert controller.exit_app() is False
    assert editor.close_calls == 0
    assert quit_calls == []
    assert messages and messages[0][0] == "Text Recognition In Progress"


def test_unattended_exit_defers_active_ocr_without_prompt(qapp, monkeypatch):
    import app as app_module

    class RunningWorker:
        @staticmethod
        def isRunning():
            return True

    controller = _exit_controller(qapp, [])
    controller._ocr_workers = [RunningWorker()]
    prompt_calls = []
    monkeypatch.setattr(
        app_module.QMessageBox,
        "information",
        lambda *_args: prompt_calls.append(True),
    )

    assert controller.exit_app(allow_prompts=False) is False
    assert prompt_calls == []


def test_handle_capture_runs_workflow_actions_in_order(qapp, monkeypatch):
    from app import SwiftShotApp
    from config import config

    monkeypatch.setattr(config, "CAPTURE_HISTORY_ENABLED", False)
    monkeypatch.setattr(config, "AFTER_CAPTURE_ACTIONS", ["save", "clipboard", "editor"])
    monkeypatch.setattr(config, "AFTER_CAPTURE_ACTION", "save")

    controller = SwiftShotApp(qapp)
    called = []
    monkeypatch.setattr(controller, "_save_directly", lambda pixmap: called.append("save"))
    monkeypatch.setattr(controller, "_copy_to_clipboard", lambda pixmap: called.append("clipboard"))
    monkeypatch.setattr(controller, "_open_editor", lambda pixmap: called.append("editor"))

    pixmap = QPixmap(2, 2)
    pixmap.fill(QColor(10, 20, 30))
    controller._handle_capture(pixmap)

    assert called == ["save", "clipboard", "editor"]


def test_handle_capture_applies_beautification_before_workflow(qapp, monkeypatch):
    from app import SwiftShotApp
    from config import config

    monkeypatch.setattr(config, "CAPTURE_HISTORY_ENABLED", False)
    monkeypatch.setattr(config, "AFTER_CAPTURE_ACTIONS", ["editor"])
    monkeypatch.setattr(config, "AFTER_CAPTURE_ACTION", "editor")
    monkeypatch.setattr(config, "BEAUTIFY_PRESET", "presentation")

    controller = SwiftShotApp(qapp)
    sizes = []
    monkeypatch.setattr(
        controller,
        "_open_editor",
        lambda pixmap: sizes.append((pixmap.width(), pixmap.height())),
    )

    pixmap = QPixmap(20, 10)
    pixmap.fill(QColor(10, 20, 30))
    controller._handle_capture(pixmap)

    assert sizes[0][0] > pixmap.width()
    assert sizes[0][1] > pixmap.height()


def test_open_editor_rejects_unsafe_clipboard_dimensions_before_import(
        qapp, monkeypatch):
    import app as app_module
    from app import SwiftShotApp

    controller = SwiftShotApp(qapp)
    notices = []
    monkeypatch.setattr(app_module, "MAX_IMAGE_PIXELS", 1)
    monkeypatch.setattr(
        controller,
        "_notify",
        lambda title, message, **kwargs: notices.append((title, message, kwargs)),
    )
    pixmap = QPixmap(2, 2)
    pixmap.fill(QColor("red"))

    assert controller._open_editor(pixmap) is False
    assert notices[0][0] == "Image could not be opened"
    assert notices[0][2]["required"] is True


def test_clipboard_copy_failure_is_visible(qapp, monkeypatch):
    import app as app_module
    from app import SwiftShotApp

    class _FailingClipboard:
        @staticmethod
        def setPixmap(_pixmap):
            raise RuntimeError("clipboard busy")

    controller = SwiftShotApp(qapp)
    notices = []
    monkeypatch.setattr(
        app_module.QApplication, "clipboard", lambda: _FailingClipboard())
    monkeypatch.setattr(
        controller,
        "_notify",
        lambda title, message, **kwargs: notices.append((title, message, kwargs)),
    )
    pixmap = QPixmap(2, 2)
    pixmap.fill(QColor("blue"))

    controller._copy_to_clipboard(pixmap)

    assert notices[0][0] == "Screenshot not copied"
    assert notices[0][2]["required"] is True


def test_saved_capture_is_not_misreported_when_path_copy_fails(
        qapp, monkeypatch, tmp_path):
    import app as app_module
    import utils
    from app import SwiftShotApp
    from config import config

    class _FailingClipboard:
        @staticmethod
        def setText(_text):
            raise RuntimeError("clipboard busy")

    destination = tmp_path / "capture.png"
    controller = SwiftShotApp(qapp)
    notices = []
    monkeypatch.setattr(config, "COPY_PATH_TO_CLIPBOARD", True)
    monkeypatch.setattr(config, "get_filename", lambda **_kwargs: str(destination))
    monkeypatch.setattr(utils, "save_pixmap", lambda *_args: True)
    monkeypatch.setattr(
        app_module.QApplication, "clipboard", lambda: _FailingClipboard())
    monkeypatch.setattr(
        controller,
        "_notify",
        lambda title, message, **kwargs: notices.append((title, message, kwargs)),
    )
    pixmap = QPixmap(2, 2)
    pixmap.fill(QColor("green"))

    controller._save_directly(pixmap)

    assert notices[0][0] == "Screenshot saved; path not copied"
    assert "Saved to" in notices[0][1]
    assert notices[0][2]["required"] is True


def test_ocr_worker_emits_ocr_file_result(qapp, monkeypatch):
    """OCR now runs off the GUI thread; the worker returns ocr_file's text."""
    import ocr
    from app import _OcrWorker

    monkeypatch.setattr(ocr, "ocr_file", lambda path: "searchable text")
    worker = _OcrWorker("does-not-matter.png", cleanup=False)
    results = []
    worker.done.connect(results.append)
    worker.run()   # execute synchronously on this thread

    assert results == ["searchable text"]


def test_update_history_ocr_writes_row(qapp, tmp_path, monkeypatch):
    import capture_history
    config = capture_history.config

    monkeypatch.setattr(config, "CAPTURE_HISTORY_ENABLED", True)
    monkeypatch.setattr(config, "CAPTURE_HISTORY_DIR", str(tmp_path))
    monkeypatch.setattr(config, "CAPTURE_HISTORY_MAX", 50)

    px = QPixmap(4, 4)
    px.fill(QColor(1, 2, 3))
    path = capture_history.save_to_history(px, "")
    assert path

    capture_history.update_history_ocr(str(tmp_path), path, "hello world")
    entries = capture_history._history_entries(str(tmp_path))
    assert any(e["ocr_text"] == "hello world" for e in entries)


def test_new_delayed_capture_invalidates_older_callback(qapp, monkeypatch):
    import app as app_module
    from app import SwiftShotApp
    from config import config

    controller = SwiftShotApp(qapp)
    callbacks = []
    fired = []
    monkeypatch.setattr(config, "CAPTURE_DELAY_MS", 0)
    monkeypatch.setattr(
        app_module.QTimer,
        "singleShot",
        lambda _delay, callback: callbacks.append(callback),
    )

    controller._capture_with_delay(lambda: fired.append("old"))
    controller._capture_with_delay(lambda: fired.append("new"))
    callbacks[0]()
    callbacks[1]()

    assert fired == ["new"]


def test_diagnostics_export_previews_privacy_categories_before_writing(
        qapp, monkeypatch):
    import app as app_module
    import diagnostics
    from app import SwiftShotApp

    controller = SwiftShotApp(qapp)
    built = []
    messages = []
    monkeypatch.setattr(
        diagnostics,
        "diagnostics_preview",
        lambda: {"included": ["Versions"], "excluded": ["Screenshots"]},
    )
    monkeypatch.setattr(
        diagnostics,
        "build_diagnostics_zip",
        lambda: built.append(True),
    )
    monkeypatch.setattr(
        app_module.QMessageBox,
        "question",
        lambda _parent, _title, message, *_args: (
            messages.append(message) or app_module.QMessageBox.Cancel
        ),
    )

    controller.export_diagnostics()

    assert built == []
    assert "Included:" in messages[0]
    assert "Never included:" in messages[0]


def test_history_rebuild_outcome_is_visible_at_startup(qapp, monkeypatch):
    import capture_history
    from app import SwiftShotApp

    controller = SwiftShotApp(qapp)
    notices = []
    monkeypatch.setattr(
        capture_history,
        "ensure_history_health",
        lambda _path: {
            "status": "recovered",
            "recovered_file_count": 3,
        },
    )
    monkeypatch.setattr(
        controller,
        "_notify",
        lambda title, message, warning=False: notices.append(
            (title, message, warning)
        ),
    )

    result = controller._check_history_health()

    assert result["status"] == "recovered"
    assert notices == [(
        "Capture history rebuilt",
        "Recovered 3 capture file(s). The damaged database was preserved in "
        "quarantine.",
        False,
    )]


def test_unrelated_notification_clears_stale_update_click(qapp, monkeypatch):
    import app as app_module
    from app import SwiftShotApp
    from config import config

    monkeypatch.setattr(config, "SHOW_NOTIFICATIONS", True)
    controller = SwiftShotApp(qapp)
    controller.tray_icon = _TrayIcon()
    opened = []
    monkeypatch.setattr(app_module.webbrowser, "open", opened.append)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)

    controller._on_update_available(
        "v9.9.9", "https://github.com/SysAdminDoc/SwiftShot/releases/tag/v9.9.9")
    controller._notify("Screenshot saved", "Saved locally")
    controller._on_tray_message_clicked()

    assert opened == []


def test_notification_action_is_one_shot_and_expires(qapp, monkeypatch):
    import app as app_module
    from app import (
        SwiftShotApp, _NotificationAction, _NotificationActionKind,
    )
    from config import config

    monkeypatch.setattr(config, "SHOW_NOTIFICATIONS", True)
    controller = SwiftShotApp(qapp)
    controller.tray_icon = _TrayIcon()
    timers = []
    monkeypatch.setattr(
        app_module.QTimer, "singleShot",
        lambda _delay, callback: timers.append(callback))
    called = []

    controller._notify(
        "Update", "Open it", action=_NotificationAction(
            _NotificationActionKind.OPEN_UPDATE,
            lambda: called.append("first")))
    controller._on_tray_message_clicked()
    controller._on_tray_message_clicked()
    assert called == ["first"]

    controller._notify(
        "Update", "Open it", action=_NotificationAction(
            _NotificationActionKind.OPEN_UPDATE,
            lambda: called.append("expired")))
    timers[-1]()
    controller._on_tray_message_clicked()
    assert called == ["first"]


def test_notification_preference_is_central_and_required_errors_remain_visible(
        qapp, monkeypatch):
    import app as app_module
    from app import SwiftShotApp
    from config import config

    monkeypatch.setattr(config, "SHOW_NOTIFICATIONS", False)
    controller = SwiftShotApp(qapp)
    controller.tray_icon = _TrayIcon()
    warnings = []
    monkeypatch.setattr(
        app_module.QMessageBox, "warning",
        lambda _parent, title, message: warnings.append((title, message)))

    assert controller._notify("Copied", "Done") is False
    assert controller.tray_icon.messages == []
    assert warnings == []

    controller._notify(
        "Capture failed", "Try again", warning=True, required=True)
    assert controller.tray_icon.messages == []
    assert warnings == [("Capture failed", "Try again")]


def test_ocr_temp_encode_failure_is_visible_and_does_not_start_worker(
        qapp, monkeypatch):
    from app import SwiftShotApp

    class _BadPixmap:
        @staticmethod
        def save(*_args):
            return False

    controller = SwiftShotApp(qapp)
    notices = []
    workers = []
    monkeypatch.setattr(
        controller, "_notify",
        lambda *args, **kwargs: notices.append((args, kwargs)))
    monkeypatch.setattr(
        controller, "_spawn_ocr_worker",
        lambda *args, **kwargs: workers.append((args, kwargs)))

    controller._do_ocr(_BadPixmap())

    assert workers == []
    assert notices[0][0][0] == "OCR could not start"
    assert notices[0][1]["required"] is True


def test_clipboard_watcher_toggle_rolls_back_when_config_cannot_save(
        qapp, monkeypatch):
    from app import SwiftShotApp
    from config import config

    controller = SwiftShotApp(qapp)
    controller._clipboard_watcher_enabled = False
    config.CLIPBOARD_WATCHER_ENABLED = False
    notices = []
    monkeypatch.setattr(config, "save", lambda: False)
    monkeypatch.setattr(
        controller, "_notify",
        lambda *args, **kwargs: notices.append((args, kwargs)),
    )

    controller._toggle_clipboard_watcher()

    assert controller._clipboard_watcher_enabled is False
    assert config.CLIPBOARD_WATCHER_ENABLED is False
    assert notices[0][1]["required"] is True


def test_hotkey_registration_failure_cleans_up_partial_listener(
        qapp, monkeypatch):
    import hotkeys
    from app import SwiftShotApp

    class _FailingListener:
        stopped = False

        def register(self, *_args):
            raise RuntimeError("shortcut conflict")

        def stop(self):
            self.stopped = True

    listener = _FailingListener()
    monkeypatch.setattr(hotkeys, "HotkeyManager", lambda: listener)
    controller = SwiftShotApp(qapp)

    assert controller._register_hotkeys() is False
    assert controller._hotkey_listener is None
    assert listener.stopped is True
