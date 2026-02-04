"""
SwiftShot Capture Menu
Dark-themed popup that appears on PrintScreen with every capture mode:
  - Per-monitor capture (Screen 1, 2, 3...)
  - All Screens
  - Window Mode (interactive, Greenshot-style)
  - Region (rectangle)
  - Region (freehand)
  - Last Region
  - OCR Region
  - Open from File / Clipboard
"""

from PyQt5.QtWidgets import QMenu, QAction, QApplication
from PyQt5.QtGui import QCursor
from PyQt5.QtCore import Qt, pyqtSignal


class CaptureMenu(QMenu):
    """Popup menu with all capture modes."""

    capture_monitor = pyqtSignal(int)    # monitor index, -1 = all
    capture_window = pyqtSignal()
    capture_region = pyqtSignal()
    capture_freehand = pyqtSignal()
    capture_last_region = pyqtSignal()
    capture_ocr = pyqtSignal()
    open_file = pyqtSignal()
    open_clipboard = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._apply_style()
        self._build_menu()

    def _apply_style(self):
        self.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 2px solid #45475a;
                border-radius: 8px;
                padding: 6px 4px;
                font-family: 'Segoe UI';
                font-size: 10pt;
            }
            QMenu::item {
                padding: 8px 40px 8px 24px;
                border-radius: 4px;
                margin: 1px 4px;
            }
            QMenu::item:selected {
                background-color: #45475a;
                color: #cdd6f4;
            }
            QMenu::item:disabled {
                color: #585b70;
            }
            QMenu::separator {
                height: 1px;
                background-color: #313244;
                margin: 5px 12px;
            }
        """)

    def _build_menu(self):
        screens = QApplication.screens()

        # --- Per-monitor captures ---
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            primary = "  (Primary)" if screen == QApplication.primaryScreen() else ""
            label = f"Screen {i + 1}  -  {geo.width()} x {geo.height()}{primary}"
            action = self.addAction(label)
            idx = i
            action.triggered.connect(lambda checked, n=idx: self.capture_monitor.emit(n))

        if len(screens) > 1:
            action = self.addAction(f"All Screens  ({len(screens)} monitors)")
            action.triggered.connect(lambda: self.capture_monitor.emit(-1))

        self.addSeparator()

        # --- Capture modes ---
        a = self.addAction("Window Mode                       Alt+PrtSc")
        a.triggered.connect(lambda: self.capture_window.emit())

        a = self.addAction("Region                                    PrtSc*")
        a.triggered.connect(lambda: self.capture_region.emit())

        a = self.addAction("Region (Freehand)")
        a.triggered.connect(lambda: self.capture_freehand.emit())

        a = self.addAction("Last Region                       Shift+PrtSc")
        a.triggered.connect(lambda: self.capture_last_region.emit())

        self.addSeparator()

        # --- OCR ---
        a = self.addAction("OCR Region  (Extract Text)")
        a.triggered.connect(lambda: self.capture_ocr.emit())

        self.addSeparator()

        # --- Open ---
        a = self.addAction("Open from File...")
        a.triggered.connect(lambda: self.open_file.emit())

        a = self.addAction("Open from Clipboard")
        a.triggered.connect(lambda: self.open_clipboard.emit())

    def popup_at_cursor(self):
        """Show the menu at the current cursor position."""
        self.popup(QCursor.pos())
