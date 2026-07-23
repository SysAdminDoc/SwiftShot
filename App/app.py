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
from dataclasses import dataclass
from enum import Enum
from PyQt5.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QMessageBox, QDialog, QAction
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QTimer, QRect, QThread, pyqtSignal, QAbstractNativeEventFilter

from config import config
from logger import log
from ocr_dialog import OcrResultDialog
from safe_io import MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS, load_image
from utils import pil_to_qpixmap


class _SystemThemeFilter(QAbstractNativeEventFilter):
    """Watch for Windows app-theme changes (WM_SETTINGCHANGE / ImmersiveColorSet)
    and notify the app so a 'system' theme selection repaints live (R-32)."""

    WM_SETTINGCHANGE = 0x001A

    def __init__(self, on_change):
        super().__init__()
        self._on_change = on_change

    def nativeEventFilter(self, event_type, message):
        try:
            et = bytes(event_type) if not isinstance(event_type, bytes) else event_type
            if et == b"windows_generic_MSG":
                import ctypes
                from ctypes import wintypes
                msg = ctypes.cast(int(message),
                                  ctypes.POINTER(wintypes.MSG)).contents
                if msg.message == self.WM_SETTINGCHANGE and msg.lParam:
                    if ctypes.wstring_at(msg.lParam) == "ImmersiveColorSet":
                        self._on_change()
        except Exception:
            pass
        return False, 0


def _load_file_pixmap(path):
    return pil_to_qpixmap(load_image(path))


def _pixmap_within_safe_limits(pixmap):
    if pixmap is None or pixmap.isNull():
        return False
    width, height = pixmap.width(), pixmap.height()
    return (
        0 < width <= MAX_IMAGE_DIMENSION
        and 0 < height <= MAX_IMAGE_DIMENSION
        and width * height <= MAX_IMAGE_PIXELS
    )


class _NotificationActionKind(Enum):
    OPEN_UPDATE = "open_update"


@dataclass(frozen=True)
class _NotificationAction:
    kind: _NotificationActionKind
    callback: object


class _OcrWorker(QThread):
    """Run OCR off the GUI thread. The WinRT OCR PowerShell subprocess has a
    2-5 s cold start, so doing it synchronously froze the tray/editor on every
    capture (interactive OCR too). The pixmap is encoded to a temp file on the
    main thread first; only the subprocess runs here."""

    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, image_path, cleanup=False, parent=None):
        super().__init__(parent)
        self._path = image_path
        self._cleanup = cleanup

    def run(self):
        try:
            from ocr import ocr_file
            self.done.emit(ocr_file(self._path) or "")
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            if self._cleanup:
                try:
                    os.unlink(self._path)
                except OSError:
                    pass


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
        self._clipboard_watcher_connected = False
        self._last_clipboard_change = 0.0
        self._history_dialog = None
        self._capture_menu = None
        self._update_checker = None
        self._update_url = None
        self._update_action = None
        self._notification_action = None
        self._notification_generation = 0
        self._tray_menu = None
        self._exit_action = None
        self._ocr_workers = []      # keep async OCR threads alive until done
        self._capture_generation = 0
        self._capture_menu_generation = 0
        self._scrolling_dialog = None
        self._recovery_prompted = set()

    def start(self):
        # Set app-wide icon so every QWidget/QDialog inherits it
        app_icon = self._create_app_icon()
        self.app.setWindowIcon(app_icon)

        # Live OS-theme listener so a "system" theme selection follows Windows
        # dark/light changes without a restart (R-32).
        if sys.platform == 'win32':
            try:
                self._theme_filter = _SystemThemeFilter(self._on_system_theme_changed)
                self.app.installNativeEventFilter(self._theme_filter)
            except Exception:
                log.warning("Could not install system-theme listener", exc_info=True)

        self._create_tray_icon()
        hotkeys_ready = self._register_hotkeys()
        self.tray_icon.show()
        if not hotkeys_ready:
            self._notify(
                "Capture shortcuts unavailable",
                "SwiftShot could not register its global shortcuts. Use the "
                "tray menu for capture, then review shortcut conflicts in "
                "Preferences.",
                warning=True, required=True,
            )
        self._check_history_health()

        # Defer recovery discovery until the tray is live. Corrupt journals
        # are quarantined and valid documents are offered once per startup.
        QTimer.singleShot(0, self._offer_recovery_journals)

        self._notify(
            "SwiftShot",
            "SwiftShot is running. Press PrintScreen for the capture menu.",
            duration_ms=2000,
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

    def _check_history_health(self):
        """Run the bounded startup check and surface any recovery outcome."""
        try:
            from capture_history import ensure_history_health
            result = ensure_history_health(config.CAPTURE_HISTORY_DIR)
        except Exception:
            log.warning("Capture-history health check failed", exc_info=True)
            self._notify(
                "Capture history check failed",
                "History images were left untouched. See diagnostics for details.",
                warning=True,
            )
            return None
        status = result["status"]
        if status == "recovered":
            self._notify(
                "Capture history rebuilt",
                f"Recovered {result['recovered_file_count']} capture file(s). "
                "The damaged database was preserved in quarantine.",
            )
        elif status in ("recovery_failed", "check_unavailable", "check_timeout"):
            self._notify(
                "Capture history needs attention",
                "The database check could not complete; capture images were "
                "left untouched. Export diagnostics for details.",
                warning=True,
            )
        return result

    # -------------------------------------------------------------------
    # Editor crash recovery
    # -------------------------------------------------------------------

    def _build_recovery_prompt(self, entry):
        box = QMessageBox()
        box.setWindowTitle("Recover Unsaved SwiftShot Edit")
        box.setText(
            f"SwiftShot found an unsaved editor recovery.\n\n"
            f"Document: {entry.document_name}\n"
            f"Recovery time: {entry.saved_at}"
        )
        box.setInformativeText(
            "Restore opens an unsaved copy and never overwrites the original."
        )
        preview = QPixmap()
        if preview.loadFromData(entry.preview_png, "PNG"):
            box.setIconPixmap(preview.scaled(
                320, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))
        restore_button = box.addButton("Restore", QMessageBox.AcceptRole)
        discard_button = box.addButton("Discard", QMessageBox.DestructiveRole)
        box.addButton("Keep for Later", QMessageBox.RejectRole)
        box.setDefaultButton(restore_button)
        return box, restore_button, discard_button

    def _recovery_decision(self, entry):
        box, restore_button, discard_button = self._build_recovery_prompt(entry)
        box.exec_()
        if box.clickedButton() is restore_button:
            return "restore"
        if box.clickedButton() is discard_button:
            return "discard"
        return "later"

    def _restore_recovery_entry(self, entry):
        from editor import ImageEditor
        editor = ImageEditor(swiftshot_app=self)
        if not editor.restore_recovery(entry.path):
            editor._set_dirty(False)
            editor.close()
            return False
        self.editors.append(editor)
        editor.show()
        editor.raise_()
        editor.activateWindow()
        return True

    def _offer_recovery_journals(self):
        from recovery import discard_recovery, scan_recovery_journals
        entries, quarantined = scan_recovery_journals()
        if quarantined:
            log.warning("Quarantined %d corrupt recovery journal(s)",
                        len(quarantined))
            self._notify(
                "Recovery file quarantined",
                f"SwiftShot moved {len(quarantined)} corrupt recovery file(s) "
                "aside and continued startup.",
                warning=True,
            )
        for entry in entries:
            if entry.path in self._recovery_prompted:
                continue
            self._recovery_prompted.add(entry.path)
            decision = self._recovery_decision(entry)
            if decision == "restore":
                self._restore_recovery_entry(entry)
            elif decision == "discard" and not discard_recovery(entry.path):
                self._notify(
                    "Recovery discard failed",
                    "The recovery copy was retained so it can be retried.",
                    warning=True,
                )

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
        self._update_url = url
        self._notify(
            "SwiftShot update available",
            f"Version {version} is available. Select this notification to "
            "open the verified GitHub release page.",
            duration_ms=5000,
            action=_NotificationAction(
                _NotificationActionKind.OPEN_UPDATE,
                lambda target=url: webbrowser.open(target),
            ),
        )
        # Add a download entry to the tray menu so the update stays reachable
        # after the notification fades.
        if self._tray_menu and self._update_action is None:
            action = QAction(f"Download Update {version}...", self._tray_menu)
            action.triggered.connect(self._open_update_page)
            self._tray_menu.insertAction(self._exit_action, action)
            self._tray_menu.insertSeparator(self._exit_action)
            self._update_action = action

    def _open_update_page(self):
        if self._update_url:
            webbrowser.open(self._update_url)

    def _on_tray_message_clicked(self):
        action = self._notification_action
        self._notification_generation += 1
        self._notification_action = None
        if action is None:
            return
        try:
            action.callback()
        except Exception:
            log.warning(
                "Tray notification action failed: %s", action.kind.value,
                exc_info=True,
            )

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
        from theme import stylesheet_for_theme

        self.tray_icon = QSystemTrayIcon(self.app.windowIcon(), self.app)

        menu = QMenu()
        menu.setStyleSheet(stylesheet_for_theme(config.THEME))

        # Hotkey columns are refreshed from live config via
        # _refresh_tray_hotkey_labels — hardcoded shortcuts lie after a rebind.
        self._tray_hotkey_actions = {}
        act = menu.addAction("Capture Menu")
        act.triggered.connect(self.show_capture_menu)
        self._tray_hotkey_actions[("Capture Menu", "CAPTURE_REGION_HOTKEY")] = act
        menu.addSeparator()
        menu.addAction("Capture Region").triggered.connect(self.capture_region)
        act = menu.addAction("Capture Window")
        act.triggered.connect(self.capture_window)
        self._tray_hotkey_actions[("Capture Window", "CAPTURE_WINDOW_HOTKEY")] = act
        act = menu.addAction("Capture Full Screen")
        act.triggered.connect(self.capture_fullscreen)
        self._tray_hotkey_actions[("Capture Full Screen", "CAPTURE_FULLSCREEN_HOTKEY")] = act
        act = menu.addAction("Capture Last Region")
        act.triggered.connect(self.capture_last_region)
        self._tray_hotkey_actions[("Capture Last Region", "CAPTURE_LAST_REGION_HOTKEY")] = act
        menu.addSeparator()
        act = menu.addAction("Region (Freehand)")
        act.triggered.connect(self.capture_freehand)
        self._tray_hotkey_actions[("Region (Freehand)", "CAPTURE_FREEHAND_HOTKEY")] = act
        act = menu.addAction("OCR Region")
        act.triggered.connect(self.capture_ocr)
        self._tray_hotkey_actions[("OCR Region", "CAPTURE_OCR_HOTKEY")] = act
        act = menu.addAction("Scrolling Capture...")
        act.triggered.connect(self.capture_scrolling)
        self._tray_hotkey_actions[("Scrolling Capture...", "CAPTURE_SCROLLING_HOTKEY")] = act
        self._refresh_tray_hotkey_labels()
        menu.addSeparator()
        menu.addAction("Open Image from File...").triggered.connect(self.open_from_file)
        menu.addAction("Open Image from Clipboard").triggered.connect(self.open_from_clipboard)
        menu.addSeparator()
        menu.addAction("Capture History...").triggered.connect(self.show_history)
        menu.addSeparator()
        menu.addAction("Preferences...").triggered.connect(self.show_settings)
        menu.addSeparator()
        menu.addAction("About SwiftShot").triggered.connect(self.show_about)
        menu.addAction("Export Diagnostics...").triggered.connect(self.export_diagnostics)
        menu.addSeparator()
        self._exit_action = menu.addAction("Exit")
        self._exit_action.triggered.connect(self.exit_app)

        self._tray_menu = menu
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.setToolTip("SwiftShot - Screenshot Tool")
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)

    def export_diagnostics(self):
        """Preview and write a privacy-sanitized local support bundle."""
        try:
            from diagnostics import (
                build_diagnostics_zip,
                diagnostics_preview,
                format_diagnostics_preview,
            )
            reply = QMessageBox.question(
                None,
                "Export Privacy-Safe Diagnostics",
                format_diagnostics_preview(diagnostics_preview()),
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Yes:
                return
            path = build_diagnostics_zip()
            log.info(f"Diagnostics bundle written: {path}")
            self._notify("Diagnostics saved", f"Saved {os.path.basename(path)}")
            try:
                if os.name == "nt":
                    os.startfile(os.path.dirname(path))   # reveal in Explorer
            except Exception:
                pass
        except Exception as e:
            log.error(f"Diagnostics export failed: {e}", exc_info=True)
            self._notify(
                "Diagnostics export failed",
                "SwiftShot could not create the support bundle. Verify the "
                "destination folder and try again.",
                warning=True, required=True)

    def _refresh_tray_hotkey_labels(self):
        """Sync tray-menu shortcut columns with the configured hotkeys."""
        from utils import hotkey_suffix
        for (base, key), action in getattr(self, "_tray_hotkey_actions", {}).items():
            action.setText(base + hotkey_suffix(getattr(config, key, "")))

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_capture_menu()

    # -------------------------------------------------------------------
    # Hotkeys
    # -------------------------------------------------------------------

    def _register_hotkeys(self):
        if sys.platform != 'win32':
            return True
        listener = None
        try:
            from hotkeys import HotkeyManager
            listener = HotkeyManager()
            self._hotkey_listener = listener

            bindings = (
                ("Capture menu", config.CAPTURE_REGION_HOTKEY,
                 self.show_capture_menu),
                ("Window capture", config.CAPTURE_WINDOW_HOTKEY,
                 self.capture_window),
                ("Fullscreen capture", config.CAPTURE_FULLSCREEN_HOTKEY,
                 self.capture_fullscreen),
                ("Last region", config.CAPTURE_LAST_REGION_HOTKEY,
                 self.capture_last_region),
                ("OCR", config.CAPTURE_OCR_HOTKEY, self.capture_ocr),
                ("Freehand capture", config.CAPTURE_FREEHAND_HOTKEY,
                 self.capture_freehand),
                ("Scrolling capture", config.CAPTURE_SCROLLING_HOTKEY,
                 self.capture_scrolling),
                ("Color picker", config.CAPTURE_COLOR_PICKER_HOTKEY,
                 self.pick_color),
            )
            for label, combo, callback in bindings:
                if combo and not listener.register(combo, callback):
                    raise ValueError(f"{label} shortcut is invalid or duplicated")

            if not self._hotkey_listener.start():
                raise OSError("Windows did not install the keyboard hook")
            log.info("Hotkeys registered successfully")
            return True
        except Exception as e:
            log.warning(f"Could not register hotkeys: {e}")
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
            self._hotkey_listener = None
            return False

    def _reregister_hotkeys(self):
        """Tear down and rebuild the global hotkey hook (live rebinding)."""
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
            self._hotkey_listener = None
        return self._register_hotkeys()

    # -------------------------------------------------------------------
    # Capture Delay Helper
    # -------------------------------------------------------------------

    def _supersede_countdown(self):
        """Cancel any in-flight countdown before starting a new one. The single
        self._countdown slot holds the only reference, so overwriting it would
        GC the widget mid-count and its capture would never fire, silently."""
        prev = getattr(self, "_countdown", None)
        if prev is not None:
            try:
                log.info("Superseding an in-flight countdown with a new capture")
                prev._cancel()
            except Exception:
                pass
            self._countdown = None

    def _capture_is_current(self, generation):
        return generation == self._capture_generation

    def _begin_capture_operation(self):
        """Supersede capture UI/input and return the new operation token."""
        self._capture_generation += 1
        self._supersede_countdown()
        self._close_overlay()
        self._close_window_picker()
        scrolling = self._scrolling_dialog
        if scrolling is not None:
            try:
                scrolling.reject()
            except Exception:
                pass
            self._scrolling_dialog = None
        return self._capture_generation

    def _cancel_capture(self, generation, overlay=None):
        """Invalidate callbacks owned by one capture without cancelling newer work."""
        if not self._capture_is_current(generation):
            return
        if overlay is not None and getattr(self, "_countdown", None) is overlay:
            self._countdown = None
        self._capture_generation += 1

    def _run_capture_callback(self, generation, callback):
        if self._capture_is_current(generation):
            callback()

    def _capture_with_delay(self, callback):
        """Execute callback after configured delay (with countdown if >0)."""
        generation = self._begin_capture_operation()
        delay = config.CAPTURE_DELAY_MS
        if delay > 0:
            try:
                from countdown_overlay import CountdownOverlay
                overlay = CountdownOverlay(delay)
                overlay.countdown_finished.connect(
                    lambda g=generation, cb=callback:
                        self._run_capture_callback(g, cb)
                )
                overlay.cancelled.connect(
                    lambda g=generation, o=overlay: self._cancel_capture(g, o)
                )
                self._countdown = overlay  # prevent GC
                overlay.start()
            except Exception as e:
                log.error(f"Countdown overlay failed: {e}")
                QTimer.singleShot(
                    100,
                    lambda g=generation, cb=callback:
                        self._run_capture_callback(g, cb),
                )
        else:
            QTimer.singleShot(
                100,
                lambda g=generation, cb=callback:
                    self._run_capture_callback(g, cb),
            )

    # -------------------------------------------------------------------
    # Capture Menu (PrintScreen popup)
    # -------------------------------------------------------------------

    def show_capture_menu(self):
        self._capture_menu_generation += 1
        generation = self._capture_menu_generation
        QTimer.singleShot(
            50, lambda: self._do_show_capture_menu(generation)
        )

    def _do_show_capture_menu(self, generation=None):
        if (generation is not None
                and generation != self._capture_menu_generation):
            return
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
            self._capture_failed(
                "SwiftShot could not open the capture menu. Try a direct "
                "capture hotkey or restart SwiftShot.")

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
                self._capture_failed(
                    "SwiftShot could not read the selected monitor. Verify "
                    "that the display is connected, then try again.")
        except Exception as e:
            log.error(f"Monitor capture failed: {e}", exc_info=True)
            self._capture_failed(
                "SwiftShot could not capture the selected monitor. Verify "
                "the display connection and try again.")

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
                self._capture_failed(
                    "SwiftShot could not read the desktop. Verify that the "
                    "screens are connected and try again.")
                return

            self._overlay = RegionSelector(full, mode=mode)
            overlay = self._overlay
            generation = self._capture_generation
            self._overlay._ocr_mode = ocr_mode
            self._overlay._full_screenshot = full
            self._overlay.region_selected.connect(
                lambda rect, g=generation, o=overlay:
                    self._on_region_selected(full, rect, ocr_mode, g, o)
            )
            self._overlay.freehand_selected.connect(
                lambda data, g=generation, o=overlay:
                    self._on_freehand_selected(full, data, g, o)
            )
            self._overlay.switch_to_window.connect(
                lambda g=generation, o=overlay:
                    self._switch_to_window_mode(full, g, o)
            )
            self._overlay.cancelled.connect(
                lambda g=generation, o=overlay:
                    self._cancel_region_overlay(g, o)
            )
            self._overlay.show_spanning()
        except Exception as e:
            log.error(f"Region overlay failed: {e}")
            self._capture_failed(
                "SwiftShot could not start region selection. Try again or "
                "restart SwiftShot.")

    def _on_region_selected(self, full_screenshot, rect, ocr_mode=False,
                            generation=None, overlay=None):
        generation = (self._capture_generation if generation is None
                      else generation)
        if not self._capture_is_current(generation):
            if overlay is not None:
                overlay.close()
            return
        self._close_overlay(overlay)
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
                else:
                    self._capture_failed(
                        "The selected OCR region is outside the available "
                        "desktop. Select the region again.")
            except Exception as e:
                log.error(f"OCR crop failed: {e}")
                self._capture_failed(
                    "SwiftShot could not prepare the selected region for OCR. "
                    "Select the region again.")
            return

        # Check if timed capture is active
        if config.CAPTURE_TIMER_ENABLED and config.CAPTURE_TIMER_SECONDS > 0:
            self._timed_capture_region(rect, generation=generation)
        else:
            # Immediate capture from the already-taken screenshot
            try:
                from capture import CaptureManager
                cropped = CaptureManager.crop_image(full_screenshot, rect)
                if cropped:
                    self._handle_capture(cropped)
                else:
                    self._capture_failed(
                        "The selected region is outside the available desktop. "
                        "Select the region again.")
            except Exception as e:
                log.error(f"Region selection failed: {e}")
                self._capture_failed(
                    "SwiftShot could not create the selected region. Select "
                    "the region again.")

    def _on_freehand_selected(self, full_screenshot, data, generation=None,
                              overlay=None):
        """Crop to the freehand bounding rect, then mask outside the drawn
        shape to transparent so the capture matches what was drawn."""
        generation = (self._capture_generation if generation is None
                      else generation)
        if not self._capture_is_current(generation):
            if overlay is not None:
                overlay.close()
            return
        self._close_overlay(overlay)
        try:
            points, rect = data
            rect = QRect(rect)
        except Exception:
            return
        if rect.width() < 1 or rect.height() < 1:
            return

        config.LAST_REGION = f"{rect.x()},{rect.y()},{rect.width()},{rect.height()}"
        config.save()

        if config.CAPTURE_TIMER_ENABLED and config.CAPTURE_TIMER_SECONDS > 0:
            self._timed_capture_region(rect, points, generation)
            return
        try:
            from capture import CaptureManager
            from utils import apply_freehand_mask
            cropped = CaptureManager.crop_image(full_screenshot, rect)
            if cropped:
                self._handle_capture(
                    apply_freehand_mask(cropped, points, rect), preserve_alpha=True)
            else:
                self._capture_failed(
                    "The freehand region is outside the available desktop. "
                    "Draw the region again.")
        except Exception as e:
            log.error(f"Freehand selection failed: {e}")
            self._capture_failed(
                "SwiftShot could not create the freehand capture. Draw the "
                "region again.")

    def _close_overlay(self, expected=None):
        if expected is not None and self._overlay is not expected:
            try:
                expected.close()
            except Exception:
                pass
            return
        if self._overlay:
            try:
                self._overlay.hide()
                self._overlay.close()
            except Exception:
                pass
            self._overlay = None

    def _cancel_region_overlay(self, generation, overlay):
        self._close_overlay(overlay)
        self._cancel_capture(generation)

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
                self._capture_failed(
                    "SwiftShot could not read the desktop for window capture. "
                    "Try again or use region capture.")
                return
            self._start_window_picker(full)
        except Exception as e:
            log.error(f"Window capture failed: {e}")
            self._capture_failed(
                "SwiftShot could not read the desktop for window capture. "
                "Try again or use region capture.")

    def _start_window_picker(self, full_screenshot):
        try:
            from window_picker import WindowPicker
            self._close_window_picker()
            self._window_picker = WindowPicker(full_screenshot)
            picker = self._window_picker
            generation = self._capture_generation
            self._window_picker._full_screenshot = full_screenshot
            self._window_picker.element_selected.connect(
                lambda rect, g=generation, p=picker:
                    self._on_window_selected(full_screenshot, rect, g, p)
            )
            self._window_picker.switch_to_region.connect(
                lambda g=generation, p=picker:
                    self._switch_to_region_mode(full_screenshot, g, p)
            )
            self._window_picker.cancelled.connect(
                lambda g=generation, p=picker:
                    self._cancel_window_picker(g, p)
            )
            self._window_picker.show_spanning()
        except Exception as e:
            log.error(f"Window picker failed: {e}")
            self._capture_failed(
                "SwiftShot could not start window selection. Try again or use "
                "region capture.")

    def _on_window_selected(self, full_screenshot, rect, generation=None,
                            picker=None):
        generation = (self._capture_generation if generation is None
                      else generation)
        if not self._capture_is_current(generation):
            if picker is not None:
                picker.close()
            return
        self._close_window_picker(picker)
        if rect.width() < 1 or rect.height() < 1:
            return

        # Check if timed capture is active
        if config.CAPTURE_TIMER_ENABLED and config.CAPTURE_TIMER_SECONDS > 0:
            self._timed_capture_region(rect, generation=generation)
        else:
            try:
                from capture import CaptureManager
                cropped = CaptureManager.crop_image(full_screenshot, rect)
                if cropped:
                    self._handle_capture(cropped)
                else:
                    self._capture_failed(
                        "The selected window is outside the available desktop. "
                        "Select the window again.")
            except Exception as e:
                log.error(f"Window selection failed: {e}")
                self._capture_failed(
                    "SwiftShot could not create the selected window capture. "
                    "Select the window again.")

    def _close_window_picker(self, expected=None):
        if expected is not None and self._window_picker is not expected:
            try:
                expected.close()
            except Exception:
                pass
            return
        if self._window_picker:
            try:
                self._window_picker.hide()
                self._window_picker.close()
            except Exception:
                pass
            self._window_picker = None

    def _cancel_window_picker(self, generation, picker):
        self._close_window_picker(picker)
        self._cancel_capture(generation)

    # -------------------------------------------------------------------
    # Timed Capture
    # -------------------------------------------------------------------

    def _timed_capture_region(self, rect, freehand_points=None,
                              generation=None):
        """
        Timed capture flow:
        1. User already selected a region/window (overlay is closed)
        2. Show countdown overlay so user can interact with the screen
        3. When countdown ends, take a FRESH screenshot and crop to rect
        """
        generation = (self._capture_generation if generation is None
                      else generation)
        if not self._capture_is_current(generation):
            return
        seconds = config.CAPTURE_TIMER_SECONDS
        total_ms = seconds * 1000
        log.info(f"Timed capture: {seconds}s countdown for region {rect.x()},{rect.y()} "
                 f"{rect.width()}x{rect.height()}")

        try:
            from countdown_overlay import CountdownOverlay
            self._supersede_countdown()
            overlay = CountdownOverlay(total_ms)
            overlay.countdown_finished.connect(
                lambda r=QRect(rect), g=generation:
                    self._timed_capture_fire(r, freehand_points, g)
            )
            overlay.cancelled.connect(
                lambda g=generation, o=overlay: self._cancel_capture(g, o)
            )
            self._countdown = overlay  # prevent GC
            overlay.start()
        except Exception as e:
            log.error(f"Timed capture countdown failed: {e}")
            # Fall back to immediate capture
            self._timed_capture_fire(rect, freehand_points, generation)

    def _timed_capture_fire(self, rect, freehand_points=None, generation=None):
        """Take a fresh screenshot and crop to the saved region."""
        generation = (self._capture_generation if generation is None
                      else generation)
        if not self._capture_is_current(generation):
            return
        self._countdown = None
        try:
            from capture import CaptureManager
            fresh = CaptureManager.capture_fullscreen()
            if fresh:
                cropped = CaptureManager.crop_image(fresh, rect)
                if cropped:
                    if freehand_points:
                        from utils import apply_freehand_mask
                        cropped = apply_freehand_mask(
                            cropped, freehand_points, rect)
                    log.info("Timed capture completed")
                    self._handle_capture(cropped, preserve_alpha=bool(freehand_points))
                else:
                    log.warning("Timed capture: crop returned None")
                    self._capture_failed(
                        "The saved timed-capture region is no longer available. "
                        "Select the region again.")
            else:
                log.warning("Timed capture: fresh screenshot returned None")
                self._capture_failed(
                    "SwiftShot could not refresh the screen after the countdown. "
                    "Try the timed capture again.")
        except Exception as e:
            log.error(f"Timed capture fire failed: {e}")
            self._capture_failed(
                "SwiftShot could not finish the timed capture. Select the "
                "region and try again.")

    # -------------------------------------------------------------------
    # Space Toggle: Region <-> Window
    # -------------------------------------------------------------------

    def _switch_to_window_mode(self, full_screenshot, generation=None,
                               overlay=None):
        generation = (self._capture_generation if generation is None
                      else generation)
        if not self._capture_is_current(generation):
            return
        self._close_overlay(overlay)
        QTimer.singleShot(
            50,
            lambda g=generation: self._run_capture_callback(
                g, lambda: self._start_window_picker(full_screenshot)
            ),
        )

    def _switch_to_region_mode(self, full_screenshot, generation=None,
                               picker=None):
        generation = (self._capture_generation if generation is None
                      else generation)
        if not self._capture_is_current(generation):
            return
        self._close_window_picker(picker)
        try:
            from overlay import RegionSelector
            self._overlay = RegionSelector(full_screenshot, mode="rectangle")
            overlay = self._overlay
            self._overlay._full_screenshot = full_screenshot
            self._overlay.region_selected.connect(
                lambda rect, g=generation, o=overlay:
                    self._on_region_selected(
                        full_screenshot, rect, False, g, o
                    )
            )
            self._overlay.switch_to_window.connect(
                lambda g=generation, o=overlay:
                    self._switch_to_window_mode(full_screenshot, g, o)
            )
            self._overlay.cancelled.connect(
                lambda g=generation, o=overlay:
                    self._cancel_region_overlay(g, o)
            )
            QTimer.singleShot(
                50,
                lambda g=generation, o=overlay:
                    self._run_capture_callback(g, o.show_spanning),
            )
        except Exception as e:
            log.error(f"Switch to region mode failed: {e}")
            self._capture_failed(
                "SwiftShot could not switch capture modes. Start a new region "
                "capture and try again.")

    # -------------------------------------------------------------------
    # Fullscreen / Monitor Capture
    # -------------------------------------------------------------------

    def capture_fullscreen(self):
        self._capture_with_delay(self._do_fullscreen_capture)

    def _do_fullscreen_capture(self):
        try:
            generation = self._capture_generation
            screens = QApplication.screens()
            if len(screens) > 1:
                from monitor_picker import MonitorPicker
                from PyQt5.QtWidgets import QDialog
                picker = MonitorPicker()
                # Capture only after the dialog is closed AND has had a paint
                # cycle to leave the screen — capturing from the selection
                # signal grabbed the picker itself into the screenshot.
                if picker.exec_() == QDialog.Accepted:
                    idx = picker.selected_index()
                    QTimer.singleShot(
                        150,
                        lambda g=generation: self._run_capture_callback(
                            g, lambda: self._do_capture_monitor(idx)
                        ),
                    )
                else:
                    self._cancel_capture(generation)
            else:
                from capture import CaptureManager
                screenshot = CaptureManager.capture_fullscreen()
                if screenshot:
                    self._handle_capture(screenshot)
                else:
                    self._capture_failed(
                        "SwiftShot could not read the desktop. Verify that the "
                        "screen is available and try again.")
        except Exception as e:
            log.error(f"Fullscreen capture failed: {e}")
            self._capture_failed(
                "SwiftShot could not capture the desktop. Verify that the "
                "screens are connected and try again.")

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
                else:
                    self._capture_failed(
                        "The previous capture region is outside the current "
                        "desktop. Select a new region.")
            else:
                self._capture_failed(
                    "SwiftShot could not read the desktop. Select a new region "
                    "and try again.")
        except Exception as e:
            log.error(f"Last region capture failed: {e}")
            self._capture_failed(
                "SwiftShot could not recapture the previous region. Select a "
                "new region and try again.")

    # -------------------------------------------------------------------
    # OCR Capture
    # -------------------------------------------------------------------

    def capture_ocr(self):
        self._capture_with_delay(self._do_ocr_capture)

    def _notify(self, title, message, warning=False, duration_ms=3000,
                action=None, required=False):
        """Route one tray message and its optional one-shot click action.

        QSystemTrayIcon exposes one global ``messageClicked`` signal, not the
        message that was clicked. Every new message therefore clears the old
        action, and an action also expires shortly after its balloon. Required
        failures use a dialog when tray notifications are disabled so a save
        or capture failure never becomes silent.
        """
        self._notification_generation += 1
        generation = self._notification_generation
        self._notification_action = None

        if not config.SHOW_NOTIFICATIONS or not self.tray_icon:
            if required:
                QMessageBox.warning(None, title, message)
            return False

        if action is not None:
            if not isinstance(action, _NotificationAction):
                raise TypeError("notification action must be _NotificationAction")
            self._notification_action = action
            QTimer.singleShot(
                max(0, int(duration_ms)) + 1000,
                lambda current=generation:
                    self._expire_notification_action(current),
            )
        icon = QSystemTrayIcon.Warning if warning else QSystemTrayIcon.Information
        self.tray_icon.showMessage(
            title, message, icon, max(0, int(duration_ms)))
        return True

    def _expire_notification_action(self, generation):
        if generation == self._notification_generation:
            self._notification_generation += 1
            self._notification_action = None

    def _capture_failed(self, message):
        self._notify(
            "Capture failed", message,
            warning=True, duration_ms=4000, required=True)

    def pick_color(self):
        """Global color picker: copy the pixel under the cursor as hex."""
        try:
            from PyQt5.QtGui import QCursor
            pos = QCursor.pos()
            screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
            if screen is None:
                self._notify(
                    "Color picker unavailable",
                    "SwiftShot could not find an active screen. Reconnect the "
                    "display and try again.",
                    warning=True, required=True)
                return
            img = screen.grabWindow(0, pos.x(), pos.y(), 1, 1).toImage()
            hexs = img.pixelColor(0, 0).name().upper()
            QApplication.clipboard().setText(hexs)
            self._notify(
                "Color copied", f"{hexs} copied to the clipboard.",
                duration_ms=2000)
        except Exception as e:
            log.error(f"Color picker failed: {e}")
            self._notify(
                "Color picker failed",
                "SwiftShot could not read the pixel under the pointer. Try "
                "again on a visible screen.",
                warning=True, required=True)

    def _do_ocr_capture(self):
        self._start_region_overlay("rectangle", ocr_mode=True)

    def _spawn_ocr_worker(self, image_path, cleanup, on_done, on_failed=None):
        """Start an OCR worker, keeping a reference so it isn't GC'd mid-run."""
        worker = _OcrWorker(image_path, cleanup=cleanup, parent=self)
        worker.done.connect(on_done)
        if on_failed:
            worker.failed.connect(on_failed)
        worker.finished.connect(
            lambda w=worker: self._ocr_workers.remove(w)
            if w in self._ocr_workers else None)
        self._ocr_workers.append(worker)
        worker.start()

    def _do_ocr(self, pixmap):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp_path = tmp.name; tmp.close()
        try:
            if not pixmap.save(tmp_path, 'PNG'):
                raise OSError("Qt could not encode the OCR image as PNG")
        except Exception as e:
            log.error(f"OCR image save failed: {e}")
            try: os.unlink(tmp_path)
            except OSError: pass
            self._notify(
                "OCR could not start",
                "SwiftShot could not prepare the selected image for OCR. "
                "Select the region and try again.",
                warning=True, required=True)
            return
        self._spawn_ocr_worker(
            tmp_path, cleanup=True,
            on_done=self._on_ocr_done, on_failed=self._on_ocr_failed)

    def _on_ocr_done(self, text):
        if text:
            # The result dialog owns auto-copy and keeps the extracted text
            # recoverable even when the Windows clipboard is temporarily busy.
            OcrResultDialog(text).exec_()
        else:
            self._notify(
                "No text found",
                "No readable text was detected in the selected region.",
                warning=True)

    def _on_ocr_failed(self, message):
        log.error(f"OCR failed: {message}")
        QMessageBox.warning(
            None, "OCR Error", f"Could not extract text:\n\n{message}")

    # -------------------------------------------------------------------
    # Scrolling Capture
    # -------------------------------------------------------------------

    def capture_scrolling(self):
        generation = self._begin_capture_operation()
        try:
            from scrolling_capture import ScrollingCaptureDialog
            dlg = ScrollingCaptureDialog()
            self._scrolling_dialog = dlg
            outcome = dlg.exec_()
            if (self._scrolling_dialog is dlg
                    and self._capture_is_current(generation)):
                self._scrolling_dialog = None
            if (outcome == QDialog.Accepted
                    and self._capture_is_current(generation)):
                result = dlg.get_result()
                if result and not result.isNull():
                    self._handle_capture(result)
                    if dlg.was_truncated():
                        self._notify(
                            "Scrolling capture size limited",
                            "SwiftShot captured the page up to its safe image "
                            "size limit. Capture the remaining section "
                            "separately if needed.",
                            warning=True,
                        )
                else:
                    self._capture_failed(
                        "The scrolling capture did not produce an image. Keep "
                        "the target window visible and try again.")
        except Exception as e:
            log.error(f"Scrolling capture failed: {e}")
            self._capture_failed(
                "SwiftShot could not complete the scrolling capture. Keep the "
                "target window visible and try again.")

    # -------------------------------------------------------------------
    # Post-capture handling
    # -------------------------------------------------------------------

    def _handle_capture(self, pixmap, preserve_alpha=False):
        if not _pixmap_within_safe_limits(pixmap):
            self._capture_failed(
                "The capture is empty or exceeds SwiftShot's safe image "
                "limits. Capture a smaller area and try again."
            )
            return
        if config.PLAY_CAMERA_SOUND:
            try:
                from utils import play_camera_sound
                play_camera_sound()
            except Exception:
                pass
        # Beautify/frame draw a rectangular background+border over the whole
        # bounding box; on a freehand (transparent-outside) capture that would
        # fill in the shape and erase the drawn outline. Skip them there.
        if not preserve_alpha:
            pixmap = self._apply_beautification(pixmap)
            pixmap = self._apply_frame(pixmap)
            pixmap = self._apply_backdrop(pixmap)
        actions = config.get_after_capture_actions()
        log.info(f"Capture received: {pixmap.width()}x{pixmap.height()} "
                 f"actions={actions}")
        # Save to history immediately with no OCR text; if auto-OCR is on, run
        # it asynchronously and UPDATE the row when it finishes so the slow
        # WinRT subprocess never blocks the capture.
        try:
            from capture_history import save_to_history
            saved_path = save_to_history(pixmap, "")
            if saved_path and config.CAPTURE_HISTORY_AUTO_OCR:
                self._start_history_ocr(saved_path)
            elif config.CAPTURE_HISTORY_ENABLED and not saved_path:
                self._notify(
                    "Capture not added to history",
                    "The capture is still available in its selected workflow "
                    "destinations, but SwiftShot could not save the history "
                    "copy. Verify the history folder and export diagnostics "
                    "if the problem continues.",
                    warning=True, required=True)
        except Exception as e:
            log.warning(f"Could not save to history: {e}")
            self._notify(
                "Capture not added to history",
                "The capture is still available in its selected workflow "
                "destinations. Verify the history folder and try again.",
                warning=True, required=True)

        for action in actions:
            if action == "editor":
                self._open_editor(pixmap)
            elif action == "save":
                self._save_directly(pixmap)
            elif action == "clipboard":
                self._copy_to_clipboard(pixmap)

    def _apply_beautification(self, pixmap):
        if config.BEAUTIFY_PRESET == "none":
            return pixmap
        try:
            from utils import apply_beautification_preset
            return apply_beautification_preset(pixmap, config.BEAUTIFY_PRESET)
        except Exception as e:
            log.warning(f"Could not apply beautification preset: {e}")
            return pixmap

    def _apply_frame(self, pixmap):
        try:
            from utils import apply_frame
            return apply_frame(pixmap)
        except Exception as e:
            log.warning(f"Could not apply frame: {e}")
            return pixmap

    def _apply_backdrop(self, pixmap):
        try:
            from utils import apply_backdrop
            return apply_backdrop(pixmap)
        except Exception as e:
            log.warning(f"Could not apply backdrop: {e}")
            return pixmap

    def _start_history_ocr(self, filepath):
        """Run OCR on a saved history file in the background and write the
        result back to its row (the file already exists, so no cleanup)."""
        def _done(text, fp=filepath):
            from capture_history import update_history_ocr
            update_history_ocr(config.CAPTURE_HISTORY_DIR, fp, text)
        self._spawn_ocr_worker(
            filepath, cleanup=False, on_done=_done,
            on_failed=lambda msg: log.warning(f"History OCR failed: {msg}"))

    def open_image_file(self, path):
        """Open an image file in the editor (file-association / CLI entry)."""
        try:
            px = _load_file_pixmap(path)
        except Exception as error:
            log.warning(f"Could not load image file {path}: {error}")
            self._notify(
                "Image could not be opened",
                "The file is missing, unsupported, damaged, or exceeds the "
                "safe image limits.",
                warning=True, required=True)
            return
        if px.isNull():
            log.warning(f"Could not load image file: {path}")
            self._notify(
                "Image could not be opened",
                "The file did not contain a readable image.",
                warning=True, required=True)
            return
        log.info(f"Opening image file in editor: {path}")
        self._open_editor(px)

    def _open_editor(self, pixmap):
        if not _pixmap_within_safe_limits(pixmap):
            self._notify(
                "Image could not be opened",
                "The clipboard or capture image is empty or exceeds "
                "SwiftShot's safe image limits. Try a smaller image.",
                warning=True, required=True,
            )
            return False
        try:
            from editor import ImageEditor
            # Reuse an existing editor window if the user asked for it --
            # but only one without unsaved changes, never discarding work.
            if config.EDITOR_REUSE_EDITOR:
                for existing in reversed(self.editors):
                    try:
                        if existing.isVisible() and not getattr(existing, "_dirty", False):
                            existing.load_pixmap(pixmap)
                            existing.show()
                            existing.raise_()
                            existing.activateWindow()
                            log.info("Capture loaded into existing editor")
                            return True
                    except Exception:
                        continue
            editor = ImageEditor(pixmap, self)
            editor.show()
            editor.raise_()
            editor.activateWindow()
            # On Windows, force foreground with Win32 API
            if sys.platform == 'win32':
                try:
                    import ctypes
                    from ctypes import wintypes
                    hwnd = int(editor.winId())
                    set_foreground = ctypes.windll.user32.SetForegroundWindow
                    set_foreground.argtypes = [wintypes.HWND]
                    set_foreground.restype = wintypes.BOOL
                    set_foreground(wintypes.HWND(hwnd))
                except Exception:
                    pass
            self.editors.append(editor)
            log.info("Editor opened successfully")
            return True
        except Exception as e:
            log.error(f"Could not open editor: {e}", exc_info=True)
            try:
                QMessageBox.critical(
                    None, "SwiftShot Error",
                    f"Could not open editor:\n\n{e}"
                )
            except Exception:
                pass
            return False

    def _save_directly(self, pixmap):
        try:
            from utils import get_foreground_window_metadata, save_pixmap

            filepath = config.get_filename(
                width=pixmap.width(),
                height=pixmap.height(),
                **get_foreground_window_metadata(),
            )
            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
            success = save_pixmap(
                pixmap,
                filepath,
                config.OUTPUT_FILE_FORMAT,
                config.OUTPUT_JPEG_QUALITY,
            )
            if success:
                if config.COPY_PATH_TO_CLIPBOARD:
                    try:
                        QApplication.clipboard().setText(filepath)
                    except Exception:
                        log.warning("Saved screenshot path was not copied",
                                    exc_info=True)
                        self._notify(
                            "Screenshot saved; path not copied",
                            f"Saved to {filepath}, but Windows did not accept "
                            "the file path on the clipboard.",
                            warning=True, required=True,
                        )
                    else:
                        self._notify(
                            "Screenshot saved", f"Saved to {filepath}",
                            duration_ms=2000)
                else:
                    self._notify(
                        "Screenshot saved", f"Saved to {filepath}",
                        duration_ms=2000)
                log.info(f"Screenshot saved: {filepath}")
            else:
                log.error(f"Direct save failed: {filepath}")
                self._notify(
                    "Screenshot not saved",
                    f"SwiftShot could not write {filepath}. Check that the "
                    "folder exists and is writable, then try again.",
                    warning=True, duration_ms=4000, required=True)
        except Exception as e:
            log.error(f"Direct save failed: {e}", exc_info=True)
            self._notify(
                "Screenshot not saved",
                "SwiftShot could not save the screenshot. Verify the output "
                "folder and filename settings, then try again.",
                warning=True, duration_ms=4000, required=True)

    def _copy_to_clipboard(self, pixmap):
        try:
            QApplication.clipboard().setPixmap(pixmap)
            self._notify(
                "Screenshot copied", "The screenshot is ready to paste.",
                duration_ms=1500)
        except Exception:
            log.warning("Could not copy screenshot to the clipboard",
                        exc_info=True)
            self._notify(
                "Screenshot not copied",
                "Windows did not accept the clipboard image. The capture is "
                "still available in any other selected destinations; try "
                "copying it again from the editor or history.",
                warning=True, required=True,
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
            log.error(f"Pin failed: {e}", exc_info=True)
            self._notify(
                "Pin failed",
                "SwiftShot could not create the pinned window. The capture "
                "is still available in its other selected destinations.",
                warning=True, required=True)

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
            log.error(f"History dialog failed: {e}", exc_info=True)
            self._notify(
                "Capture history unavailable",
                "SwiftShot could not open capture history. Export diagnostics "
                "for details and try again.",
                warning=True, required=True)

    def _open_history_image(self, filepath):
        try:
            self._open_editor(_load_file_pixmap(filepath))
        except Exception as error:
            log.warning(f"Could not open history image {filepath}: {error}")
            self._notify(
                "Capture could not be opened",
                "The history image is missing, locked, or unreadable. Refresh "
                "capture history and try again.",
                warning=True, required=True)

    def _pin_history_image(self, filepath):
        try:
            self.pin_pixmap(_load_file_pixmap(filepath))
        except Exception as error:
            log.warning(f"Could not pin history image {filepath}: {error}")
            self._notify(
                "Capture could not be pinned",
                "The history image is missing, locked, or unreadable. Refresh "
                "capture history and try again.",
                warning=True, required=True)

    # -------------------------------------------------------------------
    # Clipboard Watcher
    # -------------------------------------------------------------------

    def _toggle_clipboard_watcher(self):
        previous = self._clipboard_watcher_enabled
        desired = not previous
        config.CLIPBOARD_WATCHER_ENABLED = desired
        if not config.save():
            config.CLIPBOARD_WATCHER_ENABLED = previous
            self._notify(
                "Clipboard watcher unchanged",
                "SwiftShot could not save this preference. Check that the "
                "configuration folder is writable, then try again.",
                warning=True, required=True,
            )
            return
        self._clipboard_watcher_enabled = desired
        if self._clipboard_watcher_enabled:
            self._start_clipboard_watcher()
            self._notify(
                "Clipboard watcher enabled",
                "Copied images will open in SwiftShot.", duration_ms=1500)
        else:
            self._stop_clipboard_watcher()
            self._notify(
                "Clipboard watcher disabled",
                "Copied images will no longer open automatically.",
                duration_ms=1500)

    def _start_clipboard_watcher(self):
        """Watch the clipboard via Qt's change signal (no polling)."""
        if self._clipboard_watcher_connected:
            return
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)
        self._clipboard_watcher_connected = True
        log.info("Clipboard watcher started")

    def _stop_clipboard_watcher(self):
        if self._clipboard_watcher_connected:
            try:
                QApplication.clipboard().dataChanged.disconnect(
                    self._on_clipboard_changed)
            except Exception:
                pass
            self._clipboard_watcher_connected = False
            log.info("Clipboard watcher stopped")

    def _on_clipboard_changed(self):
        try:
            import time
            clipboard = QApplication.clipboard()
            # Ignore our own copies (capture actions, editor copy, OCR text)
            if clipboard.ownsClipboard():
                return
            mime = clipboard.mimeData()
            if not mime or not mime.hasImage():
                return
            # Some apps fire several change notifications per copy
            now = time.monotonic()
            if now - self._last_clipboard_change < 0.5:
                return
            self._last_clipboard_change = now
            pixmap = clipboard.pixmap()
            if pixmap and not pixmap.isNull():
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
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif *.webp);;All Files (*)"
        )
        if filepath:
            try:
                self._open_editor(_load_file_pixmap(filepath))
            except Exception as error:
                log.warning(f"Could not open image file {filepath}: {error}")
                self._notify(
                    "Image could not be opened",
                    "The file is unsupported, damaged, locked, or exceeds the "
                    "safe image limits.",
                    warning=True, required=True)

    def open_from_clipboard(self):
        clipboard = QApplication.clipboard()
        pixmap = clipboard.pixmap()
        if pixmap and not pixmap.isNull():
            self._open_editor(pixmap)
        else:
            self._notify(
                "No image in clipboard",
                "Copy an image, then choose Open Image from Clipboard again.",
                warning=True, duration_ms=2000)

    # -------------------------------------------------------------------
    # Settings / About
    # -------------------------------------------------------------------

    def _reapply_theme(self):
        """Re-apply the current theme across the app, tray, and open editors."""
        from theme import apply_theme, stylesheet_for_theme
        apply_theme(self.app, config.THEME)
        if self.tray_icon and self.tray_icon.contextMenu():
            self.tray_icon.contextMenu().setStyleSheet(
                stylesheet_for_theme(config.THEME))
        for editor in list(self.editors):
            try:
                if editor.isVisible() and hasattr(editor, "retheme"):
                    editor.retheme()
            except Exception:
                log.warning("Could not re-theme an open editor", exc_info=True)

    def _on_system_theme_changed(self):
        """WM_SETTINGCHANGE handler: refresh only when following the system."""
        if config.THEME == "system":
            self._reapply_theme()

    def show_settings(self):
        try:
            from settings_dialog import SettingsDialog

            dialog = SettingsDialog()
            if dialog.exec_() == QDialog.Accepted:
                # Re-apply app + tray + open-editor theming in one place;
                # retheme is non-destructive and cheap, so no change-detection.
                self._reapply_theme()
                self._refresh_tray_hotkey_labels()
                if not self._reregister_hotkeys():
                    self._notify(
                        "Capture shortcuts unavailable",
                        "SwiftShot saved your preferences but could not "
                        "register the global shortcuts. Resolve shortcut "
                        "conflicts and apply Preferences again.",
                        warning=True, required=True,
                    )
                # Apply the clipboard-watcher setting live and keep the flag in
                # sync with config — otherwise the next tray toggle flips a
                # stale flag and writes the inverted value back.
                desired = config.CLIPBOARD_WATCHER_ENABLED
                if desired != self._clipboard_watcher_enabled:
                    self._clipboard_watcher_enabled = desired
                    if desired:
                        self._start_clipboard_watcher()
                    else:
                        self._stop_clipboard_watcher()
        except Exception as e:
            log.error(f"Settings dialog failed: {e}", exc_info=True)
            self._notify(
                "Preferences unavailable",
                "SwiftShot could not open or apply Preferences. Export "
                "diagnostics for details and try again.",
                warning=True, required=True,
            )

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

    def exit_app(self, allow_prompts=True):
        # Give open editors the chance to prompt for unsaved changes;
        # an editor that refuses to close aborts the exit.
        if not allow_prompts and any(
                getattr(editor, "_dirty", False) for editor in self.editors):
            log.info("Unattended exit refused because an editor is dirty")
            return False
        running_ocr = []
        for worker in list(self._ocr_workers):
            try:
                if worker.isRunning():
                    running_ocr.append(worker)
            except RuntimeError:
                # Qt wrapper already deleted; it cannot still own a thread.
                continue
        if running_ocr:
            log.info(
                "Application exit deferred for %d active OCR operation(s)",
                len(running_ocr),
            )
            if allow_prompts:
                QMessageBox.information(
                    None,
                    "Text Recognition In Progress",
                    "SwiftShot is still recognizing text. Wait for the OCR "
                    "result or error, then exit again. This prevents an "
                    "incomplete operation from being terminated abruptly.",
                )
            return False
        for editor in list(self.editors):
            try:
                if not editor.close():
                    log.info("Exit cancelled from editor close prompt")
                    return False
            except Exception:
                log.warning("Editor failed to close; refusing application exit",
                            exc_info=True)
                return False
        self._begin_capture_operation()
        log.info("SwiftShot shutting down")
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
        self._stop_clipboard_watcher()
        # Join the update-check thread so it can't emit into a torn-down app
        # ("QThread: Destroyed while thread is still running").
        if self._update_checker is not None:
            try:
                self._update_checker.requestInterruption()
                if not self._update_checker.wait(5000):
                    log.warning("Update checker did not stop before shutdown")
            except Exception:
                pass
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
        return True
