"""
SwiftShot Settings Dialog
Tabbed interface for all application preferences.
Includes custom hotkey recorder widget for remapping keyboard shortcuts.
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QComboBox, QCheckBox, QSpinBox, QLineEdit,
    QSlider, QColorDialog, QPushButton, QLabel, QGroupBox,
    QFileDialog, QMessageBox, QDialogButtonBox
)
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtCore import Qt, pyqtSignal

from config import config
from logger import log


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
        self._update_style(False)

    def _update_style(self, recording):
        if recording:
            self.setStyleSheet(
                "QLineEdit { background-color: #45475a; color: #f9e2af; "
                "border: 2px solid #f9e2af; border-radius: 4px; "
                "padding: 4px 8px; min-height: 24px; font-weight: bold; }"
            )
        else:
            self.setStyleSheet(
                "QLineEdit { background-color: #313244; color: #cdd6f4; "
                "border: 1px solid #45475a; border-radius: 4px; "
                "padding: 4px 8px; min-height: 24px; }"
                "QLineEdit:hover { border-color: #89b4fa; }"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._recording = True
            self.setText("Press keys...")
            self._update_style(True)
            self.setFocus()
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

    # --- Tab: General ---

    def _create_general_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        self.launch_startup = QCheckBox("Launch SwiftShot on Windows startup")
        self.launch_startup.setChecked(config.LAUNCH_AT_STARTUP)
        layout.addRow(self.launch_startup)

        self.minimize_tray = QCheckBox("Minimize to system tray")
        self.minimize_tray.setChecked(config.MINIMIZE_TO_TRAY)
        layout.addRow(self.minimize_tray)

        self.check_updates = QCheckBox("Check for updates on startup")
        self.check_updates.setChecked(config.CHECK_FOR_UPDATES)
        layout.addRow(self.check_updates)

        self.show_notifications = QCheckBox("Show tray notifications")
        self.show_notifications.setChecked(config.SHOW_NOTIFICATIONS)
        layout.addRow(self.show_notifications)

        self.play_sound = QCheckBox("Play capture sound")
        self.play_sound.setChecked(config.PLAY_CAMERA_SOUND)
        layout.addRow(self.play_sound)

        self.after_capture = QComboBox()
        self.after_capture.addItems(["Open in Editor", "Save to File", "Copy to Clipboard"])
        idx_map = {"editor": 0, "save": 1, "clipboard": 2}
        self.after_capture.setCurrentIndex(idx_map.get(config.AFTER_CAPTURE_ACTION, 0))
        layout.addRow("After capture:", self.after_capture)

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
            "<i style='color:#6c7086;'>Select region/window first, then interact<br>"
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
        info.setStyleSheet("color: #a6adc8; font-size: 9pt;")
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

        restart_note = QLabel(
            "<i style='color:#f9e2af;'>Hotkey changes require a restart "
            "to take effect.</i>"
        )
        form.addRow(restart_note)

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
        self.file_format.addItems(["png", "jpg", "bmp", "gif", "tiff"])
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
        self.filename_pattern.setToolTip(
            "Variables: {YYYY}, {MM}, {DD}, {hh}, {mm}, {ss}")
        layout.addRow("Filename pattern:", self.filename_pattern)

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

        # Highlight color picker
        hl_row = QHBoxLayout()
        self._highlight_color = QColor(config.EDITOR_HIGHLIGHT_COLOR)
        self.highlight_btn = QPushButton()
        self.highlight_btn.setFixedSize(28, 28)
        self._update_color_btn(self.highlight_btn, self._highlight_color)
        self.highlight_btn.clicked.connect(self._pick_highlight_color)
        hl_row.addWidget(self.highlight_btn)
        hl_row.addWidget(QLabel(config.EDITOR_HIGHLIGHT_COLOR))
        hl_row.addStretch()
        layout.addRow("Highlight color:", hl_row)

        return w

    # --- Tab: Frame ---

    def _create_frame_tab(self):
        w = QWidget()
        layout = QFormLayout(w)
        layout.setSpacing(10)

        layout.addRow(QLabel("Border"))

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
        config_label.setStyleSheet("color: #6c7086; font-size: 9pt;")
        config_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow(config_label)

        log_label = QLabel(f"Log: {config.log_file}")
        log_label.setStyleSheet("color: #6c7086; font-size: 9pt;")
        log_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow(log_label)

        open_log_btn = QPushButton("Open Log File")
        open_log_btn.clicked.connect(self._open_log)
        layout.addRow(open_log_btn)

        return w

    # --- Helpers ---

    def _update_color_btn(self, btn, color):
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color.name()}; "
            f"border: 2px solid #45475a; border-radius: 4px; }}"
            f"QPushButton:hover {{ border-color: #89b4fa; }}"
        )

    def _pick_highlight_color(self):
        color = QColorDialog.getColor(
            self._highlight_color, self, "Highlight Color")
        if color.isValid():
            self._highlight_color = color
            self._update_color_btn(self.highlight_btn, color)

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
        # General
        config.LAUNCH_AT_STARTUP = self.launch_startup.isChecked()
        config.MINIMIZE_TO_TRAY = self.minimize_tray.isChecked()
        config.CHECK_FOR_UPDATES = self.check_updates.isChecked()
        config.SHOW_NOTIFICATIONS = self.show_notifications.isChecked()
        config.PLAY_CAMERA_SOUND = self.play_sound.isChecked()
        actions = ["editor", "save", "clipboard"]
        config.AFTER_CAPTURE_ACTION = actions[
            self.after_capture.currentIndex()]
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
        config.EDITOR_HIGHLIGHT_COLOR = self._highlight_color.name()

        # Frame
        config.BORDER_WIDTH = self.border_width.value()
        config.BORDER_COLOR = self._border_color.name()
        config.SHADOW_RADIUS = self.shadow_radius.value()
        config.SHADOW_OPACITY = self.shadow_opacity.value()
        config.ROUNDED_CORNERS_RADIUS = self.rounded_radius.value()

        # Advanced
        config.CAPTURE_HISTORY_ENABLED = self.history_enabled.isChecked()
        config.CAPTURE_HISTORY_MAX = self.history_max.value()
        config.PIN_OPACITY = self.pin_opacity.value()

        # Apply startup registry
        try:
            from utils import set_startup_registry
            set_startup_registry(config.LAUNCH_AT_STARTUP)
        except Exception:
            pass

        config.save()
        log.info("Settings saved")
        self.accept()

    def _stylesheet(self):
        return """
            QDialog { background-color: #1e1e2e; }
            QTabWidget::pane {
                border: 1px solid #45475a; border-radius: 6px;
                background: #1e1e2e;
            }
            QTabBar::tab {
                background: #313244; color: #cdd6f4; padding: 8px 14px;
                border: 1px solid #45475a; border-bottom: none;
                border-top-left-radius: 6px; border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1e1e2e; border-bottom: 2px solid #89b4fa;
            }
            QTabBar::tab:hover { background: #45475a; }
            QWidget { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { background: transparent; }
            QCheckBox { spacing: 8px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QGroupBox {
                font-weight: bold; border: 1px solid #45475a;
                border-radius: 6px; margin-top: 8px; padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 12px; padding: 0 4px;
            }
            QComboBox, QSpinBox, QLineEdit {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 4px;
                padding: 4px 8px; min-height: 24px;
            }
            QComboBox:hover, QSpinBox:hover, QLineEdit:hover {
                border-color: #89b4fa;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #313244; color: #cdd6f4;
                selection-background-color: #45475a;
                border: 1px solid #45475a;
            }
            QSlider::groove:horizontal {
                height: 6px; background: #313244; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px; height: 16px; margin: -5px 0;
                background: #89b4fa; border-radius: 8px;
            }
            QPushButton {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 6px 16px; min-height: 24px;
            }
            QPushButton:hover {
                background-color: #45475a; border-color: #89b4fa;
            }
            QDialogButtonBox QPushButton { min-width: 80px; }
        """
