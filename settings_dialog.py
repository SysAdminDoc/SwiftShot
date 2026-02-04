"""
SwiftShot Settings Dialog
Configuration UI for all application settings.
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QComboBox, QCheckBox, QSpinBox, QLineEdit,
    QPushButton, QFileDialog, QLabel, QGroupBox, QDialogButtonBox,
    QSlider
)
from PyQt5.QtCore import Qt

from config import config


class SettingsDialog(QDialog):
    """Application settings dialog."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SwiftShot Preferences")
        self.setMinimumSize(500, 450)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Tab widget
        tabs = QTabWidget()
        tabs.addTab(self._create_general_tab(), "General")
        tabs.addTab(self._create_output_tab(), "Output")
        tabs.addTab(self._create_capture_tab(), "Capture")
        tabs.addTab(self._create_editor_tab(), "Editor")
        layout.addWidget(tabs)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        layout.addWidget(buttons)
    
    def _create_general_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Startup
        group = QGroupBox("Startup")
        form = QFormLayout()
        
        self.launch_startup = QCheckBox("Launch SwiftShot on Windows startup")
        self.launch_startup.setChecked(config.LAUNCH_AT_STARTUP)
        form.addRow(self.launch_startup)
        
        self.minimize_tray = QCheckBox("Minimize to system tray")
        self.minimize_tray.setChecked(config.MINIMIZE_TO_TRAY)
        form.addRow(self.minimize_tray)
        
        group.setLayout(form)
        layout.addWidget(group)
        
        # After Capture
        group2 = QGroupBox("After Capture")
        form2 = QFormLayout()
        
        self.after_capture = QComboBox()
        self.after_capture.addItems([
            "Open in Editor",
            "Save Directly",
            "Copy to Clipboard",
        ])
        action_map = {"editor": 0, "save": 1, "clipboard": 2}
        self.after_capture.setCurrentIndex(
            action_map.get(config.AFTER_CAPTURE_ACTION, 0)
        )
        form2.addRow("Default action:", self.after_capture)
        
        self.copy_path = QCheckBox("Copy file path to clipboard after saving")
        self.copy_path.setChecked(config.COPY_PATH_TO_CLIPBOARD)
        form2.addRow(self.copy_path)
        
        self.play_sound = QCheckBox("Play camera sound on capture")
        self.play_sound.setChecked(config.PLAY_CAMERA_SOUND)
        form2.addRow(self.play_sound)
        
        group2.setLayout(form2)
        layout.addWidget(group2)
        
        layout.addStretch()
        return widget
    
    def _create_output_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("File Output")
        form = QFormLayout()
        
        # Format
        self.file_format = QComboBox()
        self.file_format.addItems(["png", "jpg", "bmp", "gif", "tiff"])
        idx = self.file_format.findText(config.OUTPUT_FILE_FORMAT)
        if idx >= 0:
            self.file_format.setCurrentIndex(idx)
        form.addRow("Image format:", self.file_format)
        
        # Quality
        self.jpeg_quality = QSpinBox()
        self.jpeg_quality.setRange(1, 100)
        self.jpeg_quality.setValue(config.OUTPUT_JPEG_QUALITY)
        self.jpeg_quality.setSuffix("%")
        form.addRow("JPEG quality:", self.jpeg_quality)
        
        # Filename pattern
        self.filename_pattern = QLineEdit(config.OUTPUT_FILENAME_PATTERN)
        form.addRow("Filename pattern:", self.filename_pattern)
        
        pattern_help = QLabel(
            "Tokens: {YYYY} {MM} {DD} {hh} {mm} {ss}"
        )
        pattern_help.setStyleSheet("color: #6c7086; font-size: 9pt; background: transparent;")
        form.addRow("", pattern_help)
        
        # Output directory
        dir_layout = QHBoxLayout()
        self.output_dir = QLineEdit(config.OUTPUT_FILE_PATH or "(Desktop)")
        self.output_dir.setReadOnly(True)
        dir_layout.addWidget(self.output_dir)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_layout.addWidget(browse_btn)
        
        form.addRow("Save to:", dir_layout)
        
        self.auto_increment = QCheckBox("Auto-increment filename if exists")
        self.auto_increment.setChecked(config.OUTPUT_FILE_INCREMENT)
        form.addRow(self.auto_increment)
        
        group.setLayout(form)
        layout.addWidget(group)
        
        layout.addStretch()
        return widget
    
    def _create_capture_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("Capture Options")
        form = QFormLayout()
        
        self.capture_mouse = QCheckBox("Include mouse pointer in captures")
        self.capture_mouse.setChecked(config.CAPTURE_MOUSE_POINTER)
        form.addRow(self.capture_mouse)
        
        self.capture_delay = QSpinBox()
        self.capture_delay.setRange(0, 10000)
        self.capture_delay.setValue(config.CAPTURE_DELAY_MS)
        self.capture_delay.setSuffix(" ms")
        self.capture_delay.setSingleStep(250)
        form.addRow("Capture delay:", self.capture_delay)
        
        group.setLayout(form)
        layout.addWidget(group)
        
        # Hotkeys info
        group2 = QGroupBox("Hotkeys")
        form2 = QFormLayout()
        
        hotkeys_info = [
            ("Region capture:", config.CAPTURE_REGION_HOTKEY),
            ("Window capture:", config.CAPTURE_WINDOW_HOTKEY),
            ("Fullscreen capture:", config.CAPTURE_FULLSCREEN_HOTKEY),
            ("Last region:", config.CAPTURE_LAST_REGION_HOTKEY),
        ]
        
        for label, key in hotkeys_info:
            key_label = QLabel(key)
            key_label.setStyleSheet(
                "background-color: #313244; padding: 4px 8px; "
                "border: 1px solid #45475a; border-radius: 4px;"
            )
            form2.addRow(label, key_label)
        
        group2.setLayout(form2)
        layout.addWidget(group2)
        
        layout.addStretch()
        return widget
    
    def _create_editor_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        group = QGroupBox("Editor Defaults")
        form = QFormLayout()
        
        self.default_line_width = QSpinBox()
        self.default_line_width.setRange(1, 20)
        self.default_line_width.setValue(config.EDITOR_DEFAULT_LINE_WIDTH)
        form.addRow("Line width:", self.default_line_width)
        
        self.default_font_size = QSpinBox()
        self.default_font_size.setRange(8, 72)
        self.default_font_size.setValue(config.EDITOR_DEFAULT_FONT_SIZE)
        form.addRow("Font size:", self.default_font_size)
        
        self.obfuscate_factor = QSpinBox()
        self.obfuscate_factor.setRange(4, 32)
        self.obfuscate_factor.setValue(config.EDITOR_OBFUSCATE_FACTOR)
        form.addRow("Pixelation block size:", self.obfuscate_factor)
        
        self.obfuscate_mode = QComboBox()
        self.obfuscate_mode.addItems(["pixelate", "blur"])
        idx = self.obfuscate_mode.findText(config.EDITOR_OBFUSCATE_MODE)
        if idx >= 0:
            self.obfuscate_mode.setCurrentIndex(idx)
        form.addRow("Obfuscate mode:", self.obfuscate_mode)
        
        group.setLayout(form)
        layout.addWidget(group)
        
        layout.addStretch()
        return widget
    
    def _browse_output_dir(self):
        """Browse for output directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Output Directory",
            config.OUTPUT_FILE_PATH or os.path.expanduser("~")
        )
        if directory:
            self.output_dir.setText(directory)
    
    def _apply(self):
        """Apply settings without closing."""
        action_map = {0: "editor", 1: "save", 2: "clipboard"}
        
        config.LAUNCH_AT_STARTUP = self.launch_startup.isChecked()
        config.MINIMIZE_TO_TRAY = self.minimize_tray.isChecked()
        config.AFTER_CAPTURE_ACTION = action_map.get(
            self.after_capture.currentIndex(), "editor"
        )
        config.COPY_PATH_TO_CLIPBOARD = self.copy_path.isChecked()
        config.PLAY_CAMERA_SOUND = self.play_sound.isChecked()
        config.OUTPUT_FILE_FORMAT = self.file_format.currentText()
        config.OUTPUT_JPEG_QUALITY = self.jpeg_quality.value()
        config.OUTPUT_FILENAME_PATTERN = self.filename_pattern.text()
        config.OUTPUT_FILE_INCREMENT = self.auto_increment.isChecked()
        config.CAPTURE_MOUSE_POINTER = self.capture_mouse.isChecked()
        config.CAPTURE_DELAY_MS = self.capture_delay.value()
        config.EDITOR_DEFAULT_LINE_WIDTH = self.default_line_width.value()
        config.EDITOR_DEFAULT_FONT_SIZE = self.default_font_size.value()
        config.EDITOR_OBFUSCATE_FACTOR = self.obfuscate_factor.value()
        config.EDITOR_OBFUSCATE_MODE = self.obfuscate_mode.currentText()
        
        output_text = self.output_dir.text()
        if output_text and output_text != "(Desktop)":
            config.OUTPUT_FILE_PATH = output_text
        
        config.save()
    
    def _save_and_close(self):
        """Apply and close."""
        self._apply()
        self.accept()
