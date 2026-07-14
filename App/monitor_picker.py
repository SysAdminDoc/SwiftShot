"""
SwiftShot Monitor Picker Dialog
Shows thumbnails of each connected monitor for the user to pick
which one to capture for fullscreen mode.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QApplication, QFrame, QScrollArea, QWidget
)
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QCursor
from PyQt5.QtCore import Qt, pyqtSignal

from config import config
from theme import colors_for_theme
from utils import exclude_window_from_capture


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
        self.setFocusPolicy(Qt.StrongFocus)
        geo = screen.geometry()
        self.setAccessibleName(f"Monitor {index + 1}")
        self.setAccessibleDescription(
            f"Capture monitor {index + 1}, {geo.width()} by {geo.height()} pixels. "
            "Press Enter to capture.")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        colors = colors_for_theme(config.THEME)

        # Background
        active = self._hovered or self.hasFocus()
        bg = QColor(colors["BG2"]) if active else QColor(colors["BG1"])
        painter.setBrush(bg)
        border = QColor(colors["ACCENT"]) if active else QColor(colors["BORDER"])
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
            painter.setPen(QPen(QColor(colors["BORDER"]), 1))
            painter.drawRect(tx - 1, ty - 1, scaled.width() + 1, scaled.height() + 1)
            # Actual thumbnail
            painter.drawPixmap(tx, ty, scaled)

        # Label: Monitor number
        geo = self.screen.geometry()
        label = f"Monitor {self.index + 1}"
        sub_label = f"{geo.width()} x {geo.height()}"

        painter.setPen(QColor(colors["TEXT_PRI"]))
        font = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(font)
        label_y = h - 44
        painter.drawText(thumb_margin, label_y, label)

        painter.setPen(QColor(colors["TEXT_SEC"]))
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

            painter.setBrush(QColor(colors["ACCENT"]))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bx, by, bw, bh, 3, 3)

            painter.setPen(QColor(colors["BG1"]))
            painter.drawText(bx + 6, by + fm.ascent() + 3, badge_text)

        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.index)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit(self.index)
        else:
            super().keyPressEvent(event)


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
        self._cards = []
        self.setAccessibleName("Monitor picker")
        self.setAccessibleDescription(
            "Choose one monitor or the full desktop to capture.")

        self._build_ui()
        self._center_on_cursor()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Frameless dialog: draw its own border with theme tokens; buttons
        # and labels inherit the app-wide stylesheet.
        colors = colors_for_theme(config.THEME)
        self.setStyleSheet(f"""
            MonitorPicker {{
                background-color: {colors['BG1']};
                border: 2px solid {colors['BORDER']};
                border-radius: 12px;
            }}
        """)

        # Title
        title = QLabel("Select Monitor")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        screens = QApplication.screens()

        # Empty state: no displays enumerated (e.g. a headless/console session).
        if not screens:
            subtitle = QLabel("No displays detected.")
            subtitle.setFont(QFont("Segoe UI", 10))
            subtitle.setStyleSheet(f"color: {colors['TEXT_SEC']};")
            subtitle.setAlignment(Qt.AlignCenter)
            layout.addWidget(subtitle)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
            return

        subtitle = QLabel("Click a monitor to capture it, or press 1-9")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet(f"color: {colors['TEXT_SEC']};")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        # Monitor cards row
        cards_container = QWidget()
        cards_layout = QHBoxLayout(cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(12)

        for i, screen in enumerate(screens):
            thumbnail = self._capture_monitor_thumbnail(screen)
            card = MonitorCard(i, screen, thumbnail)
            card.clicked.connect(self._on_card_clicked)
            cards_layout.addWidget(card)
            self._cards.append(card)

        cards_container.adjustSize()
        cards_scroll = QScrollArea()
        cards_scroll.setAccessibleName("Available monitors")
        cards_scroll.setWidget(cards_container)
        cards_scroll.setWidgetResizable(False)
        cards_scroll.setFrameShape(QFrame.NoFrame)
        cards_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        cards_scroll.setFixedHeight(216)
        active_screen = (QApplication.screenAt(QCursor.pos())
                         or QApplication.primaryScreen())
        available_width = (active_screen.availableGeometry().width()
                           if active_screen is not None else 960)
        cards_scroll.setMaximumWidth(max(300, int(available_width * 0.9)))
        self.cards_scroll = cards_scroll
        layout.addWidget(cards_scroll, alignment=Qt.AlignCenter)

        # "All Monitors" button + Cancel
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        if len(screens) > 1:
            all_btn = QPushButton(f"All Monitors ({len(screens)})")
            all_btn.setToolTip("Capture the complete virtual desktop")
            all_btn.clicked.connect(lambda: self._on_card_clicked(-1))
            btn_layout.addWidget(all_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def showEvent(self, event):
        super().showEvent(event)
        exclude_window_from_capture(self)
        if self._cards:
            self._cards[0].setFocus(Qt.OtherFocusReason)

    def _capture_monitor_thumbnail(self, screen):
        """Capture a quick thumbnail of a monitor.

        Uses the monitor's own QScreen -- grabbing through the primary
        screen with logical coordinates is wrong under mixed/high DPI.
        """
        return screen.grabWindow(0)

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
        elif Qt.Key_1 <= event.key() <= Qt.Key_9:
            index = event.key() - Qt.Key_1
            if index < len(QApplication.screens()):
                self._on_card_clicked(index)
        elif event.key() == Qt.Key_A:
            self._on_card_clicked(-1)
        else:
            super().keyPressEvent(event)
