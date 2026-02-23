"""
SwiftShot Countdown Overlay
Full-screen translucent overlay showing a countdown timer before capture.
Used when CAPTURE_DELAY_MS > 0.
"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QColor, QFont, QPen
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QRectF

from utils import virtual_geometry


class CountdownOverlay(QWidget):
    """Full-screen countdown overlay before capture."""

    countdown_finished = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, total_ms, parent=None):
        super().__init__(parent)
        self._total_ms = max(100, total_ms)
        self._remaining_ms = self._total_ms
        self._seconds_left = (self._total_ms + 999) // 1000

        geo = virtual_geometry()
        self.setFixedSize(geo.width(), geo.height())
        self.move(geo.x(), geo.y())

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.WaitCursor)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        """Show the overlay and start counting down."""
        self.show()
        self.activateWindow()
        self.raise_()
        self._timer.start(50)

    def _tick(self):
        self._remaining_ms -= 50
        new_seconds = max(0, (self._remaining_ms + 999) // 1000)
        if new_seconds != self._seconds_left:
            self._seconds_left = new_seconds
        self.update()

        if self._remaining_ms <= 0:
            self._timer.stop()
            self.hide()
            self.countdown_finished.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Semi-transparent dark background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60))

        # Center circle with countdown number
        cx = self.width() / 2
        cy = self.height() / 2
        radius = 80

        # Progress ring
        progress = 1.0 - (self._remaining_ms / self._total_ms)
        span_angle = int(progress * 360 * 16)

        ring_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        # Background circle
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 30, 46, 220))
        painter.drawEllipse(ring_rect)

        # Progress arc
        pen = QPen(QColor("#89b4fa"), 6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(ring_rect.adjusted(4, 4, -4, -4), 90 * 16, -span_angle)

        # Number
        display = max(1, self._seconds_left)
        painter.setPen(QColor("#cdd6f4"))
        font = QFont("Segoe UI", 48, QFont.Bold)
        painter.setFont(font)
        painter.drawText(ring_rect, Qt.AlignCenter, str(display))

        # Label below
        painter.setPen(QColor("#a6adc8"))
        font = QFont("Segoe UI", 12)
        painter.setFont(font)
        label_rect = QRectF(cx - 150, cy + radius + 10, 300, 40)
        painter.drawText(label_rect, Qt.AlignCenter, "Capturing in... (Esc to cancel)")

        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._timer.stop()
            self.hide()
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)
