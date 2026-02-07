"""
SwiftShot Window Picker - Greenshot-exact interactive window capture.

Matches Greenshot's CaptureForm.cs behavior precisely:
  - MediumSeaGreen semi-transparent overlay (ARGB 50,60,179,113)
  - Subtle black border pen (ARGB 50,0,0,0)
  - 700ms Quintic ease-out animation from cursor to window bounds
  - PgDown to drill into child window elements
  - PgUp to return to parent level
  - Space to toggle to region capture mode
  - Z to toggle zoom magnifier
  - Arrow keys to nudge cursor 1px, Ctrl+Arrow 10px
  - Enter/Click to confirm, Escape to cancel
  - Pre-enumerate windows to avoid self-detection issues
"""

import sys
import time
import ctypes
from ctypes import wintypes, byref, POINTER, WINFUNCTYPE
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QFont, QCursor
from PyQt5.QtCore import Qt, QRect, QRectF, QPoint, QTimer, pyqtSignal

from utils import virtual_geometry


# ---------------------------------------------------------------------------
# Rectangle Animator (matches Greenshot's RectangleAnimator)
# ---------------------------------------------------------------------------

class RectAnimator:
    """Animates a rectangle with Quintic ease-out over 700ms."""

    def __init__(self, duration_ms=700):
        self.duration = duration_ms / 1000.0
        self.start_rect = QRectF()
        self.end_rect = QRectF()
        self.current_rect = QRectF()
        self.start_time = 0.0
        self.active = False

    def animate_to(self, target):
        target = QRectF(target)
        if self.current_rect.isEmpty():
            self.current_rect = QRectF(target)
            self.end_rect = QRectF(target)
            return
        if target == self.end_rect:
            return
        self.start_rect = QRectF(self.current_rect)
        self.end_rect = QRectF(target)
        self.start_time = time.monotonic()
        self.active = True

    def animate_from_cursor(self, cursor_pos, target):
        target = QRectF(target)
        self.start_rect = QRectF(cursor_pos.x(), cursor_pos.y(), 0, 0)
        self.end_rect = QRectF(target)
        self.current_rect = QRectF(self.start_rect)
        self.start_time = time.monotonic()
        self.active = True

    def tick(self):
        if not self.active:
            return False
        elapsed = time.monotonic() - self.start_time
        t = min(1.0, elapsed / self.duration)
        e = self._quintic_ease_out(t)
        x = self.start_rect.x() + (self.end_rect.x() - self.start_rect.x()) * e
        y = self.start_rect.y() + (self.end_rect.y() - self.start_rect.y()) * e
        w = self.start_rect.width() + (self.end_rect.width() - self.start_rect.width()) * e
        h = self.start_rect.height() + (self.end_rect.height() - self.start_rect.height()) * e
        self.current_rect = QRectF(x, y, w, h)
        if t >= 1.0:
            self.active = False
            self.current_rect = QRectF(self.end_rect)
        return True

    @staticmethod
    def _quintic_ease_out(t):
        t = t - 1.0
        return t * t * t * t * t + 1.0


# ---------------------------------------------------------------------------
# Window Picker Overlay
# ---------------------------------------------------------------------------

WNDENUMPROC = WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


class WindowPicker(QWidget):
    """Greenshot-exact interactive window capture overlay."""

    element_selected = pyqtSignal(QRect)
    switch_to_region = pyqtSignal()
    cancelled = pyqtSignal()

    GREEN_FILL = QColor(60, 179, 113, 50)
    OVERLAY_PEN = QColor(0, 0, 0, 50)
    DARK_OVERLAY = QColor(0, 0, 0, 40)

    def __init__(self, screenshot: QPixmap, parent=None):
        super().__init__(parent)
        self.screenshot = screenshot
        self.current_pos = QPoint()

        self._top_windows = []
        self._child_cache = {}
        self._parent_stack = []
        self._current_hwnd = 0
        self._current_rect = QRect()

        self._animator = RectAnimator(duration_ms=700)
        self._first_highlight = True
        self._show_magnifier = False
        self._magnifier_size = 120
        self._magnifier_zoom = 4
        self._own_hwnd = 0

        geo = virtual_geometry()
        self._desktop_offset = QPoint(geo.x(), geo.y())
        self._desktop_geo = geo
        self.setFixedSize(geo.width(), geo.height())
        self.move(geo.x(), geo.y())

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint |
            Qt.Tool | Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

        if sys.platform == 'win32':
            self._setup_win32()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(16)

    def show_spanning(self):
        self.show()
        if hasattr(self, '_desktop_geo'):
            self.setGeometry(self._desktop_geo)
        self.activateWindow()
        self.raise_()

    def _setup_win32(self):
        self.user32 = ctypes.windll.user32
        self.dwmapi = ctypes.windll.dwmapi
        self.user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, POINTER(wintypes.RECT)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user32.GetWindow.restype = wintypes.HWND
        self.user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetParent.argtypes = [wintypes.HWND]
        self.user32.GetParent.restype = wintypes.HWND

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(50, self._init_windows)

    def _init_windows(self):
        if sys.platform != 'win32':
            return
        self._own_hwnd = int(self.winId())
        self._top_windows = []

        def enum_cb(hwnd, lparam):
            if hwnd == self._own_hwnd:
                return True
            if not self.user32.IsWindowVisible(hwnd):
                return True
            title_len = self.user32.GetWindowTextLengthW(hwnd)
            if title_len == 0:
                return True
            rect = self._get_win_rect(hwnd)
            if rect.width() < 5 or rect.height() < 5:
                return True
            self._top_windows.append((hwnd, rect))
            return True

        proc = WNDENUMPROC(enum_cb)
        self.user32.EnumWindows(proc, 0)
        self.current_pos = self.mapFromGlobal(QCursor.pos())
        self._update_highlight()

    def _get_win_rect(self, hwnd):
        rect = wintypes.RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        r = self.dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, byref(rect), ctypes.sizeof(rect)
        )
        if r != 0:
            self.user32.GetWindowRect(hwnd, byref(rect))
        return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def _to_display(self, screen_rect):
        return QRect(
            screen_rect.x() - self._desktop_offset.x(),
            screen_rect.y() - self._desktop_offset.y(),
            screen_rect.width(), screen_rect.height()
        )

    def _enum_direct_children(self, parent_hwnd):
        if parent_hwnd in self._child_cache:
            return self._child_cache[parent_hwnd]
        GW_CHILD, GW_HWNDNEXT = 5, 2
        children = []
        child = self.user32.GetWindow(parent_hwnd, GW_CHILD)
        while child:
            if self.user32.IsWindowVisible(child):
                rect = self._get_win_rect(child)
                if rect.width() > 2 and rect.height() > 2:
                    children.append((child, rect))
            child = self.user32.GetWindow(child, GW_HWNDNEXT)
        self._child_cache[parent_hwnd] = children
        return children

    def _find_window_at(self, sx, sy):
        if not self._parent_stack:
            for hwnd, rect in self._top_windows:
                if rect.contains(sx, sy):
                    return hwnd, rect
        else:
            parent = self._parent_stack[-1]
            for hwnd, rect in self._enum_direct_children(parent):
                if rect.contains(sx, sy):
                    return hwnd, rect
            parent_rect = self._get_win_rect(parent)
            return parent, parent_rect
        return 0, QRect()

    def _update_highlight(self):
        if sys.platform != 'win32':
            return
        screen_pos = self.mapToGlobal(self.current_pos)
        hwnd, screen_rect = self._find_window_at(screen_pos.x(), screen_pos.y())
        if hwnd and screen_rect.width() > 0:
            disp = self._to_display(screen_rect)
            if hwnd != self._current_hwnd:
                self._current_hwnd = hwnd
                self._current_rect = screen_rect
                if self._first_highlight:
                    self._animator.animate_from_cursor(self.current_pos, disp)
                    self._first_highlight = False
                else:
                    self._animator.animate_to(disp)
        elif hwnd == 0:
            self._current_hwnd = 0
            self._current_rect = QRect()

    def _page_down(self):
        if not self._current_hwnd:
            return
        children = self._enum_direct_children(self._current_hwnd)
        if children:
            self._parent_stack.append(self._current_hwnd)
            self._current_hwnd = 0
            self._first_highlight = True
            self._update_highlight()

    def _page_up(self):
        if not self._parent_stack:
            return
        parent = self._parent_stack.pop()
        self._child_cache.pop(parent, None)
        self._current_hwnd = 0
        self._first_highlight = True
        self._update_highlight()

    def _nudge_cursor(self, dx, dy):
        pos = QCursor.pos()
        QCursor.setPos(pos.x() + dx, pos.y() + dy)
        self.current_pos = self.mapFromGlobal(QCursor.pos())
        self._update_highlight()

    def _on_tick(self):
        if self._animator.tick():
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self.screenshot)
        painter.fillRect(self.rect(), self.DARK_OVERLAY)

        hr = self._animator.current_rect
        if not hr.isEmpty() and hr.width() > 1 and hr.height() > 1:
            ir = QRect(int(hr.x()), int(hr.y()), int(hr.width()), int(hr.height()))
            src = ir.intersected(self.screenshot.rect())
            if not src.isEmpty():
                painter.drawPixmap(src.topLeft(), self.screenshot.copy(src))
            painter.fillRect(ir, self.GREEN_FILL)
            painter.setPen(QPen(self.OVERLAY_PEN, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(ir)

        if self._show_magnifier:
            self._draw_magnifier(painter)

        # Mode hints
        hints = []
        if self._parent_stack:
            depth = len(self._parent_stack)
            hints.append(f"Child level {depth}  |  PgUp: back  |  PgDown: deeper")
        hints.append("Space: Region Mode  |  Z: magnifier  |  Esc: cancel")

        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        fm = painter.fontMetrics()

        for i, txt in enumerate(hints):
            tw, th = fm.horizontalAdvance(txt) + 20, fm.height() + 10
            if i == 0 and self._parent_stack:
                x, y = self.width() - tw - 12, self.height() - th - 12
            else:
                x, y = (self.width() - tw) // 2, 10 + i * (th + 4)
            painter.setBrush(QColor(30, 30, 46, 200))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, y, tw, th, 4, 4)
            painter.setPen(QColor(205, 214, 244))
            painter.drawText(x + 10, y + fm.ascent() + 5, txt)

        painter.end()

    def _draw_magnifier(self, painter):
        pos = self.current_pos
        sz = self._magnifier_size
        zm = self._magnifier_zoom
        src_sz = sz // zm
        src = QRect(pos.x() - src_sz // 2, pos.y() - src_sz // 2, src_sz, src_sz)
        mx, my = pos.x() + 24, pos.y() + 24
        if mx + sz + 4 > self.width():
            mx = pos.x() - sz - 24
        if my + sz + 4 > self.height():
            my = pos.y() - sz - 24
        mag = self.screenshot.copy(src).scaled(sz, sz, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        painter.setBrush(QColor(30, 30, 46, 230))
        painter.setPen(QPen(QColor(60, 179, 113, 180), 2))
        painter.drawRoundedRect(mx - 2, my - 2, sz + 4, sz + 4, 4, 4)
        painter.drawPixmap(mx, my, mag)
        cx, cy = mx + sz // 2, my + sz // 2
        painter.setPen(QPen(QColor(255, 80, 80), 1))
        painter.drawLine(cx - 8, cy, cx + 8, cy)
        painter.drawLine(cx, cy - 8, cx, cy + 8)

    def mouseMoveEvent(self, event):
        self.current_pos = event.pos()
        self._update_highlight()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._current_rect.isEmpty():
                self._timer.stop()
                self.hide()  # Hide immediately so screen is unblocked
                result_rect = self._to_display(self._current_rect)
                # Defer signal emission -- closing from inside mousePressEvent
                # with BypassWindowManagerHint can freeze the screen
                QTimer.singleShot(50, lambda: self.element_selected.emit(result_rect))
        elif event.button() == Qt.RightButton:
            self._timer.stop()
            self.hide()
            QTimer.singleShot(50, lambda: self.cancelled.emit())

    def keyPressEvent(self, event):
        key = event.key()
        step = 10 if event.modifiers() & Qt.ControlModifier else 1
        if key == Qt.Key_Escape:
            self._timer.stop()
            self.hide()
            QTimer.singleShot(50, lambda: self.cancelled.emit())
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            if not self._current_rect.isEmpty():
                self._timer.stop()
                self.hide()
                result_rect = self._to_display(self._current_rect)
                QTimer.singleShot(50, lambda: self.element_selected.emit(result_rect))
        elif key == Qt.Key_Space:
            self._timer.stop()
            self.switch_to_region.emit()
        elif key == Qt.Key_PageDown:
            self._page_down()
        elif key == Qt.Key_PageUp:
            self._page_up()
        elif key == Qt.Key_Z:
            self._show_magnifier = not self._show_magnifier
            self.update()
        elif key == Qt.Key_Up:
            self._nudge_cursor(0, -step)
        elif key == Qt.Key_Down:
            self._nudge_cursor(0, step)
        elif key == Qt.Key_Left:
            self._nudge_cursor(-step, 0)
        elif key == Qt.Key_Right:
            self._nudge_cursor(step, 0)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
