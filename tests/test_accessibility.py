from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QSlider, QSpinBox


def _interactive_children(dialog):
    widgets = []
    for widget_type in (QAbstractButton, QComboBox, QSpinBox, QLineEdit, QSlider):
        widgets.extend(dialog.findChildren(widget_type))
    return widgets


def test_capture_menu_supports_keyboard_activation(qapp):
    from capture_menu import CaptureMenu

    menu = CaptureMenu(clipboard_watching=False)
    triggered = []
    menu.capture_region.connect(lambda: triggered.append("region"))

    menu.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.NoModifier))
    assert menu.activeAction() == menu._selectable_actions()[0]

    region_action = next(
        action for action in menu._selectable_actions()
        if "Region" in action.text()
        and "Freehand" not in action.text()
        and "Last" not in action.text()
        and "OCR" not in action.text()
    )
    menu.setActiveAction(region_action)
    menu.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))

    assert triggered == ["region"]


def test_capture_menu_has_accessible_names(qapp):
    from capture_menu import CaptureMenu

    menu = CaptureMenu(clipboard_watching=True)

    assert menu.accessibleName() == "SwiftShot capture menu"
    assert menu._timer_cb.accessibleName() == "Enable timed capture"
    assert menu._timer_spin.accessibleName() == "Timed capture countdown seconds"
    for action in menu._selectable_actions():
        assert action.toolTip()


def test_settings_controls_have_accessible_names(qapp):
    from settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    unnamed = [
        widget.__class__.__name__
        for widget in _interactive_children(dialog)
        if not widget.accessibleName()
    ]

    assert dialog.accessibleName() == "SwiftShot preferences"
    assert dialog.tabs.accessibleName() == "Preferences sections"
    assert unnamed == []


def test_settings_filename_preview_updates(qapp):
    from settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    dialog.filename_pattern.setText("{app}_{w}x{h}_{counter}")

    assert dialog.filename_preview.text() == "notepad_1920x1080_001.png"

    dialog.file_format.setCurrentText("webp")
    assert dialog.filename_preview.text() == "notepad_1920x1080_001.webp"


def test_hotkey_recorder_keyboard_start_updates_accessible_state(qapp):
    from settings_dialog import HotkeyRecorderWidget

    widget = HotkeyRecorderWidget("Print")
    widget.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))

    assert widget.text() == "Press keys..."
    assert "Recording shortcut" in widget.accessibleDescription()
