"""
SwiftShot Settings Dialog
Tabbed interface for all application preferences.
Includes custom hotkey recorder widget for remapping keyboard shortcuts.
"""

import os
import re
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QComboBox, QCheckBox, QSpinBox, QLineEdit,
    QSlider, QColorDialog, QPushButton, QLabel, QGroupBox,
    QFileDialog, QMessageBox, QDialogButtonBox, QAbstractButton,
    QApplication, QListWidget, QListWidgetItem, QAbstractItemView
)
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtCore import Qt, pyqtSignal

from config import (
    AFTER_CAPTURE_ACTION_CHOICES,
    BEAUTIFICATION_PRESETS,
    FILENAME_TEMPLATE_HELP,
    OUTPUT_FILE_FORMAT_CHOICES,
    config,
)
from logger import log
from theme import THEME_LABELS, apply_theme, colors_for_theme, stylesheet_for_theme


WORKFLOW_ACTION_LABELS = {
    "editor": "Open in editor",
    "save": "Save to file",
    "clipboard": "Copy image to clipboard",
}


# ---------------------------------------------------------------------------
# Hotkey Recorder Widget
# ---------------------------------------------------------------------------

class HotkeyRecorderWidget(QLineEdit):
    """
    Custom widget that records keyboard shortcuts.
    Click to focus, then press the desired key combination.
    Displays combos like 'Ctrl+Shift+F5', 'Alt+Print', etc.
    """

    hotkey_changed = pyqtSignal(str)

    _VK_NAMES = {
        Qt.Key_Print: "Print", Qt.Key_SysReq: "Print",
        Qt.Key_F1: "F1", Qt.Key_F2: "F2", Qt.Key_F3: "F3", Qt.Key_F4: "F4",
        Qt.Key_F5: "F5", Qt.Key_F6: "F6", Qt.Key_F7: "F7", Qt.Key_F8: "F8",
        Qt.Key_F9: "F9", Qt.Key_F10: "F10", Qt.Key_F11: "F11", Qt.Key_F12: "F12",
        Qt.Key_Escape: "Escape", Qt.Key_Space: "Space",
        Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter",
        Qt.Key_Tab: "Tab", Qt.Key_Insert: "Insert", Qt.Key_Delete: "Delete",
        Qt.Key_Home: "Home", Qt.Key_End: "End",
        Qt.Key_PageUp: "PageUp", Qt.Key_PageDown: "PageDown",
        Qt.Key_Up: "Up", Qt.Key_Down: "Down",
        Qt.Key_Left: "Left", Qt.Key_Right: "Right",
        Qt.Key_Pause: "Pause", Qt.Key_ScrollLock: "ScrollLock",
    }

    def __init__(self, current_combo="", parent=None):
        super().__init__(parent)
        self._combo = current_combo
        self._recording = False
        self.setReadOnly(True)
        self.setPlaceholderText("Click to record shortcut...")
        self.setText(current_combo if current_combo else "(none)")
        self.setAlignment(Qt.AlignCenter)
        self.setAccessibleDescription(
            "Shortcut field. Press Enter or click to start recording a key combination."
        )
        self._update_style(False)

    def _begin_recording(self):
        self._recording = True
        self.setText("Press keys...")
        self._update_style(True)
        self.setFocus()

    def _update_style(self, recording):
        colors = colors_for_theme(config.THEME)
        if recording:
            self.setAccessibleDescription(
                "Recording shortcut. Press a key combination, Escape to cancel, or Backspace to clear."
            )
            self.setStyleSheet(
                f"QLineEdit {{ background-color: {colors['BG3']}; "
                f"color: {colors['YELLOW']}; "
                f"border: 2px solid {colors['YELLOW']}; border-radius: 4px; "
                "padding: 4px 8px; min-height: 24px; font-weight: bold; }"
            )
        else:
            self.setAccessibleDescription(
                "Shortcut field. Press Enter or click to start recording a key combination."
            )
            self.setStyleSheet(
                f"QLineEdit {{ background-color: {colors['BG2']}; "
                f"color: {colors['TEXT_PRI']}; "
                f"border: 1px solid {colors['BORDER']}; border-radius: 4px; "
                "padding: 4px 8px; min-height: 24px; }"
                f"QLineEdit:hover {{ border-color: {colors['ACCENT']}; }}"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._begin_recording()
        super().mousePressEvent(event)

    def focusOutEvent(self, event):
        if self._recording:
            self._recording = False
            self.setText(self._combo if self._combo else "(none)")
            self._update_style(False)
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self._recording:
            if event.key() == Qt.Key_Escape:
                self.clearFocus()
            elif event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
                self._begin_recording()
            return

        key = event.key()

        # Escape cancels recording
        if key == Qt.Key_Escape:
            self._recording = False
            self.setText(self._combo if self._combo else "(none)")
            self._update_style(False)
            self.clearFocus()
            return

        # Backspace/Delete clears the binding
        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            self._combo = ""
            self._recording = False
            self.setText("(none)")
            self._update_style(False)
            self.clearFocus()
            self.hotkey_changed.emit("")
            return

        # Ignore standalone modifier presses
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
                   Qt.Key_AltGr, Qt.Key_Super_L, Qt.Key_Super_R):
            return

        # Build combo string
        parts = []
        mods = event.modifiers()
        if mods & Qt.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.AltModifier:
            parts.append("Alt")
        if mods & Qt.ShiftModifier:
            parts.append("Shift")

        # Get key name
        key_name = self._VK_NAMES.get(key)
        if key_name is None:
            if Qt.Key_A <= key <= Qt.Key_Z:
                key_name = chr(key)
            elif Qt.Key_0 <= key <= Qt.Key_9:
                key_name = chr(key)
            else:
                seq = QKeySequence(key)
                key_name = seq.toString()
                if not key_name:
                    return

        parts.append(key_name)
        combo = "+".join(parts)

        self._combo = combo
        self._recording = False
        self.setText(combo)
        self._update_style(False)
        self.clearFocus()
        self.hotkey_changed.emit(combo)

    def get_combo(self):
        return self._combo

    def set_combo(self, combo):
        self._combo = combo
        self.setText(combo if combo else "(none)")
        self._update_style(False)


# ---------------------------------------------------------------------------
# Settings Dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    """Tabbed settings dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SwiftShot - Preferences")
        self.setMinimumSize(580, 560)
        self.setStyleSheet(self._stylesheet())

        layout = QVBoxLayout(self)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_general_tab(), "General")
        self.tabs.addTab(self._create_capture_tab(), "Capture")
        self.tabs.addTab(self._create_hotkeys_tab(), "Hotkeys")
        self.tabs.addTab(self._create_output_tab(), "Output")
        self.tabs.addTab(self._create_editor_tab(), "Editor")
        self.tabs.addTab(self._create_frame_tab(), "Frame")
        self.tabs.addTab(self._create_advanced_tab(), "Advanced")
        layout.addWidget(self.tabs)

        # Bottom buttons
        btn_row = QHBoxLayout()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setToolTip("Reset all settings to factory defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(reset_btn)

        import_btn = QPushButton("Import...")
        import_btn.setToolTip("Import settings from a JSON file")
        import_btn.clicked.connect(self._import_settings)
        btn_row.addWidget(import_btn)

        export_btn = QPushButton("Export...")
        export_btn.setToolTip("Export current settings to a JSON file")
        export_btn.clicked.connect(self._export_settings)
        btn_row.addWidget(export_btn)

        btn_row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._apply_and_close)
        buttons.rejected.connect(self.reject)
        btn_row.addWidget(buttons)

        layout.addLayout(btn_row)
        self._apply_accessibility()

    # --- Tab: General ---

    def _create_general_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        self.launch_startup = QCheckBox("Launch SwiftShot on Windows startup")
        self.launch_startup.setChecked(config.LAUNCH_AT_STARTUP)
        layout.addRow(self.launch_startup)

        self.check_updates = QCheckBox("Check for updates on startup")
        self.check_updates.setChecked(config.CHECK_FOR_UPDATES)
        layout.addRow(self.check_updates)

        self.show_notifications = QCheckBox("Show tray notifications")
        self.show_notifications.setChecked(config.SHOW_NOTIFICATIONS)
        layout.addRow(self.show_notifications)

        self.theme = QComboBox()
        for value, label in THEME_LABELS.items():
            self.theme.addItem(label, value)
        idx = self.theme.findData(config.THEME)
        self.theme.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow("Theme:", self.theme)

        self.play_sound = QCheckBox("Play capture sound")
        self.play_sound.setChecked(config.PLAY_CAMERA_SOUND)
        layout.addRow(self.play_sound)

        workflow_group = QGroupBox("Post-capture workflow")
        workflow_layout = QVBoxLayout(workflow_group)
        self.after_capture_list = QListWidget()
        self.after_capture_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.after_capture_list.setDefaultDropAction(Qt.MoveAction)
        self.after_capture_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.after_capture_list.setFixedHeight(96)
        self._populate_after_capture_list()
        workflow_layout.addWidget(self.after_capture_list)

        workflow_buttons = QHBoxLayout()
        up_btn = QPushButton("Move Up")
        up_btn.clicked.connect(lambda: self._move_workflow_item(-1))
        workflow_buttons.addWidget(up_btn)
        down_btn = QPushButton("Move Down")
        down_btn.clicked.connect(lambda: self._move_workflow_item(1))
        workflow_buttons.addWidget(down_btn)
        workflow_buttons.addStretch()
        workflow_layout.addLayout(workflow_buttons)
        layout.addRow(workflow_group)

        self.copy_path = QCheckBox("Copy file path to clipboard after saving")
        self.copy_path.setChecked(config.COPY_PATH_TO_CLIPBOARD)
        layout.addRow(self.copy_path)

        return w

    # --- Tab: Capture ---

    def _create_capture_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        self.capture_mouse = QCheckBox("Include mouse pointer in captures")
        self.capture_mouse.setChecked(config.CAPTURE_MOUSE_POINTER)
        layout.addRow(self.capture_mouse)

        self.capture_delay = QSpinBox()
        self.capture_delay.setRange(0, 10000)
        self.capture_delay.setSingleStep(500)
        self.capture_delay.setSuffix(" ms")
        self.capture_delay.setValue(config.CAPTURE_DELAY_MS)
        self.capture_delay.setToolTip("Delay before the capture overlay appears")
        layout.addRow("Pre-capture delay:", self.capture_delay)

        self.clipboard_watcher = QCheckBox("Enable clipboard watcher")
        self.clipboard_watcher.setChecked(config.CLIPBOARD_WATCHER_ENABLED)
        self.clipboard_watcher.setToolTip(
            "Auto-open editor when images are copied to clipboard")
        layout.addRow(self.clipboard_watcher)

        layout.addRow(QLabel(""))

        # Timed capture settings
        timer_group = QGroupBox("Timed Capture")
        tg_layout = QFormLayout(timer_group)
        colors = colors_for_theme(config.THEME)

        self.timer_enabled = QCheckBox("Enable timed capture by default")
        self.timer_enabled.setChecked(config.CAPTURE_TIMER_ENABLED)
        self.timer_enabled.setToolTip(
            "Select your region first, then a countdown gives you\n"
            "time to interact with the screen before the shot is taken.")
        tg_layout.addRow(self.timer_enabled)

        self.timer_seconds = QSpinBox()
        self.timer_seconds.setRange(1, 30)
        self.timer_seconds.setSuffix(" seconds")
        self.timer_seconds.setValue(config.CAPTURE_TIMER_SECONDS)
        self.timer_seconds.setToolTip("Countdown duration after region selection")
        tg_layout.addRow("Timer duration:", self.timer_seconds)

        tg_layout.addRow(QLabel(
            f"<i style='color:{colors['TEXT_MUT']};'>Select region/window first, then interact<br>"
            "with the screen during countdown. Screenshot<br>"
            "is taken when timer ends.</i>"
        ))

        layout.addRow(timer_group)

        return w

    # --- Tab: Hotkeys ---

    def _create_hotkeys_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        info = QLabel(
            "Click any shortcut field, then press the desired key combination.\n"
            "Press Backspace to clear a binding. Press Escape to cancel."
        )
        colors = colors_for_theme(config.THEME)
        info.setStyleSheet(f"color: {colors['TEXT_SEC']}; font-size: 9pt;")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        # Primary hotkeys
        form.addRow(QLabel("<b>Primary Capture Hotkeys</b>"))

        self.hk_region = HotkeyRecorderWidget(config.CAPTURE_REGION_HOTKEY)
        form.addRow("Capture Menu / Region:", self.hk_region)

        self.hk_window = HotkeyRecorderWidget(config.CAPTURE_WINDOW_HOTKEY)
        form.addRow("Window Capture:", self.hk_window)

        self.hk_fullscreen = HotkeyRecorderWidget(config.CAPTURE_FULLSCREEN_HOTKEY)
        form.addRow("Fullscreen / Monitor:", self.hk_fullscreen)

        self.hk_last_region = HotkeyRecorderWidget(config.CAPTURE_LAST_REGION_HOTKEY)
        form.addRow("Last Region:", self.hk_last_region)

        form.addRow(QLabel(""))
        form.addRow(QLabel("<b>Additional Hotkeys</b>"))

        self.hk_ocr = HotkeyRecorderWidget(config.CAPTURE_OCR_HOTKEY)
        form.addRow("OCR Region:", self.hk_ocr)

        self.hk_freehand = HotkeyRecorderWidget(config.CAPTURE_FREEHAND_HOTKEY)
        form.addRow("Freehand Region:", self.hk_freehand)

        self.hk_scrolling = HotkeyRecorderWidget(config.CAPTURE_SCROLLING_HOTKEY)
        form.addRow("Scrolling Capture:", self.hk_scrolling)

        form.addRow(QLabel(""))

        # Reset hotkeys button
        reset_hk_btn = QPushButton("Reset Hotkeys to Defaults")
        reset_hk_btn.setFixedWidth(220)
        reset_hk_btn.clicked.connect(self._reset_hotkeys)
        form.addRow("", reset_hk_btn)

        layout.addLayout(form)
        layout.addStretch()
        return w

    def _reset_hotkeys(self):
        self.hk_region.set_combo("Print")
        self.hk_window.set_combo("Alt+Print")
        self.hk_fullscreen.set_combo("Ctrl+Print")
        self.hk_last_region.set_combo("Shift+Print")
        self.hk_ocr.set_combo("")
        self.hk_freehand.set_combo("")
        self.hk_scrolling.set_combo("")

    # --- Tab: Output ---

    def _create_output_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        self.file_format = QComboBox()
        self.file_format.addItems(list(OUTPUT_FILE_FORMAT_CHOICES))
        idx = self.file_format.findText(config.OUTPUT_FILE_FORMAT)
        if idx >= 0:
            self.file_format.setCurrentIndex(idx)
        layout.addRow("File format:", self.file_format)

        self.jpeg_quality = QSpinBox()
        self.jpeg_quality.setRange(1, 100)
        self.jpeg_quality.setValue(config.OUTPUT_JPEG_QUALITY)
        self.jpeg_quality.setSuffix("%")
        layout.addRow("JPEG quality:", self.jpeg_quality)

        self.filename_pattern = QLineEdit(config.OUTPUT_FILENAME_PATTERN)
        self.filename_pattern.setToolTip(FILENAME_TEMPLATE_HELP)
        self.filename_pattern.textChanged.connect(self._update_filename_preview)
        layout.addRow("Filename pattern:", self.filename_pattern)

        self.filename_preview = QLabel()
        self.filename_preview.setToolTip(FILENAME_TEMPLATE_HELP)
        self.file_format.currentTextChanged.connect(self._update_filename_preview)
        layout.addRow("Preview:", self.filename_preview)
        self._update_filename_preview()

        dir_row = QHBoxLayout()
        self.output_dir = QLineEdit(config.OUTPUT_FILE_PATH or "(Desktop)")
        dir_row.addWidget(self.output_dir)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_row.addWidget(browse_btn)
        layout.addRow("Save directory:", dir_row)

        self.auto_increment = QCheckBox("Auto-increment filename if exists")
        self.auto_increment.setChecked(config.OUTPUT_FILE_INCREMENT)
        layout.addRow(self.auto_increment)

        return w

    # --- Tab: Editor ---

    def _create_editor_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        self.default_line_width = QSpinBox()
        self.default_line_width.setRange(1, 20)
        self.default_line_width.setValue(config.EDITOR_DEFAULT_LINE_WIDTH)
        layout.addRow("Default line width:", self.default_line_width)

        self.default_font_size = QSpinBox()
        self.default_font_size.setRange(6, 72)
        self.default_font_size.setValue(config.EDITOR_DEFAULT_FONT_SIZE)
        layout.addRow("Default font size:", self.default_font_size)

        self.obfuscate_factor = QSpinBox()
        self.obfuscate_factor.setRange(2, 50)
        self.obfuscate_factor.setValue(config.EDITOR_OBFUSCATE_FACTOR)
        layout.addRow("Obfuscate factor:", self.obfuscate_factor)

        self.obfuscate_mode = QComboBox()
        self.obfuscate_mode.addItems(["pixelate", "blur"])
        idx = self.obfuscate_mode.findText(config.EDITOR_OBFUSCATE_MODE)
        if idx >= 0:
            self.obfuscate_mode.setCurrentIndex(idx)
        layout.addRow("Obfuscate mode:", self.obfuscate_mode)

        self.reuse_editor = QCheckBox("Reuse existing editor window")
        self.reuse_editor.setChecked(config.EDITOR_REUSE_EDITOR)
        layout.addRow(self.reuse_editor)

        return w

    # --- Tab: Frame ---

    def _create_frame_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        self.beautify_preset = QComboBox()
        for value, preset in BEAUTIFICATION_PRESETS.items():
            self.beautify_preset.addItem(preset["label"], value)
        idx = self.beautify_preset.findData(config.BEAUTIFY_PRESET)
        self.beautify_preset.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow("Beautification preset:", self.beautify_preset)

        layout.addRow(QLabel(""))
        layout.addRow(QLabel("Border"))

        self.border_enabled = QCheckBox("Add a border to captures")
        self.border_enabled.setChecked(config.BORDER_ENABLED)
        layout.addRow(self.border_enabled)

        self.border_width = QSpinBox()
        self.border_width.setRange(0, 50)
        self.border_width.setValue(config.BORDER_WIDTH)
        layout.addRow("Border width:", self.border_width)

        border_row = QHBoxLayout()
        self._border_color = QColor(config.BORDER_COLOR)
        self.border_color_btn = QPushButton()
        self.border_color_btn.setFixedSize(28, 28)
        self._update_color_btn(self.border_color_btn, self._border_color)
        self.border_color_btn.clicked.connect(self._pick_border_color)
        border_row.addWidget(self.border_color_btn)
        border_row.addStretch()
        layout.addRow("Border color:", border_row)

        layout.addRow(QLabel(""))
        layout.addRow(QLabel("Shadow"))

        self.shadow_enabled = QCheckBox("Add a drop shadow to captures")
        self.shadow_enabled.setChecked(config.SHADOW_ENABLED)
        layout.addRow(self.shadow_enabled)

        self.shadow_radius = QSpinBox()
        self.shadow_radius.setRange(0, 50)
        self.shadow_radius.setValue(config.SHADOW_RADIUS)
        layout.addRow("Shadow radius:", self.shadow_radius)

        self.shadow_opacity = QSlider(Qt.Horizontal)
        self.shadow_opacity.setRange(0, 255)
        self.shadow_opacity.setValue(config.SHADOW_OPACITY)
        layout.addRow("Shadow opacity:", self.shadow_opacity)

        layout.addRow(QLabel(""))
        layout.addRow(QLabel("Rounded Corners"))

        self.rounded_enabled = QCheckBox("Round capture corners")
        self.rounded_enabled.setChecked(config.ROUNDED_CORNERS_ENABLED)
        layout.addRow(self.rounded_enabled)

        self.rounded_radius = QSpinBox()
        self.rounded_radius.setRange(0, 100)
        self.rounded_radius.setValue(config.ROUNDED_CORNERS_RADIUS)
        layout.addRow("Corner radius:", self.rounded_radius)

        return w

    # --- Tab: Advanced ---

    def _create_advanced_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        self.history_enabled = QCheckBox("Enable capture history")
        self.history_enabled.setChecked(config.CAPTURE_HISTORY_ENABLED)
        layout.addRow(self.history_enabled)

        self.history_auto_ocr = QCheckBox("Auto-OCR captures for searchable history")
        self.history_auto_ocr.setChecked(config.CAPTURE_HISTORY_AUTO_OCR)
        self.history_auto_ocr.setToolTip(
            "Extract text from each capture and include it in history search")
        layout.addRow(self.history_auto_ocr)

        self.history_max = QSpinBox()
        self.history_max.setRange(5, 500)
        self.history_max.setValue(config.CAPTURE_HISTORY_MAX)
        layout.addRow("Max history items:", self.history_max)

        self.pin_opacity = QSlider(Qt.Horizontal)
        self.pin_opacity.setRange(10, 100)
        self.pin_opacity.setValue(config.PIN_OPACITY)
        layout.addRow("Pin window opacity:", self.pin_opacity)

        layout.addRow(QLabel(""))

        config_label = QLabel(f"Config: {config.config_dir}")
        colors = colors_for_theme(config.THEME)
        config_label.setStyleSheet(f"color: {colors['TEXT_MUT']}; font-size: 9pt;")
        config_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow(config_label)

        log_label = QLabel(f"Log: {config.log_file}")
        log_label.setStyleSheet(f"color: {colors['TEXT_MUT']}; font-size: 9pt;")
        log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow(log_label)

        open_log_btn = QPushButton("Open Log File")
        open_log_btn.clicked.connect(self._open_log)
        layout.addRow(open_log_btn)

        return w

    # --- Helpers ---

    def _populate_after_capture_list(self):
        configured = config.get_after_capture_actions()
        ordered = configured + [
            action for action in AFTER_CAPTURE_ACTION_CHOICES
            if action not in configured
        ]
        for action in ordered:
            item = QListWidgetItem(WORKFLOW_ACTION_LABELS[action])
            item.setData(Qt.UserRole, action)
            item.setFlags(
                item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled
            )
            item.setCheckState(Qt.Checked if action in configured else Qt.Unchecked)
            self.after_capture_list.addItem(item)
        self.after_capture_list.setCurrentRow(0)

    def _move_workflow_item(self, direction):
        row = self.after_capture_list.currentRow()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= self.after_capture_list.count():
            return
        item = self.after_capture_list.takeItem(row)
        self.after_capture_list.insertItem(new_row, item)
        self.after_capture_list.setCurrentRow(new_row)

    def _selected_after_capture_actions(self):
        actions = []
        for row in range(self.after_capture_list.count()):
            item = self.after_capture_list.item(row)
            if item.checkState() == Qt.Checked:
                actions.append(item.data(Qt.UserRole))
        return actions or ["editor"]

    def _update_filename_preview(self):
        if not hasattr(self, "filename_preview"):
            return
        preview = config.preview_filename(
            pattern=self.filename_pattern.text(),
            file_format=self.file_format.currentText(),
            width=1920,
            height=1080,
            app_name="notepad",
            window_title="Release notes",
        )
        self.filename_preview.setText(preview)

    def _update_color_btn(self, btn, color):
        colors = colors_for_theme(config.THEME)
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color.name()}; "
            f"border: 2px solid {colors['BORDER']}; border-radius: 4px; }}"
            f"QPushButton:hover {{ border-color: {colors['ACCENT']}; }}"
        )

    def _pick_border_color(self):
        color = QColorDialog.getColor(
            self._border_color, self, "Border Color")
        if color.isValid():
            self._border_color = color
            self._update_color_btn(self.border_color_btn, color)

    def _browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory")
        if path:
            self.output_dir.setText(path)

    def _open_log(self):
        try:
            if os.name == 'nt':
                os.startfile(config.log_file)
            else:
                import subprocess
                subprocess.Popen(['xdg-open', config.log_file])
        except Exception:
            pass

    def _reset_defaults(self):
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Reset all settings to factory defaults?\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            config.reset_to_defaults()
            app = QApplication.instance()
            if app:
                apply_theme(app, config.THEME)
            self.accept()
            log.info("Settings reset to defaults")

    def _import_settings(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filepath:
            if config.import_settings(filepath):
                QMessageBox.information(
                    self, "Import",
                    "Settings imported successfully.\n"
                    "Please restart for all changes to take effect."
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Import Failed",
                    "Could not import settings from the selected file."
                )

    def _export_settings(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", "swiftshot-settings.json",
            "JSON Files (*.json);;All Files (*)"
        )
        if filepath:
            if config.export_settings(filepath):
                QMessageBox.information(
                    self, "Export", f"Settings exported to:\n{filepath}")
            else:
                QMessageBox.warning(
                    self, "Export Failed", "Could not export settings.")

    def _apply_and_close(self):
        # Refuse to apply if the same shortcut is bound to multiple actions
        combos = [c for c in (
            self.hk_region.get_combo(), self.hk_window.get_combo(),
            self.hk_fullscreen.get_combo(), self.hk_last_region.get_combo(),
            self.hk_ocr.get_combo(), self.hk_freehand.get_combo(),
            self.hk_scrolling.get_combo(),
        ) if c]
        duplicates = sorted({c for c in combos if combos.count(c) > 1})
        if duplicates:
            QMessageBox.warning(
                self, "Duplicate Shortcuts",
                "The same shortcut is assigned to more than one action: "
                f"{', '.join(duplicates)}.\n\n"
                "Give each action a unique shortcut, or clear one with Backspace."
            )
            self.tabs.setCurrentIndex(2)
            return

        # General
        config.LAUNCH_AT_STARTUP = self.launch_startup.isChecked()
        config.CHECK_FOR_UPDATES = self.check_updates.isChecked()
        config.SHOW_NOTIFICATIONS = self.show_notifications.isChecked()
        config.PLAY_CAMERA_SOUND = self.play_sound.isChecked()
        config.THEME = self.theme.currentData() or "dark"
        config.AFTER_CAPTURE_ACTIONS = self._selected_after_capture_actions()
        config.AFTER_CAPTURE_ACTION = config.AFTER_CAPTURE_ACTIONS[0]
        config.COPY_PATH_TO_CLIPBOARD = self.copy_path.isChecked()

        # Capture
        config.CAPTURE_MOUSE_POINTER = self.capture_mouse.isChecked()
        config.CAPTURE_DELAY_MS = self.capture_delay.value()
        config.CLIPBOARD_WATCHER_ENABLED = self.clipboard_watcher.isChecked()
        config.CAPTURE_TIMER_ENABLED = self.timer_enabled.isChecked()
        config.CAPTURE_TIMER_SECONDS = self.timer_seconds.value()

        # Hotkeys
        config.CAPTURE_REGION_HOTKEY = self.hk_region.get_combo()
        config.CAPTURE_WINDOW_HOTKEY = self.hk_window.get_combo()
        config.CAPTURE_FULLSCREEN_HOTKEY = self.hk_fullscreen.get_combo()
        config.CAPTURE_LAST_REGION_HOTKEY = self.hk_last_region.get_combo()
        config.CAPTURE_OCR_HOTKEY = self.hk_ocr.get_combo()
        config.CAPTURE_FREEHAND_HOTKEY = self.hk_freehand.get_combo()
        config.CAPTURE_SCROLLING_HOTKEY = self.hk_scrolling.get_combo()

        # Output
        config.OUTPUT_FILE_FORMAT = self.file_format.currentText()
        config.OUTPUT_JPEG_QUALITY = self.jpeg_quality.value()
        config.OUTPUT_FILENAME_PATTERN = self.filename_pattern.text()
        out_dir = self.output_dir.text()
        config.OUTPUT_FILE_PATH = "" if out_dir == "(Desktop)" else out_dir
        config.OUTPUT_FILE_INCREMENT = self.auto_increment.isChecked()

        # Editor
        config.EDITOR_DEFAULT_LINE_WIDTH = self.default_line_width.value()
        config.EDITOR_DEFAULT_FONT_SIZE = self.default_font_size.value()
        config.EDITOR_OBFUSCATE_FACTOR = self.obfuscate_factor.value()
        config.EDITOR_OBFUSCATE_MODE = self.obfuscate_mode.currentText()
        config.EDITOR_REUSE_EDITOR = self.reuse_editor.isChecked()

        # Frame
        config.BEAUTIFY_PRESET = self.beautify_preset.currentData() or "none"
        config.BORDER_ENABLED = self.border_enabled.isChecked()
        config.BORDER_WIDTH = self.border_width.value()
        config.BORDER_COLOR = self._border_color.name()
        config.SHADOW_ENABLED = self.shadow_enabled.isChecked()
        config.SHADOW_RADIUS = self.shadow_radius.value()
        config.SHADOW_OPACITY = self.shadow_opacity.value()
        config.ROUNDED_CORNERS_ENABLED = self.rounded_enabled.isChecked()
        config.ROUNDED_CORNERS_RADIUS = self.rounded_radius.value()

        # Advanced
        config.CAPTURE_HISTORY_ENABLED = self.history_enabled.isChecked()
        config.CAPTURE_HISTORY_AUTO_OCR = self.history_auto_ocr.isChecked()
        config.CAPTURE_HISTORY_MAX = self.history_max.value()
        config.PIN_OPACITY = self.pin_opacity.value()

        # Apply startup registry
        try:
            from utils import set_startup_registry
            if not set_startup_registry(config.LAUNCH_AT_STARTUP) and config.LAUNCH_AT_STARTUP:
                log.warning("Could not write the startup registry entry")
                QMessageBox.warning(
                    self, "Startup setting",
                    "SwiftShot could not register itself to launch at startup.\n"
                    "The rest of your settings were saved.")
        except Exception:
            log.warning("Startup registry update failed", exc_info=True)

        config.save()
        app = QApplication.instance()
        if app:
            apply_theme(app, config.THEME)
        self.setStyleSheet(self._stylesheet())
        log.info("Settings saved")
        self.accept()

    def _apply_accessibility(self):
        self.setAccessibleName("SwiftShot preferences")
        self.setAccessibleDescription("Tabbed dialog for configuring SwiftShot preferences.")

        self.tabs.setAccessibleName("Preferences sections")
        for i in range(self.tabs.count()):
            tab_name = self.tabs.tabText(i)
            widget = self.tabs.widget(i)
            widget.setAccessibleName(f"{tab_name} settings")
            widget.setAccessibleDescription(f"Settings in the {tab_name} section.")

        named_controls = {
            self.launch_startup: "Launch SwiftShot on Windows startup",
            self.check_updates: "Check for updates on startup",
            self.show_notifications: "Show tray notifications",
            self.theme: "Application theme",
            self.play_sound: "Play capture sound",
            self.after_capture_list: "Post-capture workflow actions",
            self.copy_path: "Copy file path to clipboard after saving",
            self.capture_mouse: "Include mouse pointer in captures",
            self.capture_delay: "Pre-capture delay in milliseconds",
            self.clipboard_watcher: "Enable clipboard watcher",
            self.timer_enabled: "Enable timed capture by default",
            self.timer_seconds: "Timed capture duration in seconds",
            self.hk_region: "Capture menu hotkey",
            self.hk_window: "Window capture hotkey",
            self.hk_fullscreen: "Fullscreen or monitor capture hotkey",
            self.hk_last_region: "Last region capture hotkey",
            self.hk_ocr: "OCR region hotkey",
            self.hk_freehand: "Freehand region hotkey",
            self.hk_scrolling: "Scrolling capture hotkey",
            self.file_format: "Output file format",
            self.jpeg_quality: "JPEG quality percentage",
            self.filename_pattern: "Output filename pattern",
            self.output_dir: "Save directory",
            self.auto_increment: "Auto-increment filename if it already exists",
            self.default_line_width: "Default editor line width",
            self.default_font_size: "Default editor font size",
            self.obfuscate_factor: "Obfuscate factor",
            self.obfuscate_mode: "Obfuscate mode",
            self.reuse_editor: "Reuse existing editor window",
            self.beautify_preset: "Beautification preset",
            self.border_enabled: "Add a border to captures",
            self.border_width: "Border width",
            self.border_color_btn: "Border color picker",
            self.shadow_enabled: "Add a drop shadow to captures",
            self.shadow_radius: "Shadow radius",
            self.shadow_opacity: "Shadow opacity",
            self.rounded_enabled: "Round capture corners",
            self.rounded_radius: "Rounded corner radius",
            self.history_enabled: "Enable capture history",
            self.history_auto_ocr: "Auto-OCR captures for searchable history",
            self.history_max: "Maximum history items",
            self.pin_opacity: "Pin window opacity",
        }
        for widget, name in named_controls.items():
            self._set_accessible(widget, name)

        self.filename_pattern.setAccessibleDescription(FILENAME_TEMPLATE_HELP)
        self.filename_preview.setAccessibleName("Filename preview")
        self.filename_preview.setAccessibleDescription(FILENAME_TEMPLATE_HELP)

        for widget in self.findChildren((
            QAbstractButton, QComboBox, QSpinBox, QLineEdit, QSlider,
        )):
            if not widget.accessibleName():
                self._set_accessible(widget, self._fallback_accessible_name(widget))
            elif not widget.accessibleDescription() and widget.toolTip():
                widget.setAccessibleDescription(self._clean_accessible_text(widget.toolTip()))

    def _set_accessible(self, widget, name, description=None):
        widget.setAccessibleName(name)
        widget.setAccessibleDescription(description or name)

    def _fallback_accessible_name(self, widget):
        if isinstance(widget, QAbstractButton) and widget.text():
            return self._clean_accessible_text(widget.text())
        if isinstance(widget, QLineEdit) and widget.placeholderText():
            return self._clean_accessible_text(widget.placeholderText())
        if widget.toolTip():
            return self._clean_accessible_text(widget.toolTip())
        return widget.__class__.__name__

    @staticmethod
    def _clean_accessible_text(text):
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(text.replace("&", "").split())

    def _stylesheet(self):
        return stylesheet_for_theme(config.THEME)
