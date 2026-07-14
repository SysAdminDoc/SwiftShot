"""
SwiftShot Countdown Overlay
Small always-on-top countdown badge shown before a capture fires.
Used for timed capture and CAPTURE_DELAY_MS.

Deliberately NOT full-screen and NOT focus-stealing: timed capture exists
so the user can interact with the screen (open menus, hover tooltips)
while the countdown runs. Clicking the badge cancels the capture.
"""

import time

from PyQt5.QtWidgets import QWidget, QApplication, QPushButton
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QCursor, QPalette
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRectF
from utils import exclude_window_from_capture


class CountdownOverlay(QWidget):
    """Compact countdown badge shown in the corner of the active screen."""

    countdown_finished = pyqtSignal()
    cancelled = pyqtSignal()

    BADGE_W = 150
    BADGE_H = 184

    def __init__(self, total_ms, parent=None):
        super().__init__(parent)
        self._total_ms = max(100, total_ms)
        self._remaining_ms = self._total_ms
        self._seconds_left = (self._total_ms + 999) // 1000
        self._generation = 0
        self._active_generation = None

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Never steal focus: the user must be able to keep interacting
        # with other applications during the countdown.
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.BADGE_W, self.BADGE_H)
        self.setToolTip("Click to cancel the timed capture")
        self.setAccessibleName("Timed capture countdown")
        self.setAccessibleDescription(
            f"Timed capture in {self._seconds_left} seconds. Activate Cancel "
            "timed capture to stop it.")
        self.setFocusPolicy(Qt.NoFocus)

        # Keep the window non-activating, but expose a native button so UIA /
        # Narrator gets a Button role and Invoke action instead of an opaque
        # custom-painted client area.
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setAccessibleName("Cancel timed capture")
        self.cancel_button.setAccessibleDescription(
            "Stop the pending capture and close this countdown.")
        self.cancel_button.setToolTip("Cancel timed capture")
        self.cancel_button.setFocusPolicy(Qt.StrongFocus)
        self.cancel_button.setGeometry(25, 150, 100, 28)
        self.cancel_button.setStyleSheet(
            "QPushButton { background: palette(button); color: palette(button-text); "
            "border: 1px solid palette(window-text); border-radius: 4px; }"
            "QPushButton:focus { border: 2px solid palette(highlight); }"
        )
        self.cancel_button.clicked.connect(self._cancel)

        self._ring_background = QColor(30, 30, 46, 230)
        self._ring_color = QColor("#89b4fa")
        self._number_color = QColor("#cdd6f4")
        self._label_color = QColor("#a6adc8")
        try:
            from theme import is_high_contrast_enabled
            if is_high_contrast_enabled():
                self._ring_background = self.palette().color(QPalette.Window)
                self._ring_background.setAlpha(245)
                self._ring_color = self.palette().color(QPalette.Highlight)
                self._number_color = self.palette().color(QPalette.WindowText)
                self._label_color = self.palette().color(QPalette.Text)
        except ImportError:
            pass

        self._timer = QTimer(self)
        self._timer.timeout.connect(
            lambda: self._tick(self._active_generation)
        )

    def showEvent(self, event):
        super().showEvent(event)
        exclude_window_from_capture(self)

    def closeEvent(self, event):
        self._generation += 1
        self._active_generation = None
        self._timer.stop()
        super().closeEvent(event)

    def _position_badge(self):
        """Bottom-right corner of the screen the cursor is on."""
        screen = QApplication.screenAt(QCursor.pos())
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 24,
                  geo.bottom() - self.height() - 24)

    def start(self):
        """Show the badge and start counting down."""
        self._position_badge()
        self.show()
        self.raise_()
        self._generation += 1
        self._active_generation = self._generation
        self._started_at = time.monotonic()
        self._timer.start(50)

    def _tick(self, generation=None):
        if (generation != self._active_generation
                or generation != self._generation
                or not self._timer.isActive()
                or not self.isVisible()):
            return
        # Derive remaining time from the clock, not tick counts — coarse
        # QTimer slack accumulates and made long countdowns fire late.
        elapsed_ms = int((time.monotonic() - self._started_at) * 1000)
        self._remaining_ms = self._total_ms - elapsed_ms
        new_seconds = max(0, (self._remaining_ms + 999) // 1000)
        if new_seconds != self._seconds_left:
            self._seconds_left = new_seconds
            self.setAccessibleDescription(
                f"Timed capture in {max(1, new_seconds)} seconds. Activate "
                "Cancel timed capture to stop it.")
        self.update()

        if self._remaining_ms <= 0:
            self._timer.stop()
            self.hide()
            self._active_generation = None
            self.countdown_finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        radius = 56
        cx = self.width() / 2
        cy = radius + 8

        # Progress ring
        progress = 1.0 - (self._remaining_ms / self._total_ms)
        span_angle = int(progress * 360 * 16)

        ring_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        # Background circle
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._ring_background)
        painter.drawEllipse(ring_rect)

        # Progress arc
        pen = QPen(self._ring_color, 5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(ring_rect.adjusted(4, 4, -4, -4), 90 * 16, -span_angle)

        # Number
        display = max(1, self._seconds_left)
        painter.setPen(self._number_color)
        font = QFont("Segoe UI", 32, QFont.Bold)
        painter.setFont(font)
        painter.drawText(ring_rect, Qt.AlignCenter, str(display))

        # Label below
        painter.setPen(self._label_color)
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        label_rect = QRectF(0, cy + radius + 6, self.width(), 22)
        painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop,
                         "Capturing soon")

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._cancel()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel()
        else:
            super().keyPressEvent(event)

    def _cancel(self):
        self._generation += 1
        self._active_generation = None
        self._timer.stop()
        self.hide()
        self.cancelled.emit()
