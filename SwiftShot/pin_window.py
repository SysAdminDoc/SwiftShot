"""
SwiftShot Pin Window
Always-on-top borderless mini-window for pinned screenshots.
Drag to move, scroll to resize, right-click context menu.
"""

from PyQt5.QtWidgets import (
    QWidget, QApplication, QMenu, QAction, QLabel, QVBoxLayout, QHBoxLayout
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QColor, QPen, QCursor, QFont, QIcon
)
from PyQt5.QtCore import Qt, QPoint, QSize, QRect, pyqtSignal

from config import config
from logger import log


class PinWindow(QWidget):
    """Always-on-top floating screenshot window."""

    closed = pyqtSignal(object)  # emits self

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._original_pixmap = pixmap.copy()
        self._pixmap = pixmap.copy()
        self._scale = 1.0
        self._min_scale = 0.1
        self._max_scale = 5.0
        self._dragging = False
        self._drag_start = QPoint()
        self._hovered = False
        self._opacity = config.PIN_OPACITY / 100.0

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.SizeAllCursor)
        self.setWindowOpacity(self._opacity)

        self._update_size()
        self._center_on_cursor()

    def _center_on_cursor(self):
        pos = QCursor.pos()
        self.move(pos.x() - self.width() // 2, pos.y() - self.height() // 2)

    def _update_size(self):
        w = max(50, int(self._original_pixmap.width() * self._scale))
        h = max(50, int(self._original_pixmap.height() * self._scale))
        self._pixmap = self._original_pixmap.scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setFixedSize(self._pixmap.width() + 4, self._pixmap.height() + 4)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Shadow
        painter.fillRect(3, 3, self.width() - 3, self.height() - 3, QColor(0, 0, 0, 40))

        # Image
        painter.drawPixmap(0, 0, self._pixmap)

        # Border
        border_color = QColor(config.PIN_BORDER_COLOR)
        if self._hovered:
            border_color.setAlpha(220)
            pen_width = 2
        else:
            border_color.setAlpha(100)
            pen_width = 1
        painter.setPen(QPen(border_color, pen_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(0, 0, self._pixmap.width(), self._pixmap.height())

        # Close button (top-right, visible on hover)
        if self._hovered:
            bx = self._pixmap.width() - 20
            by = 4
            painter.setBrush(QColor(243, 139, 168, 200))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bx, by, 16, 16, 3, 3)
            painter.setPen(QPen(QColor("white"), 1.5))
            painter.drawLine(bx + 4, by + 4, bx + 12, by + 12)
            painter.drawLine(bx + 12, by + 4, bx + 4, by + 12)

        # Scale indicator on hover
        if self._hovered:
            pct = f"{int(self._scale * 100)}%"
            painter.setPen(QColor("#cdd6f4"))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.setBrush(QColor(30, 30, 46, 180))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(pct) + 8
            painter.drawRoundedRect(4, self._pixmap.height() - 20, tw, 16, 3, 3)
            painter.drawText(8, self._pixmap.height() - 8, pct)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check close button
            bx = self._pixmap.width() - 20
            by = 4
            if bx <= event.pos().x() <= bx + 16 and by <= event.pos().y() <= by + 16:
                self.close()
                return
            self._dragging = True
            self._drag_start = event.globalPos() - self.pos()
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPos() - self._drag_start)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self._scale = min(self._max_scale, self._scale * 1.1)
        else:
            self._scale = max(self._min_scale, self._scale / 1.1)
        old_center = self.geometry().center()
        self._update_size()
        # Re-center on the same point
        self.move(old_center.x() - self.width() // 2,
                  old_center.y() - self.height() // 2)

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Double-click to reset to 100% scale."""
        if event.button() == Qt.LeftButton:
            self._scale = 1.0
            self._update_size()

    def _show_context_menu(self, pos):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e2e; color: #cdd6f4;
                    border: 1px solid #45475a; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #45475a; }
            QMenu::separator { height: 1px; background-color: #313244; margin: 4px 8px; }
        """)

        copy_act = menu.addAction("Copy to Clipboard")
        copy_act.triggered.connect(self._copy_to_clipboard)

        menu.addSeparator()

        op100 = menu.addAction("100% Opacity")
        op100.triggered.connect(lambda: self._set_opacity(1.0))
        op75 = menu.addAction("75% Opacity")
        op75.triggered.connect(lambda: self._set_opacity(0.75))
        op50 = menu.addAction("50% Opacity")
        op50.triggered.connect(lambda: self._set_opacity(0.50))
        op25 = menu.addAction("25% Opacity")
        op25.triggered.connect(lambda: self._set_opacity(0.25))

        menu.addSeparator()

        zoom_fit = menu.addAction("Reset Zoom (100%)")
        zoom_fit.triggered.connect(lambda: self._set_scale(1.0))
        zoom_50 = menu.addAction("Zoom 50%")
        zoom_50.triggered.connect(lambda: self._set_scale(0.5))
        zoom_200 = menu.addAction("Zoom 200%")
        zoom_200.triggered.connect(lambda: self._set_scale(2.0))

        menu.addSeparator()

        close_act = menu.addAction("Close Pin")
        close_act.triggered.connect(self.close)

        menu.exec_(pos)

    def _copy_to_clipboard(self):
        QApplication.clipboard().setPixmap(self._original_pixmap)

    def _set_opacity(self, val):
        self._opacity = val
        self.setWindowOpacity(val)

    def _set_scale(self, val):
        self._scale = val
        self._update_size()

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self._copy_to_clipboard()
        else:
            super().keyPressEvent(event)
