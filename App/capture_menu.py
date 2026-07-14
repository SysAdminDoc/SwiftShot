"""
SwiftShot Capture Menu
Dark-themed popup on PrintScreen with every capture mode.
Includes embedded timer controls for delayed capture after region selection.
"""

from PyQt5.QtWidgets import (
    QMenu, QApplication, QWidgetAction,
    QWidget, QHBoxLayout, QCheckBox, QSpinBox, QLabel
)
from PyQt5.QtGui import QCursor
from PyQt5.QtCore import Qt, pyqtSignal

from config import config
from theme import colors_for_theme, stylesheet_for_theme
from utils import exclude_window_from_capture


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
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("SwiftShot capture menu")
        self.setAccessibleDescription(
            "Choose a screenshot capture mode. Use the arrow keys to move and Enter to start."
        )
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
        self.setStyleSheet(stylesheet_for_theme(config.THEME))

    def _build_menu(self):
        screens = QApplication.screens()

        # Per-monitor captures
        for i, screen in enumerate(screens):
            geo = screen.geometry()
            primary = "  (Primary)" if screen == QApplication.primaryScreen() else ""
            label = f"Screen {i + 1}  -  {geo.width()} x {geo.height()}{primary}"
            action = self._add_menu_action(
                label,
                f"Capture screen {i + 1} at {geo.width()} by {geo.height()} pixels{primary}.",
            )
            idx = i
            action.triggered.connect(
                lambda checked, n=idx: self.capture_monitor.emit(n))

        if len(screens) > 1:
            action = self._add_menu_action(
                f"All Screens  ({len(screens)} monitors)",
                f"Capture all {len(screens)} monitors.",
            )
            action.triggered.connect(lambda: self.capture_monitor.emit(-1))

        self.addSeparator()

        # Capture modes (\t right-aligns the shortcut column properly;
        # space-padding misaligns with proportional fonts)
        a = self._add_menu_action(
            "Window Mode\tAlt+PrtSc",
            "Capture the selected window.",
        )
        a.triggered.connect(lambda: self.capture_window.emit())

        a = self._add_menu_action(
            "Region",
            "Select a rectangular region to capture.",
        )
        a.triggered.connect(lambda: self.capture_region.emit())

        a = self._add_menu_action(
            "Region (Freehand)",
            "Draw a freehand region to capture.",
        )
        a.triggered.connect(lambda: self.capture_freehand.emit())

        a = self._add_menu_action(
            "Last Region\tShift+PrtSc",
            "Capture the previous region again.",
        )
        a.triggered.connect(lambda: self.capture_last_region.emit())

        self.addSeparator()

        # Scrolling capture
        a = self._add_menu_action(
            "Scrolling Capture...",
            "Capture a scrollable page or window.",
        )
        a.triggered.connect(lambda: self.capture_scrolling.emit())

        self.addSeparator()

        # OCR
        a = self._add_menu_action(
            "OCR Region  (Extract Text)",
            "Capture a region and extract text from it.",
        )
        a.triggered.connect(lambda: self.capture_ocr.emit())

        self.addSeparator()

        # Open
        a = self._add_menu_action(
            "Open from File...",
            "Open an existing image file in the editor.",
        )
        a.triggered.connect(lambda: self.open_file.emit())

        a = self._add_menu_action(
            "Open from Clipboard",
            "Open the current clipboard image in the editor.",
        )
        a.triggered.connect(lambda: self.open_clipboard.emit())

        self.addSeparator()

        # History
        a = self._add_menu_action(
            "Capture History...",
            "Open saved capture history.",
        )
        a.triggered.connect(lambda: self.show_history.emit())

        # Clipboard watcher
        watcher_label = ("Clipboard Watcher  [ON]"
                         if self._clipboard_watching
                         else "Clipboard Watcher  [OFF]")
        a = self._add_menu_action(
            watcher_label,
            "Toggle automatic opening of copied clipboard images.",
        )
        a.triggered.connect(lambda: self.toggle_clipboard_watcher.emit())

        self.addSeparator()

        # --- Timer Controls (embedded widget) ---
        self._add_timer_widget()

    def _add_menu_action(self, label, description):
        action = self.addAction(label)
        action.setToolTip(description)
        action.setStatusTip(description)
        return action

    def _selectable_actions(self):
        return [
            action for action in self.actions()
            if action.isEnabled()
            and not action.isSeparator()
            and action.text().strip()
        ]

    def _add_timer_widget(self):
        """Embed a timer checkbox + spinner into the menu as a QWidgetAction."""
        timer_widget = QWidget()
        colors = colors_for_theme(config.THEME)
        timer_widget.setAccessibleName("Timed capture controls")
        timer_widget.setAccessibleDescription(
            "Enable delayed capture and set the countdown duration."
        )
        timer_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {colors['BG1']};
                color: {colors['TEXT_PRI']};
                padding: 0px;
            }}
            QCheckBox {{
                spacing: 6px;
                font-size: 10pt;
            }}
            QCheckBox::indicator {{
                width: 15px; height: 15px;
                border: 1px solid {colors['BORDER']};
                border-radius: 3px;
                background-color: {colors['BG2']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {colors['ACCENT']};
                border-color: {colors['ACCENT']};
            }}
            QSpinBox {{
                background-color: {colors['BG2']}; color: {colors['TEXT_PRI']};
                border: 1px solid {colors['BORDER']}; border-radius: 3px;
                padding: 2px 4px; min-height: 20px;
                font-size: 9pt;
            }}
            QSpinBox:hover {{ border-color: {colors['ACCENT']}; }}
            QLabel {{
                font-size: 9pt; color: {colors['TEXT_SEC']};
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(timer_widget)
        layout.setContentsMargins(20, 6, 12, 6)
        layout.setSpacing(6)

        self._timer_cb = QCheckBox("Timer")
        self._timer_cb.setAccessibleName("Enable timed capture")
        self._timer_cb.setAccessibleDescription(
            "When enabled, capture starts after the selected area is chosen and the countdown ends."
        )
        self._timer_cb.setChecked(self._timer_enabled)
        self._timer_cb.setToolTip(
            "Select region first, then countdown gives you\n"
            "time to interact with the screen before capture."
        )
        self._timer_cb.toggled.connect(self._on_timer_toggled)
        layout.addWidget(self._timer_cb)

        self._timer_spin = QSpinBox()
        self._timer_spin.setAccessibleName("Timed capture countdown seconds")
        self._timer_spin.setAccessibleDescription(
            "Number of seconds to wait after region selection before taking the capture."
        )
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

    def showEvent(self, event):
        super().showEvent(event)
        exclude_window_from_capture(self)

    def keyPressEvent(self, event):
        selectable = self._selectable_actions()
        if not selectable:
            super().keyPressEvent(event)
            return

        key = event.key()
        active = self.activeAction()

        if key in (Qt.Key_Down, Qt.Key_Tab):
            if active not in selectable:
                self.setActiveAction(selectable[0])
            else:
                self.setActiveAction(selectable[(selectable.index(active) + 1) % len(selectable)])
            event.accept()
            return

        if key in (Qt.Key_Up, Qt.Key_Backtab):
            if active not in selectable:
                self.setActiveAction(selectable[-1])
            else:
                self.setActiveAction(selectable[(selectable.index(active) - 1) % len(selectable)])
            event.accept()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if active in selectable:
                active.trigger()
                self.close()
                event.accept()
                return

        super().keyPressEvent(event)
