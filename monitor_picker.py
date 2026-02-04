"""
SwiftShot Monitor Picker Dialog
Shows thumbnails of each connected monitor for the user to pick
which one to capture for fullscreen mode.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QApplication, QFrame, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QCursor
from PyQt5.QtCore import Qt, QRect, QSize, pyqtSignal


class MonitorCard(QFrame):
    """Clickable card showing a monitor thumbnail."""

    clicked = pyqtSignal(int)  # monitor index

    def __init__(self, index, screen, thumbnail, parent=None):
        super().__init__(parent)
        self.index = index
        self.screen = screen
        self._thumbnail = thumbnail
        self._hovered = False

        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)
        self.setFixedSize(280, 200)

        self.setStyleSheet("""
            MonitorCard {
                background-color: #1e1e2e;
                border: 2px solid #45475a;
                border-radius: 8px;
            }
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()

        # Background
        bg = QColor("#313244") if self._hovered else QColor("#1e1e2e")
        painter.setBrush(bg)
        border = QColor("#89b4fa") if self._hovered else QColor("#45475a")
        painter.setPen(QPen(border, 2))
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 8, 8)

        # Thumbnail area
        thumb_margin = 12
        thumb_top = 10
        thumb_w = w - thumb_margin * 2
        thumb_h = h - 70

        if not self._thumbnail.isNull():
            scaled = self._thumbnail.scaled(
                thumb_w, thumb_h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            tx = thumb_margin + (thumb_w - scaled.width()) // 2
            ty = thumb_top + (thumb_h - scaled.height()) // 2

            # Drop shadow
            painter.fillRect(tx + 3, ty + 3, scaled.width(), scaled.height(),
                             QColor(0, 0, 0, 60))
            # Border around thumbnail
            painter.setPen(QPen(QColor("#585b70"), 1))
            painter.drawRect(tx - 1, ty - 1, scaled.width() + 1, scaled.height() + 1)
            # Actual thumbnail
            painter.drawPixmap(tx, ty, scaled)

        # Label: Monitor number
        geo = self.screen.geometry()
        label = f"Monitor {self.index + 1}"
        sub_label = f"{geo.width()} x {geo.height()}"

        painter.setPen(QColor("#cdd6f4"))
        font = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(font)
        label_y = h - 44
        painter.drawText(thumb_margin, label_y, label)

        painter.setPen(QColor("#a6adc8"))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.drawText(thumb_margin, label_y + 20, sub_label)

        # Primary badge
        if self.screen == QApplication.primaryScreen():
            badge_text = "Primary"
            badge_font = QFont("Segoe UI", 8)
            painter.setFont(badge_font)
            fm = painter.fontMetrics()
            bw = fm.horizontalAdvance(badge_text) + 12
            bh = fm.height() + 6
            bx = w - bw - thumb_margin
            by = label_y - 6

            painter.setBrush(QColor("#89b4fa"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bx, by, bw, bh, 3, 3)

            painter.setPen(QColor("#1e1e2e"))
            painter.drawText(bx + 6, by + fm.ascent() + 3, badge_text)

        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)


class MonitorPicker(QDialog):
    """Dialog to pick which monitor to capture."""

    monitor_selected = pyqtSignal(int)  # monitor index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Monitor to Capture")
        self.setWindowFlags(
            Qt.Dialog |
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self._selected_index = -1

        self._build_ui()
        self._center_on_cursor()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.setStyleSheet("""
            MonitorPicker {
                background-color: #1e1e2e;
                border: 2px solid #45475a;
                border-radius: 12px;
            }
            QLabel {
                color: #cdd6f4;
                background: transparent;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #89b4fa;
            }
        """)

        # Title
        title = QLabel("Select Monitor")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Click a monitor to capture it")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet("color: #a6adc8;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Monitor cards row
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            thumbnail = self._capture_monitor_thumbnail(screen)
            card = MonitorCard(i, screen, thumbnail)
            card.clicked.connect(self._on_card_clicked)
            cards_layout.addWidget(card)

        layout.addLayout(cards_layout)

        # "All Monitors" button + Cancel
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        all_btn = QPushButton(f"All Monitors ({len(screens)})")
        all_btn.clicked.connect(lambda: self._on_card_clicked(-1))
        btn_layout.addWidget(all_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _capture_monitor_thumbnail(self, screen):
        """Capture a quick thumbnail of a monitor."""
        geo = screen.geometry()
        primary = QApplication.primaryScreen()
        if primary:
            pixmap = primary.grabWindow(
                0, geo.x(), geo.y(), geo.width(), geo.height()
            )
            return pixmap
        return QPixmap()

    def _center_on_cursor(self):
        """Center the dialog near the cursor."""
        self.adjustSize()
        cursor_pos = QCursor.pos()
        x = cursor_pos.x() - self.width() // 2
        y = cursor_pos.y() - self.height() // 2

        # Keep on screen
        screen = QApplication.screenAt(cursor_pos)
        if screen:
            geo = screen.availableGeometry()
            x = max(geo.left(), min(x, geo.right() - self.width()))
            y = max(geo.top(), min(y, geo.bottom() - self.height()))

        self.move(x, y)

    def _on_card_clicked(self, index):
        self._selected_index = index
        self.monitor_selected.emit(index)
        self.accept()

    def selected_index(self):
        return self._selected_index

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
