from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QColor, QKeyEvent, QPixmap
from PyQt5.QtTest import QTest
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
    assert "QCheckBox::indicator" not in menu.styleSheet()
    for action in menu._selectable_actions():
        assert action.toolTip()


def test_capture_menu_timer_rolls_back_when_config_save_fails(qapp, monkeypatch):
    import capture_menu

    menu = capture_menu.CaptureMenu(clipboard_watching=False)
    previous = capture_menu.config.CAPTURE_TIMER_ENABLED
    warnings = []
    monkeypatch.setattr(capture_menu.config, "save", lambda: False)
    monkeypatch.setattr(
        capture_menu.QMessageBox,
        "warning",
        staticmethod(lambda *args: warnings.append(args)),
    )

    menu._timer_cb.setChecked(not previous)

    assert menu._timer_enabled == previous
    assert menu._timer_cb.isChecked() == previous
    assert capture_menu.config.CAPTURE_TIMER_ENABLED == previous
    assert warnings and warnings[0][1] == "Timer Setting Unchanged"


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
    assert dialog.theme.findData("light") >= 0
    assert dialog.after_capture_list.accessibleName() == "Post-capture workflow actions"
    assert dialog.beautify_preset.findData("presentation") >= 0
    assert dialog.history_auto_ocr.accessibleName() == "Auto-OCR captures for searchable history"
    assert unnamed == []


def test_settings_duplicate_hotkey_check_covers_color_picker(qapp, monkeypatch):
    """The color-picker hotkey must be part of the duplicate-shortcut guard,
    or it could silently collide with another capture hotkey."""
    from settings_dialog import SettingsDialog, QMessageBox

    dialog = SettingsDialog()
    dialog.hk_region.set_combo("Ctrl+Shift+K")
    dialog.hk_color_picker.set_combo("Ctrl+Shift+K")   # deliberate collision

    warned = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warned.append(a[2] if len(a) > 2 else ""))
    accepted = []
    monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))
    dialog._apply_and_close()

    assert warned and "Ctrl+Shift+K" in warned[0]      # conflict was reported
    assert not accepted                                # dialog did not apply


def test_settings_after_capture_workflow_ordering(qapp):
    from PyQt5.QtCore import Qt
    from settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    save_items = dialog.after_capture_list.findItems("Save to file", Qt.MatchExactly)
    assert save_items

    save_item = save_items[0]
    save_item.setCheckState(Qt.Checked)
    dialog.after_capture_list.setCurrentItem(save_item)
    dialog._move_workflow_item(-1)

    assert dialog._selected_after_capture_actions()[:2] == ["save", "editor"]


def test_settings_filename_preview_updates(qapp):
    from settings_dialog import SettingsDialog

    dialog = SettingsDialog()
    dialog.filename_pattern.setText("{app}_{w}x{h}_{counter}")

    assert dialog.filename_preview.text() == "notepad_1920x1080_001.png"

    dialog.file_format.setCurrentText("webp")
    assert dialog.filename_preview.text() == "notepad_1920x1080_001.webp"


def test_editor_primary_controls_have_accessible_names(qapp):
    import editor

    ed = editor.ImageEditor()
    try:
        assert ed.accessibleName() == "SwiftShot image editor"
        assert ed.canvas.accessibleName() == "Image canvas"
        assert ed.canvas.accessibleDescription()
        lp = ed.layer_panel
        assert lp.layer_list.accessibleName() == "Layers"
        assert lp.opacity_slider.accessibleName() == "Layer opacity"
        assert lp.blend_combo.accessibleName() == "Layer blend mode"
        assert lp.vis_btn.accessibleName() == "Toggle layer visibility"
        assert lp.lock_btn.accessibleName() == "Lock layer"
        # Every toolbar tool button carries an accessible name.
        named = [b for b in ed._tool_buttons.values() if b.accessibleName()]
        assert len(named) == len(ed._tool_buttons)
    finally:
        ed.close()


def test_editor_accessibility_release_gate_covers_native_controls(qapp):
    """Every public editor control must keep a native UIA role/action, name,
    keyboard focus, and a minimum pointer target."""
    import editor
    from accessibility import MIN_TARGET_SIZE

    ed = editor.ImageEditor()
    try:
        controls = ed._accessible_controls
        assert len(controls) > 100
        assert all(widget.property("swiftshotAccessibleControl") for widget in controls)
        assert all(widget.accessibleName().strip() for widget in controls)
        assert all(widget.focusPolicy() != Qt.NoFocus for widget in controls)
        buttons = [widget for widget in controls if isinstance(widget, QAbstractButton)]
        assert buttons
        assert all(button.minimumWidth() >= MIN_TARGET_SIZE for button in buttons)
        assert all(button.minimumHeight() >= MIN_TARGET_SIZE for button in buttons)
        assert isinstance(ed._color_swatch, QAbstractButton)
        assert ed._color_swatch.accessibleDescription()
    finally:
        ed.close()


def test_editor_layer_view_is_structured_canvas_equivalent(qapp):
    import editor

    ed = editor.ImageEditor()
    try:
        layer = editor.Layer("Private notes", 20, 10)
        layer.visible = False
        layer.locked = True
        layer.opacity = 128
        ed.layers = [layer]
        ed.active_layer_index = 0
        ed.layer_panel.refresh()

        item = ed.layer_panel.layer_list.item(0)
        description = item.data(Qt.AccessibleDescriptionRole)
        assert "Private notes, layer" in description
        assert "hidden" in description
        assert "locked" in description
        assert "50 percent opacity" in description
        assert "Structured view of canvas layers" in ed.layer_panel.layer_list.accessibleDescription()
    finally:
        ed.close()


def test_color_swatch_keyboard_swap(qapp):
    from editor import ColorSwatchWidget

    swatch = ColorSwatchWidget()
    swatch.set_fg(QColor("red"))
    swatch.set_bg(QColor("blue"))
    swatch.show()
    swatch.setFocus()
    QTest.keyClick(swatch, Qt.Key_X)

    assert swatch.fg() == QColor("blue")
    assert swatch.bg() == QColor("red")
    assert swatch.focusPolicy() == Qt.StrongFocus


def test_pin_window_exposes_close_action_and_keyboard_controls(qapp, fresh_config):
    from accessibility import MIN_TARGET_SIZE
    from pin_window import PinWindow

    pixmap = QPixmap(60, 40)
    pixmap.fill(QColor("red"))
    pin = PinWindow(pixmap)
    try:
        assert pin.accessibleName() == "Pinned screenshot"
        assert pin.focusPolicy() == Qt.StrongFocus
        assert pin._close_button.accessibleName() == "Close pinned screenshot"
        assert pin._close_rect().width() >= MIN_TARGET_SIZE
        assert pin._close_rect().height() >= MIN_TARGET_SIZE

        old_scale = pin._scale
        pin.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Plus, Qt.NoModifier))
        assert pin._scale > old_scale
        old_pos = pin.pos()
        pin.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.ShiftModifier))
        assert pin.x() == old_pos.x() + 10
    finally:
        pin.close()


def test_countdown_exposes_non_activating_cancel_button(qapp):
    from accessibility import MIN_TARGET_SIZE
    from countdown_overlay import CountdownOverlay

    overlay = CountdownOverlay(5000)
    cancelled = []
    overlay.cancelled.connect(lambda: cancelled.append(True))

    assert overlay.testAttribute(Qt.WA_ShowWithoutActivating)
    assert overlay.focusPolicy() == Qt.NoFocus
    assert overlay.cancel_button.accessibleName() == "Cancel timed capture"
    assert overlay.cancel_button.width() >= MIN_TARGET_SIZE
    assert overlay.cancel_button.height() >= MIN_TARGET_SIZE
    overlay.cancel_button.click()
    assert cancelled == [True]


def test_region_selector_can_complete_capture_by_keyboard(qapp, monkeypatch):
    import overlay as overlay_module

    monkeypatch.setattr(overlay_module, "virtual_geometry",
                        lambda: __import__("PyQt5.QtCore", fromlist=["QRect"]).QRect(0, 0, 100, 100))
    screenshot = QPixmap(100, 100)
    screenshot.fill(QColor("black"))
    selector = overlay_module.RegionSelector(screenshot)
    selected = []
    selector.region_selected.connect(selected.append)
    selector.current_pos = __import__("PyQt5.QtCore", fromlist=["QPoint"]).QPoint(10, 10)

    QTest.keyClick(selector, Qt.Key_Return)
    QTest.keyClick(selector, Qt.Key_Right, Qt.ShiftModifier)
    QTest.keyClick(selector, Qt.Key_Down, Qt.ShiftModifier)
    QTest.keyClick(selector, Qt.Key_Return)
    QTest.qWait(75)

    assert selected
    # QRect includes both keyboard-selected endpoints.
    assert selected[0].width() == 11
    assert selected[0].height() == 11


def test_hotkey_recorder_keyboard_start_updates_accessible_state(qapp):
    from settings_dialog import HotkeyRecorderWidget

    widget = HotkeyRecorderWidget("Print")
    widget.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))

    assert widget.text() == "Press keys..."
    assert "Recording shortcut" in widget.accessibleDescription()


def test_hotkey_recorder_rejects_unmappable_key(qapp):
    """A key the global hook can't bind (e.g. F13) must not be saved — it would
    show a combo that silently never fires."""
    from settings_dialog import HotkeyRecorderWidget

    widget = HotkeyRecorderWidget("Print")
    widget._begin_recording()
    widget.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_F13, Qt.NoModifier))

    assert widget._combo == "Print"          # unchanged, not "F13"
    assert not widget._recording
