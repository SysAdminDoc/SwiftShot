from PyQt5.QtGui import QColor, QPixmap


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
    from config import config
    import capture_history

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
