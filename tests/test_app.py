from PyQt5.QtGui import QColor, QPixmap


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
