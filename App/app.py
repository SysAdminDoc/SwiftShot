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
import webbrowser
from PyQt5.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QMessageBox, QDialog
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QTimer, QRect

from config import config
from logger import log
from ocr_dialog import OcrResultDialog


class SwiftShotApp:
    """Main application controller."""

    def __init__(self, app: QApplication):
        self.app = app
        self.tray_icon = None
        self.editors = []
        self._overlay = None
        self._window_picker = None
        self._hotkey_listener = None
        self._pin_windows = []
        self._clipboard_watcher_enabled = config.CLIPBOARD_WATCHER_ENABLED
        self._clipboard_timer = None
        self._last_clipboard_pixmap = None
        self._history_dialog = None
        self._capture_menu = None
        self._update_checker = None

    def start(self):
        # Set app-wide icon so every QWidget/QDialog inherits it
        app_icon = self._create_app_icon()
        self.app.setWindowIcon(app_icon)

        self._create_tray_icon()
        self._register_hotkeys()
        self.tray_icon.show()

        if config.SHOW_NOTIFICATIONS:
            self.tray_icon.showMessage(
                "SwiftShot",
                "SwiftShot is running. Press PrintScreen for capture menu.",
                QSystemTrayIcon.Information, 2000
            )

        # Start clipboard watcher if enabled
        if self._clipboard_watcher_enabled:
            self._start_clipboard_watcher()

        # Apply startup registry
        try:
            from utils import set_startup_registry
            set_startup_registry(config.LAUNCH_AT_STARTUP)
        except Exception as e:
            log.warning(f"Could not set startup registry: {e}")

        # Check for updates in background
        if config.CHECK_FOR_UPDATES:
            self._check_for_updates()

        log.info("SwiftShot started successfully")

    # -------------------------------------------------------------------
    # Update Checker
    # -------------------------------------------------------------------

    def _check_for_updates(self):
        try:
            from updater import UpdateChecker
            self._update_checker = UpdateChecker()
            self._update_checker.update_available.connect(self._on_update_available)
            self._update_checker.start()
        except Exception as e:
            log.warning(f"Could not start update checker: {e}")

    def _on_update_available(self, version, url):
        if config.SHOW_NOTIFICATIONS:
            self.tray_icon.showMessage(
                "SwiftShot Update Available",
                f"Version {version} is available. Click tray icon to download.",
                QSystemTrayIcon.Information, 5000
            )
        self._update_url = url

    # -------------------------------------------------------------------
    # Tray Icon
    # -------------------------------------------------------------------

    def _create_app_icon(self):
        """Load swiftshot.ico from the bundle or generate programmatically."""
        icon = self._load_ico_file()
        if icon and not icon.isNull():
            return icon

        # Fallback: draw it in memory (dev/source mode)
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

    def _load_ico_file(self):
        """Try to locate swiftshot.ico or .png from standard locations."""
        candidates = []
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            candidates.append(os.path.join(exe_dir, "swiftshot.ico"))
            candidates.append(os.path.join(exe_dir, "swiftshot.png"))
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                candidates.append(os.path.join(meipass, "swiftshot.ico"))
                candidates.append(os.path.join(meipass, "swiftshot.png"))
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(script_dir, "swiftshot.ico"))
        candidates.append(os.path.join(script_dir, "swiftshot.png"))

        for path in candidates:
            if os.path.isfile(path):
                icon = QIcon(path)
                if not icon.isNull():
                    return icon
        return None

    def _create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self.app.windowIcon(), self.app)

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
        menu.addAction("Scrolling Capture...").triggered.connect(self.capture_scrolling)
        menu.addSeparator()
        menu.addAction("Open Image from File...").triggered.connect(self.open_from_file)
        menu.addAction("Open Image from Clipboard").triggered.connect(self.open_from_clipboard)
        menu.addSeparator()
        menu.addAction("Capture History...").triggered.connect(self.show_history)
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

            # Primary hotkeys
            if config.CAPTURE_REGION_HOTKEY:
                self._hotkey_listener.register(
                    config.CAPTURE_REGION_HOTKEY, self.show_capture_menu)
            if config.CAPTURE_WINDOW_HOTKEY:
                self._hotkey_listener.register(
                    config.CAPTURE_WINDOW_HOTKEY, self.capture_window)
            if config.CAPTURE_FULLSCREEN_HOTKEY:
                self._hotkey_listener.register(
                    config.CAPTURE_FULLSCREEN_HOTKEY, self.capture_fullscreen)
            if config.CAPTURE_LAST_REGION_HOTKEY:
                self._hotkey_listener.register(
                    config.CAPTURE_LAST_REGION_HOTKEY, self.capture_last_region)

            # Additional hotkeys (only register if user has set them)
            if config.CAPTURE_OCR_HOTKEY:
                self._hotkey_listener.register(
                    config.CAPTURE_OCR_HOTKEY, self.capture_ocr)
            if config.CAPTURE_FREEHAND_HOTKEY:
                self._hotkey_listener.register(
                    config.CAPTURE_FREEHAND_HOTKEY, self.capture_freehand)
            if config.CAPTURE_SCROLLING_HOTKEY:
                self._hotkey_listener.register(
                    config.CAPTURE_SCROLLING_HOTKEY, self.capture_scrolling)

            self._hotkey_listener.start()
            log.info("Hotkeys registered successfully")
        except Exception as e:
            log.warning(f"Could not register hotkeys: {e}")

    # -------------------------------------------------------------------
    # Capture Delay Helper
    # -------------------------------------------------------------------

    def _capture_with_delay(self, callback):
        """Execute callback after configured delay (with countdown if >0)."""
        delay = config.CAPTURE_DELAY_MS
        if delay > 0:
            try:
                from countdown_overlay import CountdownOverlay
                overlay = CountdownOverlay(delay)
                overlay.countdown_finished.connect(callback)
                overlay.cancelled.connect(lambda: None)
                self._countdown = overlay  # prevent GC
                overlay.start()
            except Exception as e:
                log.error(f"Countdown overlay failed: {e}")
                QTimer.singleShot(100, callback)
        else:
            QTimer.singleShot(100, callback)

    # -------------------------------------------------------------------
    # Capture Menu (PrintScreen popup)
    # -------------------------------------------------------------------

    def show_capture_menu(self):
        QTimer.singleShot(50, self._do_show_capture_menu)

    def _do_show_capture_menu(self):
        try:
            from capture_menu import CaptureMenu
            menu = CaptureMenu(clipboard_watching=self._clipboard_watcher_enabled)
            menu.capture_monitor.connect(self._on_menu_monitor)
            menu.capture_window.connect(self.capture_window)
            menu.capture_region.connect(self.capture_region)
            menu.capture_freehand.connect(self.capture_freehand)
            menu.capture_last_region.connect(self.capture_last_region)
            menu.capture_ocr.connect(self.capture_ocr)
            menu.capture_scrolling.connect(self.capture_scrolling)
            menu.open_file.connect(self.open_from_file)
            menu.open_clipboard.connect(self.open_from_clipboard)
            menu.show_history.connect(self.show_history)
            menu.toggle_clipboard_watcher.connect(self._toggle_clipboard_watcher)
            menu.popup_at_cursor()
            self._capture_menu = menu
        except Exception as e:
            log.error(f"Capture menu failed: {e}")

    def _on_menu_monitor(self, index):
        self._capture_with_delay(lambda: self._do_capture_monitor(index))

    def _do_capture_monitor(self, index):
        try:
            from capture import CaptureManager
            if index == -1:
                screenshot = CaptureManager.capture_fullscreen()
            else:
                screenshot = CaptureManager.capture_monitor(index)
            if screenshot:
                log.info(f"Monitor {index} captured: "
                         f"{screenshot.width()}x{screenshot.height()}")
                self._handle_capture(screenshot)
            else:
                log.warning(f"Monitor {index} capture returned None")
        except Exception as e:
            log.error(f"Monitor capture failed: {e}", exc_info=True)

    # -------------------------------------------------------------------
    # Region Capture
    # -------------------------------------------------------------------

    def capture_region(self):
        self._capture_with_delay(self._do_region_capture)

    def _do_region_capture(self):
        self._start_region_overlay("rectangle")

    def _start_region_overlay(self, mode="rectangle", ocr_mode=False):
        try:
            from capture import CaptureManager
            from overlay import RegionSelector

            full = CaptureManager.capture_fullscreen()
            if full is None:
                log.warning("capture_fullscreen returned None")
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
        except Exception as e:
            log.error(f"Region overlay failed: {e}")

    def _on_region_selected(self, full_screenshot, rect, ocr_mode=False):
        self._close_overlay()
        if rect.width() < 1 or rect.height() < 1:
            return

        # Save last region
        config.LAST_REGION = f"{rect.x()},{rect.y()},{rect.width()},{rect.height()}"
        config.save()

        if ocr_mode:
            # OCR doesn't use timer - crop from the already-taken screenshot
            try:
                from capture import CaptureManager
                cropped = CaptureManager.crop_image(full_screenshot, rect)
                if cropped:
                    self._do_ocr(cropped)
            except Exception as e:
                log.error(f"OCR crop failed: {e}")
            return

        # Check if timed capture is active
        if config.CAPTURE_TIMER_ENABLED and config.CAPTURE_TIMER_SECONDS > 0:
            self._timed_capture_region(rect)
        else:
            # Immediate capture from the already-taken screenshot
            try:
                from capture import CaptureManager
                cropped = CaptureManager.crop_image(full_screenshot, rect)
                if cropped:
                    self._handle_capture(cropped)
            except Exception as e:
                log.error(f"Region selection failed: {e}")

    def _close_overlay(self):
        if self._overlay:
            try:
                self._overlay.hide()
                self._overlay.close()
            except Exception:
                pass
            self._overlay = None

    # -------------------------------------------------------------------
    # Freehand Region Capture
    # -------------------------------------------------------------------

    def capture_freehand(self):
        self._capture_with_delay(self._do_freehand_capture)

    def _do_freehand_capture(self):
        self._start_region_overlay("freehand")

    # -------------------------------------------------------------------
    # Window Capture
    # -------------------------------------------------------------------

    def capture_window(self):
        self._capture_with_delay(self._do_window_capture)

    def _do_window_capture(self):
        try:
            from capture import CaptureManager
            full = CaptureManager.capture_fullscreen()
            if full is None:
                return
            self._start_window_picker(full)
        except Exception as e:
            log.error(f"Window capture failed: {e}")

    def _start_window_picker(self, full_screenshot):
        try:
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
        except Exception as e:
            log.error(f"Window picker failed: {e}")

    def _on_window_selected(self, full_screenshot, rect):
        self._close_window_picker()
        if rect.width() < 1 or rect.height() < 1:
            return

        # Check if timed capture is active
        if config.CAPTURE_TIMER_ENABLED and config.CAPTURE_TIMER_SECONDS > 0:
            self._timed_capture_region(rect)
        else:
            try:
                from capture import CaptureManager
                cropped = CaptureManager.crop_image(full_screenshot, rect)
                if cropped:
                    self._handle_capture(cropped)
            except Exception as e:
                log.error(f"Window selection failed: {e}")

    def _close_window_picker(self):
        if self._window_picker:
            try:
                self._window_picker.hide()
                self._window_picker.close()
            except Exception:
                pass
            self._window_picker = None

    # -------------------------------------------------------------------
    # Timed Capture
    # -------------------------------------------------------------------

    def _timed_capture_region(self, rect):
        """
        Timed capture flow:
        1. User already selected a region/window (overlay is closed)
        2. Show countdown overlay so user can interact with the screen
        3. When countdown ends, take a FRESH screenshot and crop to rect
        """
        seconds = config.CAPTURE_TIMER_SECONDS
        total_ms = seconds * 1000
        log.info(f"Timed capture: {seconds}s countdown for region {rect.x()},{rect.y()} "
                 f"{rect.width()}x{rect.height()}")

        try:
            from countdown_overlay import CountdownOverlay
            overlay = CountdownOverlay(total_ms)
            overlay.countdown_finished.connect(
                lambda r=QRect(rect): self._timed_capture_fire(r)
            )
            overlay.cancelled.connect(lambda: log.info("Timed capture cancelled"))
            self._countdown = overlay  # prevent GC
            overlay.start()
        except Exception as e:
            log.error(f"Timed capture countdown failed: {e}")
            # Fall back to immediate capture
            self._timed_capture_fire(rect)

    def _timed_capture_fire(self, rect):
        """Take a fresh screenshot and crop to the saved region."""
        try:
            from capture import CaptureManager
            fresh = CaptureManager.capture_fullscreen()
            if fresh:
                cropped = CaptureManager.crop_image(fresh, rect)
                if cropped:
                    log.info("Timed capture completed")
                    self._handle_capture(cropped)
                else:
                    log.warning("Timed capture: crop returned None")
            else:
                log.warning("Timed capture: fresh screenshot returned None")
        except Exception as e:
            log.error(f"Timed capture fire failed: {e}")

    # -------------------------------------------------------------------
    # Space Toggle: Region <-> Window
    # -------------------------------------------------------------------

    def _switch_to_window_mode(self, full_screenshot):
        self._close_overlay()
        QTimer.singleShot(50, lambda: self._start_window_picker(full_screenshot))

    def _switch_to_region_mode(self, full_screenshot):
        self._close_window_picker()
        try:
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
        except Exception as e:
            log.error(f"Switch to region mode failed: {e}")

    # -------------------------------------------------------------------
    # Fullscreen / Monitor Capture
    # -------------------------------------------------------------------

    def capture_fullscreen(self):
        self._capture_with_delay(self._do_fullscreen_capture)

    def _do_fullscreen_capture(self):
        try:
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
        except Exception as e:
            log.error(f"Fullscreen capture failed: {e}")

    # -------------------------------------------------------------------
    # Last Region
    # -------------------------------------------------------------------

    def capture_last_region(self):
        if not config.LAST_REGION:
            self.capture_region()
            return
        self._capture_with_delay(self._do_last_region_capture)

    def _do_last_region_capture(self):
        try:
            parts = config.LAST_REGION.split(',')
            x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        except (ValueError, IndexError):
            self.capture_region()
            return
        try:
            from capture import CaptureManager
            full = CaptureManager.capture_fullscreen()
            if full:
                rect = QRect(x, y, w, h)
                cropped = CaptureManager.crop_image(full, rect)
                if cropped:
                    self._handle_capture(cropped)
        except Exception as e:
            log.error(f"Last region capture failed: {e}")

    # -------------------------------------------------------------------
    # OCR Capture
    # -------------------------------------------------------------------

    def capture_ocr(self):
        self._capture_with_delay(self._do_ocr_capture)

    def _do_ocr_capture(self):
        self._start_region_overlay("rectangle", ocr_mode=True)

    def _do_ocr(self, pixmap):
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
            log.error(f"OCR failed: {e}")
            QMessageBox.warning(
                None, "OCR Error",
                f"Could not extract text:\n\n{str(e)}"
            )

    # -------------------------------------------------------------------
    # Scrolling Capture
    # -------------------------------------------------------------------

    def capture_scrolling(self):
        try:
            from scrolling_capture import ScrollingCaptureDialog
            dlg = ScrollingCaptureDialog()
            if dlg.exec_() == QDialog.Accepted:
                result = dlg.get_result()
                if result and not result.isNull():
                    self._handle_capture(result)
        except Exception as e:
            log.error(f"Scrolling capture failed: {e}")

    # -------------------------------------------------------------------
    # Post-capture handling
    # -------------------------------------------------------------------

    def _handle_capture(self, pixmap):
        log.info(f"Capture received: {pixmap.width()}x{pixmap.height()} "
                 f"action={config.AFTER_CAPTURE_ACTION}")
        # Save to history
        try:
            from capture_history import save_to_history
            save_to_history(pixmap)
        except Exception as e:
            log.warning(f"Could not save to history: {e}")

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
        try:
            from editor import ImageEditor
            editor = ImageEditor(pixmap, self)
            editor.show()
            editor.raise_()
            editor.activateWindow()
            # On Windows, force foreground with Win32 API
            if sys.platform == 'win32':
                try:
                    import ctypes
                    hwnd = int(editor.winId())
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
            self.editors.append(editor)
            log.info("Editor opened successfully")
        except Exception as e:
            log.error(f"Could not open editor: {e}", exc_info=True)
            try:
                QMessageBox.critical(
                    None, "SwiftShot Error",
                    f"Could not open editor:\n\n{e}"
                )
            except Exception:
                pass

    def _save_directly(self, pixmap):
        try:
            filepath = config.get_filename()
            fmt = config.OUTPUT_FILE_FORMAT.upper()
            if fmt == "JPG":
                fmt = "JPEG"
            quality = config.OUTPUT_JPEG_QUALITY if fmt == "JPEG" else -1
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            success = pixmap.save(filepath, fmt, quality)
            if success:
                self.tray_icon.showMessage(
                    "SwiftShot", f"Screenshot saved to {filepath}",
                    QSystemTrayIcon.Information, 2000
                )
                if config.COPY_PATH_TO_CLIPBOARD:
                    QApplication.clipboard().setText(filepath)
                log.info(f"Screenshot saved: {filepath}")
        except Exception as e:
            log.error(f"Direct save failed: {e}")

    def _copy_to_clipboard(self, pixmap):
        QApplication.clipboard().setPixmap(pixmap)
        if config.SHOW_NOTIFICATIONS:
            self.tray_icon.showMessage(
                "SwiftShot", "Screenshot copied to clipboard",
                QSystemTrayIcon.Information, 1500
            )

    # -------------------------------------------------------------------
    # Pin to Desktop
    # -------------------------------------------------------------------

    def pin_pixmap(self, pixmap):
        """Pin a pixmap as an always-on-top window."""
        try:
            from pin_window import PinWindow
            pin = PinWindow(pixmap)
            pin.show()
            self._pin_windows.append(pin)
            pin.closed.connect(lambda pw: self._pin_windows.remove(pw)
                               if pw in self._pin_windows else None)
        except Exception as e:
            log.error(f"Pin failed: {e}")

    # -------------------------------------------------------------------
    # Capture History
    # -------------------------------------------------------------------

    def show_history(self):
        try:
            from capture_history import CaptureHistoryDialog
            if self._history_dialog and self._history_dialog.isVisible():
                self._history_dialog.raise_()
                return
            dlg = CaptureHistoryDialog()
            dlg.open_in_editor.connect(self._open_history_image)
            dlg.pin_to_desktop.connect(self._pin_history_image)
            dlg.show()
            self._history_dialog = dlg
        except Exception as e:
            log.error(f"History dialog failed: {e}")

    def _open_history_image(self, filepath):
        pixmap = QPixmap(filepath)
        if not pixmap.isNull():
            self._open_editor(pixmap)

    def _pin_history_image(self, filepath):
        pixmap = QPixmap(filepath)
        if not pixmap.isNull():
            self.pin_pixmap(pixmap)

    # -------------------------------------------------------------------
    # Clipboard Watcher
    # -------------------------------------------------------------------

    def _toggle_clipboard_watcher(self):
        self._clipboard_watcher_enabled = not self._clipboard_watcher_enabled
        config.CLIPBOARD_WATCHER_ENABLED = self._clipboard_watcher_enabled
        config.save()
        if self._clipboard_watcher_enabled:
            self._start_clipboard_watcher()
            self.tray_icon.showMessage(
                "SwiftShot", "Clipboard watcher enabled",
                QSystemTrayIcon.Information, 1500
            )
        else:
            self._stop_clipboard_watcher()
            self.tray_icon.showMessage(
                "SwiftShot", "Clipboard watcher disabled",
                QSystemTrayIcon.Information, 1500
            )

    def _start_clipboard_watcher(self):
        if self._clipboard_timer:
            return
        self._last_clipboard_pixmap = QApplication.clipboard().pixmap()
        self._clipboard_timer = QTimer()
        self._clipboard_timer.timeout.connect(self._check_clipboard)
        self._clipboard_timer.start(1000)
        log.info("Clipboard watcher started")

    def _stop_clipboard_watcher(self):
        if self._clipboard_timer:
            self._clipboard_timer.stop()
            self._clipboard_timer = None
            log.info("Clipboard watcher stopped")

    def _check_clipboard(self):
        try:
            pixmap = QApplication.clipboard().pixmap()
            if pixmap and not pixmap.isNull():
                if self._last_clipboard_pixmap is None or self._last_clipboard_pixmap.isNull():
                    self._last_clipboard_pixmap = pixmap
                    self._open_editor(pixmap)
                elif pixmap.size() != self._last_clipboard_pixmap.size():
                    self._last_clipboard_pixmap = pixmap
                    self._open_editor(pixmap)
        except Exception as e:
            log.warning(f"Clipboard check failed: {e}")

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
        try:
            from settings_dialog import SettingsDialog
            dialog = SettingsDialog()
            dialog.exec_()
        except Exception as e:
            log.error(f"Settings dialog failed: {e}")

    def show_about(self):
        QMessageBox.about(
            None, "About SwiftShot",
            f"<h2>SwiftShot v{config.APP_VERSION}</h2>"
            "<p>A comprehensive, debloated screenshot tool.</p>"
            "<p>Inspired by Greenshot - built without any 3rd-party "
            "integrations or plugin bloat.</p>"
            "<hr>"
            "<p><b>Capture:</b> Region / Freehand / Window / Fullscreen /<br>"
            "Per-monitor / Last Region / OCR / Scrolling Capture</p>"
            "<p><b>Editor:</b> Crop, shapes, arrows, text, highlight, obfuscate,<br>"
            "step numbers, ruler, eyedropper, border/shadow/rounded corners,<br>"
            "image diff overlay, quick-annotate templates, OCR,<br>"
            "drag-and-drop export, recent colors, font picker</p>"
            "<p><b>Extras:</b> Pin to desktop, capture history, clipboard watcher,<br>"
            "countdown timer, smart edge snapping, color picker, auto-update</p>"
            "<hr>"
            "<p>License: GPL-3.0</p>"
        )

    def editor_closed(self, editor):
        if editor in self.editors:
            self.editors.remove(editor)

    def exit_app(self):
        log.info("SwiftShot shutting down")
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
        self._stop_clipboard_watcher()
        # Close all pin windows
        for pin in list(self._pin_windows):
            try:
                pin.close()
            except Exception:
                pass
        if self.tray_icon:
            self.tray_icon.hide()
        config.save()
        QApplication.quit()
