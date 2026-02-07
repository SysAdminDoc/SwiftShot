"""
SwiftShot Capture Menu
Dark-themed popup on PrintScreen with every capture mode.
Includes embedded timer controls for delayed capture after region selection.
"""

from PyQt5.QtWidgets import (
    QMenu, QAction, QApplication, QWidgetAction,
    QWidget, QHBoxLayout, QCheckBox, QSpinBox, QLabel
)
from PyQt5.QtGui import QCursor, QFont
from PyQt5.QtCore import Qt, pyqtSignal

from config import config


class CaptureMenu(QMenu):
    """Popup menu with all capture modes and timer controls."""

    capture_monitor = pyqtSignal(int)
    capture_window = pyqtSignal()
    capture_region = pyqtSignal()
    capture_freehand = pyqtSignal()
    capture_last_region = pyqtSignal()
    capture_ocr = pyqtSignal()
    capture_scrolling = pyqtSignal()
    open_file = pyqtSignal()
    open_clipboard = pyqtSignal()
    show_history = pyqtSignal()
    toggle_clipboard_watcher = pyqtSignal()

    # Emitted with (enabled, seconds) when timer state changes
    timer_changed = pyqtSignal(bool, int)

    def __init__(self, clipboard_watching=False, parent=None):
        super().__init__(parent)
        self._clipboard_watching = clipboard_watching
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._timer_enabled = config.CAPTURE_TIMER_ENABLED
        self._timer_seconds = config.CAPTURE_TIMER_SECONDS
        self._apply_style()
        self._build_menu()

    @property
    def timer_enabled(self):
        return self._timer_enabled

    @property
    def timer_seconds(self):
        return self._timer_seconds

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

        # Per-monitor captures
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            primary = "  (Primary)" if screen == QApplication.primaryScreen() else ""
            label = f"Screen {i + 1}  -  {geo.width()} x {geo.height()}{primary}"
            action = self.addAction(label)
            idx = i
            action.triggered.connect(
                lambda checked, n=idx: self.capture_monitor.emit(n))

        if len(screens) > 1:
            action = self.addAction(
                f"All Screens  ({len(screens)} monitors)")
            action.triggered.connect(lambda: self.capture_monitor.emit(-1))

        self.addSeparator()

        # Capture modes
        a = self.addAction("Window Mode                       Alt+PrtSc")
        a.triggered.connect(lambda: self.capture_window.emit())

        a = self.addAction("Region                                    PrtSc*")
        a.triggered.connect(lambda: self.capture_region.emit())

        a = self.addAction("Region (Freehand)")
        a.triggered.connect(lambda: self.capture_freehand.emit())

        a = self.addAction("Last Region                       Shift+PrtSc")
        a.triggered.connect(lambda: self.capture_last_region.emit())

        self.addSeparator()

        # Scrolling capture
        a = self.addAction("Scrolling Capture...")
        a.triggered.connect(lambda: self.capture_scrolling.emit())

        self.addSeparator()

        # OCR
        a = self.addAction("OCR Region  (Extract Text)")
        a.triggered.connect(lambda: self.capture_ocr.emit())

        self.addSeparator()

        # Open
        a = self.addAction("Open from File...")
        a.triggered.connect(lambda: self.open_file.emit())

        a = self.addAction("Open from Clipboard")
        a.triggered.connect(lambda: self.open_clipboard.emit())

        self.addSeparator()

        # History
        a = self.addAction("Capture History...")
        a.triggered.connect(lambda: self.show_history.emit())

        # Clipboard watcher
        watcher_label = ("Clipboard Watcher  [ON]"
                         if self._clipboard_watching
                         else "Clipboard Watcher  [OFF]")
        a = self.addAction(watcher_label)
        a.triggered.connect(lambda: self.toggle_clipboard_watcher.emit())

        self.addSeparator()

        # --- Timer Controls (embedded widget) ---
        self._add_timer_widget()

    def _add_timer_widget(self):
        """Embed a timer checkbox + spinner into the menu as a QWidgetAction."""
        timer_widget = QWidget()
        timer_widget.setStyleSheet("""
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                padding: 0px;
            }
            QCheckBox {
                spacing: 6px;
                font-size: 10pt;
            }
            QCheckBox::indicator {
                width: 15px; height: 15px;
                border: 1px solid #585b70;
                border-radius: 3px;
                background-color: #313244;
            }
            QCheckBox::indicator:checked {
                background-color: #89b4fa;
                border-color: #89b4fa;
            }
            QSpinBox {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 3px;
                padding: 2px 4px; min-height: 20px;
                font-size: 9pt;
            }
            QSpinBox:hover { border-color: #89b4fa; }
            QLabel {
                font-size: 9pt; color: #a6adc8;
                background: transparent;
            }
        """)

        layout = QHBoxLayout(timer_widget)
        layout.setContentsMargins(20, 6, 12, 6)
        layout.setSpacing(6)

        self._timer_cb = QCheckBox("Timer")
        self._timer_cb.setChecked(self._timer_enabled)
        self._timer_cb.setToolTip(
            "Select region first, then countdown gives you\n"
            "time to interact with the screen before capture."
        )
        self._timer_cb.toggled.connect(self._on_timer_toggled)
        layout.addWidget(self._timer_cb)

        self._timer_spin = QSpinBox()
        self._timer_spin.setRange(1, 30)
        self._timer_spin.setValue(self._timer_seconds)
        self._timer_spin.setSuffix("s")
        self._timer_spin.setFixedWidth(60)
        self._timer_spin.setEnabled(self._timer_enabled)
        self._timer_spin.valueChanged.connect(self._on_timer_value_changed)
        layout.addWidget(self._timer_spin)

        hint = QLabel("(select area, then wait)")
        hint.setVisible(self._timer_enabled)
        self._timer_hint = hint
        layout.addWidget(hint)

        layout.addStretch()

        widget_action = QWidgetAction(self)
        widget_action.setDefaultWidget(timer_widget)
        self.addAction(widget_action)

    def _on_timer_toggled(self, checked):
        self._timer_enabled = checked
        self._timer_spin.setEnabled(checked)
        self._timer_hint.setVisible(checked)

        # Persist immediately so captures in this session use the value
        config.CAPTURE_TIMER_ENABLED = checked
        config.save()

        self.timer_changed.emit(checked, self._timer_spin.value())

    def _on_timer_value_changed(self, val):
        self._timer_seconds = val
        config.CAPTURE_TIMER_SECONDS = val
        config.save()
        self.timer_changed.emit(self._timer_enabled, val)

    def popup_at_cursor(self):
        self.popup(QCursor.pos())
