"""
SwiftShot Pin Window
Always-on-top borderless mini-window for pinned screenshots.
Drag to move, scroll to resize, right-click context menu.
"""

import math

from PyQt5.QtWidgets import (
    QWidget, QApplication, QMenu, QToolButton
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QColor, QPen, QCursor, QFont, QKeySequence, QPalette
)
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal

from config import config


MAX_PIN_RENDER_PIXELS = 16_000_000
MAX_PIN_RENDER_DIMENSION = 8_192
PIN_SCREEN_FRACTION = 0.85


class PinWindow(QWidget):
    """Always-on-top floating screenshot window."""

    closed = pyqtSignal(object)  # emits self

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        if pixmap is None or pixmap.isNull():
            raise ValueError("A pinned screenshot must contain image pixels")
        self._original_pixmap = pixmap.copy()
        self._pixmap = pixmap.copy()
        original_pixels = pixmap.width() * pixmap.height()
        pixel_scale = math.sqrt(MAX_PIN_RENDER_PIXELS / original_pixels)
        dimension_scale = min(
            MAX_PIN_RENDER_DIMENSION / pixmap.width(),
            MAX_PIN_RENDER_DIMENSION / pixmap.height(),
        )
        self._max_scale = max(0.01, min(5.0, pixel_scale, dimension_scale))

        cursor_screen = QApplication.screenAt(QCursor.pos())
        cursor_screen = cursor_screen or QApplication.primaryScreen()
        fit_scale = 1.0
        if cursor_screen is not None:
            available = cursor_screen.availableGeometry()
            fit_scale = min(
                available.width() * PIN_SCREEN_FRACTION / pixmap.width(),
                available.height() * PIN_SCREEN_FRACTION / pixmap.height(),
            )
        self._scale = max(0.01, min(1.0, self._max_scale, fit_scale))
        self._min_scale = min(0.1, self._scale)
        self._dragging = False
        self._drag_start = QPoint()
        self._hovered = False
        self._opacity = config.PIN_OPACITY / 100.0
        try:
            from theme import is_high_contrast_enabled
            self._high_contrast = is_high_contrast_enabled()
        except ImportError:
            self._high_contrast = False

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Pinned screenshot")
        self.setAccessibleDescription(
            "Pinned screenshot. Arrow keys move, plus and minus zoom, Home "
            "resets zoom, Ctrl+C copies, Shift+F10 opens options, and Escape closes.")
        self.setCursor(Qt.SizeAllCursor)
        self.setWindowOpacity(self._opacity)

        self._close_button = QToolButton(self)
        self._close_button.setText("×")
        self._close_button.setAccessibleName("Close pinned screenshot")
        self._close_button.setToolTip("Close pinned screenshot")
        self._close_button.setFocusPolicy(Qt.StrongFocus)
        self._close_button.setFixedSize(28, 28)
        self._close_button.setCursor(Qt.PointingHandCursor)
        self._close_button.setStyleSheet(
            "QToolButton { background: palette(button); color: palette(button-text); "
            "border: 1px solid palette(window-text); border-radius: 4px; "
            "font-size: 18px; font-weight: bold; }"
            "QToolButton:hover, QToolButton:focus { border: 2px solid palette(highlight); }"
        )
        self._close_button.clicked.connect(self.close)

        self._update_size()
        self._center_on_cursor()

    def _center_on_cursor(self):
        pos = QCursor.pos()
        x = pos.x() - self.width() // 2
        y = pos.y() - self.height() // 2
        screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = min(max(x, available.left()),
                    available.right() - self.width() + 1)
            y = min(max(y, available.top()),
                    available.bottom() - self.height() + 1)
        self.move(x, y)

    def _update_size(self):
        self._scale = max(self._min_scale, min(self._max_scale, self._scale))
        w = max(50, int(self._original_pixmap.width() * self._scale))
        h = max(50, int(self._original_pixmap.height() * self._scale))
        self._pixmap = self._original_pixmap.scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setFixedSize(self._pixmap.width() + 4, self._pixmap.height() + 4)
        self._close_button.setGeometry(self._close_rect())

    def _close_rect(self):
        """Stable, WCAG-sized pointer target for the close action."""
        return QRect(max(0, self.width() - 32), 4, 28, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Shadow
        painter.fillRect(3, 3, self.width() - 3, self.height() - 3, QColor(0, 0, 0, 40))

        # Image
        painter.drawPixmap(0, 0, self._pixmap)

        # Border
        border_color = (self.palette().color(QPalette.WindowText)
                        if self._high_contrast else QColor(config.PIN_BORDER_COLOR))
        if self.hasFocus():
            border_color = self.palette().color(QPalette.Highlight)
            pen_width = 3
        elif self._hovered:
            border_color.setAlpha(220)
            pen_width = 2
        else:
            border_color.setAlpha(100)
            pen_width = 1
        painter.setPen(QPen(border_color, pen_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(0, 0, self._pixmap.width(), self._pixmap.height())

        # Scale indicator on hover
        if self._hovered:
            pct = f"{int(self._scale * 100)}%"
            painter.setPen(self.palette().color(QPalette.ToolTipText))
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            background = self.palette().color(QPalette.ToolTipBase)
            background.setAlpha(220)
            painter.setBrush(background)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(pct) + 8
            painter.drawRoundedRect(4, self._pixmap.height() - 20, tw, 16, 3, 3)
            painter.drawText(8, self._pixmap.height() - 8, pct)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
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
        menu = QMenu(self)

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
        old_center = self.geometry().center()
        self._scale = max(self._min_scale, min(self._max_scale, val))
        self._update_size()
        self.move(old_center.x() - self.width() // 2,
                  old_center.y() - self.height() // 2)

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.matches(QKeySequence.Copy):
            self._copy_to_clipboard()
        elif event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self._set_scale(min(self._max_scale, self._scale * 1.1))
        elif event.key() == Qt.Key_Minus:
            self._set_scale(max(self._min_scale, self._scale / 1.1))
        elif event.key() == Qt.Key_Home:
            self._set_scale(1.0)
        elif event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            dx = (-step if event.key() == Qt.Key_Left else
                  step if event.key() == Qt.Key_Right else 0)
            dy = (-step if event.key() == Qt.Key_Up else
                  step if event.key() == Qt.Key_Down else 0)
            self.move(self.x() + dx, self.y() + dy)
        elif (event.key() == Qt.Key_Menu or
              event.key() == Qt.Key_F10 and event.modifiers() & Qt.ShiftModifier):
            self._show_context_menu(self.mapToGlobal(self.rect().center()))
        else:
            super().keyPressEvent(event)
