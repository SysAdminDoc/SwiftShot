"""
SwiftShot Application Core
System tray icon, hotkey management, capture orchestration.

PrintScreen -> Capture menu popup (all modes)
Alt+PrtSc   -> Interactive window capture (Greenshot-style)
Ctrl+PrtSc  -> Monitor picker / fullscreen
Shift+PrtSc -> Last region re-capture

Space toggles between Region <-> Window mode during capture.
"""

import sys
import os
from PyQt5.QtWidgets import (
    QSystemTrayIcon, QMenu, QAction, QApplication, QMessageBox,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QTimer, QRect

from config import config


class OcrResultDialog(QDialog):
    """Dialog to show OCR results with copy-to-clipboard."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OCR Result - SwiftShot")
        self.setMinimumSize(500, 350)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; background: transparent; }
            QTextEdit {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 8px; font-family: 'Consolas'; font-size: 10pt;
            }
            QPushButton {
                background-color: #45475a; color: #cdd6f4;
                border: 1px solid #585b70; border-radius: 6px;
                padding: 8px 20px; font-size: 10pt;
            }
            QPushButton:hover { background-color: #585b70; border-color: #89b4fa; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl = QLabel("Extracted Text:")
        lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        layout.addWidget(lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setReadOnly(False)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy)
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _copy(self):
        QApplication.clipboard().setText(self.text_edit.toPlainText())


class SwiftShotApp:
    """Main application controller."""

    def __init__(self, app: QApplication):
        self.app = app
        self.tray_icon = None
        self.editors = []
        self._overlay = None
        self._window_picker = None
        self._hotkey_listener = None

    def start(self):
        self._create_tray_icon()
        self._register_hotkeys()
        self.tray_icon.show()
        self.tray_icon.showMessage(
            "SwiftShot",
            "SwiftShot is running. Press PrintScreen for capture menu.",
            QSystemTrayIcon.Information, 2000
        )

    # -------------------------------------------------------------------
    # Tray Icon
    # -------------------------------------------------------------------

    def _create_app_icon(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#89b4fa"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
        painter.setBrush(QColor("#1e1e2e"))
        painter.drawRoundedRect(12, 18, 40, 30, 4, 4)
        painter.setBrush(QColor("#89b4fa"))
        painter.drawEllipse(24, 22, 16, 16)
        painter.setBrush(QColor("#1e1e2e"))
        painter.drawEllipse(28, 26, 8, 8)
        painter.setBrush(QColor("#f9e2af"))
        painter.drawRect(16, 21, 6, 3)
        painter.setPen(QColor("#cdd6f4"))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(22, 56, "SS")
        painter.end()
        return QIcon(pixmap)

    def _create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self._create_app_icon(), self.app)

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px; padding: 4px;
            }
            QMenu::item { padding: 6px 28px 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #45475a; }
            QMenu::separator { height: 1px; background-color: #313244; margin: 4px 8px; }
        """)

        menu.addAction("Capture Menu\tPrintScreen").triggered.connect(self.show_capture_menu)
        menu.addSeparator()
        menu.addAction("Capture Region").triggered.connect(self.capture_region)
        menu.addAction("Capture Window\tAlt+PrtSc").triggered.connect(self.capture_window)
        menu.addAction("Capture Full Screen\tCtrl+PrtSc").triggered.connect(self.capture_fullscreen)
        menu.addAction("Capture Last Region\tShift+PrtSc").triggered.connect(self.capture_last_region)
        menu.addSeparator()
        menu.addAction("Region (Freehand)").triggered.connect(self.capture_freehand)
        menu.addAction("OCR Region").triggered.connect(self.capture_ocr)
        menu.addSeparator()
        menu.addAction("Open Image from File...").triggered.connect(self.open_from_file)
        menu.addAction("Open Image from Clipboard").triggered.connect(self.open_from_clipboard)
        menu.addSeparator()
        menu.addAction("Preferences...").triggered.connect(self.show_settings)
        menu.addSeparator()
        menu.addAction("About SwiftShot").triggered.connect(self.show_about)
        menu.addSeparator()
        menu.addAction("Exit").triggered.connect(self.exit_app)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip("SwiftShot - Screenshot Tool")
        self.tray_icon.activated.connect(self._tray_activated)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_capture_menu()

    # -------------------------------------------------------------------
    # Hotkeys
    # -------------------------------------------------------------------

    def _register_hotkeys(self):
        if sys.platform != 'win32':
            return
        try:
            from hotkeys import HotkeyManager
            self._hotkey_listener = HotkeyManager()
            self._hotkey_listener.register("Print", self.show_capture_menu)
            self._hotkey_listener.register("Alt+Print", self.capture_window)
            self._hotkey_listener.register("Ctrl+Print", self.capture_fullscreen)
            self._hotkey_listener.register("Shift+Print", self.capture_last_region)
            self._hotkey_listener.start()
        except Exception as e:
            print(f"Warning: Could not register hotkeys: {e}")

    # -------------------------------------------------------------------
    # Capture Menu (PrintScreen popup)
    # -------------------------------------------------------------------

    def show_capture_menu(self):
        QTimer.singleShot(50, self._do_show_capture_menu)

    def _do_show_capture_menu(self):
        from capture_menu import CaptureMenu
        menu = CaptureMenu()
        menu.capture_monitor.connect(self._on_menu_monitor)
        menu.capture_window.connect(self.capture_window)
        menu.capture_region.connect(self.capture_region)
        menu.capture_freehand.connect(self.capture_freehand)
        menu.capture_last_region.connect(self.capture_last_region)
        menu.capture_ocr.connect(self.capture_ocr)
        menu.open_file.connect(self.open_from_file)
        menu.open_clipboard.connect(self.open_from_clipboard)
        menu.popup_at_cursor()
        # Keep reference so it doesn't get garbage collected
        self._capture_menu = menu

    def _on_menu_monitor(self, index):
        QTimer.singleShot(100, lambda: self._do_capture_monitor(index))

    def _do_capture_monitor(self, index):
        from capture import CaptureManager
        if index == -1:
            screenshot = CaptureManager.capture_fullscreen()
        else:
            screenshot = CaptureManager.capture_monitor(index)
        if screenshot:
            self._handle_capture(screenshot)

    # -------------------------------------------------------------------
    # Region Capture (rectangle)
    # -------------------------------------------------------------------

    def capture_region(self):
        QTimer.singleShot(100, self._do_region_capture)

    def _do_region_capture(self):
        self._start_region_overlay("rectangle")

    def _start_region_overlay(self, mode="rectangle", ocr_mode=False):
        from capture import CaptureManager
        from overlay import RegionSelector

        full = CaptureManager.capture_fullscreen()
        if full is None:
            return

        self._overlay = RegionSelector(full, mode=mode)
        self._overlay._ocr_mode = ocr_mode
        self._overlay._full_screenshot = full
        self._overlay.region_selected.connect(
            lambda rect: self._on_region_selected(full, rect, ocr_mode)
        )
        self._overlay.switch_to_window.connect(
            lambda: self._switch_to_window_mode(full)
        )
        self._overlay.cancelled.connect(lambda: self._close_overlay())
        self._overlay.show_spanning()

    def _on_region_selected(self, full_screenshot, rect, ocr_mode=False):
        self._close_overlay()
        if rect.width() < 1 or rect.height() < 1:
            return
        from capture import CaptureManager
        cropped = CaptureManager.crop_image(full_screenshot, rect)
        if cropped:
            config.LAST_REGION = f"{rect.x()},{rect.y()},{rect.width()},{rect.height()}"
            config.save()
            if ocr_mode:
                self._do_ocr(cropped)
            else:
                self._handle_capture(cropped)

    def _close_overlay(self):
        if self._overlay:
            self._overlay.close()
            self._overlay = None

    # -------------------------------------------------------------------
    # Freehand Region Capture
    # -------------------------------------------------------------------

    def capture_freehand(self):
        QTimer.singleShot(100, self._do_freehand_capture)

    def _do_freehand_capture(self):
        self._start_region_overlay("freehand")

    # -------------------------------------------------------------------
    # Window Capture (Greenshot interactive)
    # -------------------------------------------------------------------

    def capture_window(self):
        QTimer.singleShot(100, self._do_window_capture)

    def _do_window_capture(self):
        from capture import CaptureManager
        full = CaptureManager.capture_fullscreen()
        if full is None:
            return
        self._start_window_picker(full)

    def _start_window_picker(self, full_screenshot):
        from window_picker import WindowPicker
        self._close_window_picker()
        self._window_picker = WindowPicker(full_screenshot)
        self._window_picker._full_screenshot = full_screenshot
        self._window_picker.element_selected.connect(
            lambda rect: self._on_window_selected(full_screenshot, rect)
        )
        self._window_picker.switch_to_region.connect(
            lambda: self._switch_to_region_mode(full_screenshot)
        )
        self._window_picker.cancelled.connect(lambda: self._close_window_picker())
        self._window_picker.show_spanning()

    def _on_window_selected(self, full_screenshot, rect):
        """Handle window element selection. rect is in screen coords."""
        self._close_window_picker()
        if rect.width() < 1 or rect.height() < 1:
            return
        from capture import CaptureManager
        cropped = CaptureManager.crop_image(full_screenshot, rect)
        if cropped:
            self._handle_capture(cropped)

    def _close_window_picker(self):
        if self._window_picker:
            self._window_picker.close()
            self._window_picker = None

    # -------------------------------------------------------------------
    # Space Toggle: Region <-> Window
    # -------------------------------------------------------------------

    def _switch_to_window_mode(self, full_screenshot):
        """Switch from region overlay to window picker (Space key)."""
        self._close_overlay()
        QTimer.singleShot(50, lambda: self._start_window_picker(full_screenshot))

    def _switch_to_region_mode(self, full_screenshot):
        """Switch from window picker to region overlay (Space key)."""
        self._close_window_picker()
        from overlay import RegionSelector
        self._overlay = RegionSelector(full_screenshot, mode="rectangle")
        self._overlay._full_screenshot = full_screenshot
        self._overlay.region_selected.connect(
            lambda rect: self._on_region_selected(full_screenshot, rect, False)
        )
        self._overlay.switch_to_window.connect(
            lambda: self._switch_to_window_mode(full_screenshot)
        )
        self._overlay.cancelled.connect(lambda: self._close_overlay())
        QTimer.singleShot(50, lambda: self._overlay.show_spanning())

    # -------------------------------------------------------------------
    # Fullscreen / Monitor Capture
    # -------------------------------------------------------------------

    def capture_fullscreen(self):
        QTimer.singleShot(100, self._do_fullscreen_capture)

    def _do_fullscreen_capture(self):
        screens = QApplication.screens()
        if len(screens) > 1:
            from monitor_picker import MonitorPicker
            picker = MonitorPicker()
            picker.monitor_selected.connect(
                lambda idx: self._do_capture_monitor(idx)
            )
            picker.exec_()
        else:
            from capture import CaptureManager
            screenshot = CaptureManager.capture_fullscreen()
            if screenshot:
                self._handle_capture(screenshot)

    # -------------------------------------------------------------------
    # Last Region
    # -------------------------------------------------------------------

    def capture_last_region(self):
        if not config.LAST_REGION:
            self.capture_region()
            return
        QTimer.singleShot(100, self._do_last_region_capture)

    def _do_last_region_capture(self):
        try:
            parts = config.LAST_REGION.split(',')
            x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        except (ValueError, IndexError):
            self.capture_region()
            return
        from capture import CaptureManager
        full = CaptureManager.capture_fullscreen()
        if full:
            rect = QRect(x, y, w, h)
            cropped = CaptureManager.crop_image(full, rect)
            if cropped:
                self._handle_capture(cropped)

    # -------------------------------------------------------------------
    # OCR Capture
    # -------------------------------------------------------------------

    def capture_ocr(self):
        QTimer.singleShot(100, self._do_ocr_capture)

    def _do_ocr_capture(self):
        self._start_region_overlay("rectangle", ocr_mode=True)

    def _do_ocr(self, pixmap):
        """Run OCR on captured region and show results."""
        try:
            from ocr import ocr_pixmap
            text = ocr_pixmap(pixmap)
            if text:
                QApplication.clipboard().setText(text)
                dlg = OcrResultDialog(text)
                dlg.exec_()
            else:
                self.tray_icon.showMessage(
                    "SwiftShot OCR", "No text detected in the selected region.",
                    QSystemTrayIcon.Warning, 3000
                )
        except Exception as e:
            QMessageBox.warning(
                None, "OCR Error",
                f"Could not extract text:\n\n{str(e)}"
            )

    # -------------------------------------------------------------------
    # Post-capture handling
    # -------------------------------------------------------------------

    def _handle_capture(self, pixmap):
        action = config.AFTER_CAPTURE_ACTION
        if action == "editor":
            self._open_editor(pixmap)
        elif action == "save":
            self._save_directly(pixmap)
        elif action == "clipboard":
            self._copy_to_clipboard(pixmap)
        else:
            self._open_editor(pixmap)

    def _open_editor(self, pixmap):
        from editor import ImageEditor
        editor = ImageEditor(pixmap, self)
        editor.show()
        self.editors.append(editor)

    def _save_directly(self, pixmap):
        filepath = config.get_filename()
        fmt = config.OUTPUT_FILE_FORMAT.upper()
        if fmt == "JPG":
            fmt = "JPEG"
        quality = config.OUTPUT_JPEG_QUALITY if fmt == "JPEG" else -1
        success = pixmap.save(filepath, fmt, quality)
        if success:
            self.tray_icon.showMessage(
                "SwiftShot", f"Screenshot saved to {filepath}",
                QSystemTrayIcon.Information, 2000
            )
            if config.COPY_PATH_TO_CLIPBOARD:
                QApplication.clipboard().setText(filepath)

    def _copy_to_clipboard(self, pixmap):
        QApplication.clipboard().setPixmap(pixmap)
        self.tray_icon.showMessage(
            "SwiftShot", "Screenshot copied to clipboard",
            QSystemTrayIcon.Information, 1500
        )

    # -------------------------------------------------------------------
    # Open from file / clipboard
    # -------------------------------------------------------------------

    def open_from_file(self):
        from PyQt5.QtWidgets import QFileDialog
        filepath, _ = QFileDialog.getOpenFileName(
            None, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif);;All Files (*)"
        )
        if filepath:
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                self._open_editor(pixmap)

    def open_from_clipboard(self):
        clipboard = QApplication.clipboard()
        pixmap = clipboard.pixmap()
        if pixmap and not pixmap.isNull():
            self._open_editor(pixmap)
        else:
            self.tray_icon.showMessage(
                "SwiftShot", "No image found in clipboard",
                QSystemTrayIcon.Warning, 2000
            )

    # -------------------------------------------------------------------
    # Settings / About
    # -------------------------------------------------------------------

    def show_settings(self):
        from settings_dialog import SettingsDialog
        dialog = SettingsDialog()
        dialog.exec_()

    def show_about(self):
        QMessageBox.about(
            None, "About SwiftShot",
            "<h2>SwiftShot v1.1.0</h2>"
            "<p>A comprehensive, debloated screenshot tool.</p>"
            "<p>Inspired by Greenshot - built without any 3rd-party "
            "integrations or plugin bloat.</p>"
            "<hr>"
            "<p><b>Capture Modes:</b></p>"
            "<p>Region / Freehand Region / Window (Greenshot-style) / Fullscreen<br>"
            "Per-monitor capture / Last Region / OCR Region</p>"
            "<p><b>Window Capture:</b> Interactive hover-highlight with<br>"
            "PgDown/PgUp hierarchy, Space toggle, Z magnifier</p>"
            "<p><b>Editor:</b> Crop, shapes, arrows, text, highlight, obfuscate,<br>"
            "step numbers, OCR, auto-crop, rotate, flip</p>"
            "<hr>"
            "<p>License: GPL-3.0</p>"
        )

    def editor_closed(self, editor):
        if editor in self.editors:
            self.editors.remove(editor)

    def exit_app(self):
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        if self.tray_icon:
            self.tray_icon.hide()
        config.save()
        QApplication.quit()
