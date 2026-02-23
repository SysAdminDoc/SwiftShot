"""
SwiftShot Region Selector Overlay
Full-screen translucent overlay for selecting a capture region.
Supports rectangle and freehand modes.

Features: crosshair, pixel coordinates, magnifier with color readout,
dimension display, edge snapping, Space to switch to window mode.
"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QPixmap, QFont, QPainterPath, QPolygon
)
from PyQt5.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal

from utils import virtual_geometry, pixel_color_at, color_to_hex


class RegionSelector(QWidget):
    """Full-screen overlay for region selection."""

    region_selected = pyqtSignal(QRect)
    switch_to_window = pyqtSignal()
    cancelled = pyqtSignal()

    MODE_RECTANGLE = "rectangle"
    MODE_FREEHAND = "freehand"

    # Snap distance in pixels
    SNAP_DISTANCE = 8

    def __init__(self, screenshot: QPixmap, mode="rectangle", parent=None):
        super().__init__(parent)
        self.screenshot = screenshot
        self.mode = mode
        self.selecting = False
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.current_pos = QPoint()

        # Freehand
        self.freehand_points = []

        # Edge snapping
        self._snap_enabled = True
        self._snap_edges_h = []  # horizontal edges (y values)
        self._snap_edges_v = []  # vertical edges (x values)
        self._snapped_x = None
        self._snapped_y = None

        # Color readout
        self._show_color = True
        self._current_color = (0, 0, 0)

        # UI
        self.overlay_color = QColor(0, 0, 0, 120)
        self.selection_border = QColor("#89b4fa")
        self.freehand_color = QColor("#a6e3a1")
        self.crosshair_color = QColor("#cdd6f4")
        self.text_color = QColor("#cdd6f4")
        self.text_bg = QColor(30, 30, 46, 200)
        self.magnifier_size = 120
        self.magnifier_zoom = 4

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

        geo = virtual_geometry()
        self._desktop_geo = geo
        self.setFixedSize(geo.width(), geo.height())
        self.move(geo.x(), geo.y())

        # Pre-detect window edges for snapping
        self._detect_snap_edges()

    def _detect_snap_edges(self):
        """Detect window edges for smart snapping."""
        import sys
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            from ctypes import wintypes, WINFUNCTYPE

            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi

            WNDENUMPROC = WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            edges_h = set()
            edges_v = set()

            def callback(hwnd, lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True

                rect = wintypes.RECT()
                DWMWA = 9
                r = dwmapi.DwmGetWindowAttribute(
                    hwnd, DWMWA, ctypes.byref(rect), ctypes.sizeof(rect)
                )
                if r != 0:
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))

                x, y = rect.left - self._desktop_geo.x(), rect.top - self._desktop_geo.y()
                w = rect.right - rect.left
                h = rect.bottom - rect.top

                if w > 5 and h > 5:
                    edges_v.add(x)
                    edges_v.add(x + w)
                    edges_h.add(y)
                    edges_h.add(y + h)
                return True

            cb = WNDENUMPROC(callback)
            user32.EnumWindows(cb, 0)

            self._snap_edges_v = sorted(edges_v)
            self._snap_edges_h = sorted(edges_h)
        except Exception:
            pass

    def _snap_point(self, pos):
        """Snap a point to nearby window edges."""
        if not self._snap_enabled:
            return pos

        x, y = pos.x(), pos.y()
        sx, sy = x, y
        self._snapped_x = None
        self._snapped_y = None

        for edge_x in self._snap_edges_v:
            if abs(x - edge_x) <= self.SNAP_DISTANCE:
                sx = edge_x
                self._snapped_x = edge_x
                break

        for edge_y in self._snap_edges_h:
            if abs(y - edge_y) <= self.SNAP_DISTANCE:
                sy = edge_y
                self._snapped_y = edge_y
                break

        return QPoint(sx, sy)

    def show_spanning(self):
        self.show()
        if hasattr(self, '_desktop_geo'):
            self.setGeometry(self._desktop_geo)
        self.activateWindow()
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.drawPixmap(0, 0, self.screenshot)

        if self.mode == self.MODE_FREEHAND and self.selecting and self.freehand_points:
            self._draw_freehand_overlay(painter)
        elif self.selecting and self.start_pos != self.end_pos:
            selection = QRect(self.start_pos, self.end_pos).normalized()
            self._draw_overlay_with_hole(painter, selection)
            self._draw_selection_border(painter, selection)
            self._draw_dimensions(painter, selection)
        else:
            painter.fillRect(self.rect(), self.overlay_color)
            self._draw_crosshair(painter)

        # Draw snap guides
        self._draw_snap_guides(painter)

        self._draw_coordinates(painter)
        self._draw_magnifier(painter)
        self._draw_mode_hint(painter)
        painter.end()

    def _draw_snap_guides(self, painter):
        """Draw subtle snap guide lines."""
        if self._snapped_x is not None:
            pen = QPen(QColor("#a6e3a1"), 1, Qt.DotLine)
            painter.setPen(pen)
            painter.drawLine(self._snapped_x, 0, self._snapped_x, self.height())

        if self._snapped_y is not None:
            pen = QPen(QColor("#a6e3a1"), 1, Qt.DotLine)
            painter.setPen(pen)
            painter.drawLine(0, self._snapped_y, self.width(), self._snapped_y)

    def _draw_freehand_overlay(self, painter):
        if len(self.freehand_points) < 2:
            painter.fillRect(self.rect(), self.overlay_color)
            return

        path = QPainterPath()
        path.moveTo(self.freehand_points[0])
        for pt in self.freehand_points[1:]:
            path.lineTo(pt)
        path.closeSubpath()

        bounding = path.boundingRect().toAlignedRect()

        overlay_path = QPainterPath()
        overlay_path.addRect(0, 0, self.width(), self.height())
        hole = QPainterPath()
        hole.addRect(bounding.x(), bounding.y(), bounding.width(), bounding.height())
        overlay_path = overlay_path.subtracted(hole)
        painter.fillPath(overlay_path, self.overlay_color)

        pen = QPen(self.freehand_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        pen = QPen(self.selection_border, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(bounding)

        self._draw_dimensions(painter, bounding)

    def _draw_overlay_with_hole(self, painter, selection):
        path = QPainterPath()
        path.addRect(0, 0, self.width(), self.height())
        hole = QPainterPath()
        hole.addRect(selection.x(), selection.y(),
                     selection.width(), selection.height())
        path = path.subtracted(hole)
        painter.fillPath(path, self.overlay_color)

    def _draw_selection_border(self, painter, selection):
        pen = QPen(self.selection_border, 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(selection)

        handle_size = 6
        handles = [
            selection.topLeft(), selection.topRight(),
            selection.bottomLeft(), selection.bottomRight(),
            QPoint(selection.center().x(), selection.top()),
            QPoint(selection.center().x(), selection.bottom()),
            QPoint(selection.left(), selection.center().y()),
            QPoint(selection.right(), selection.center().y()),
        ]
        painter.setBrush(QColor("#89b4fa"))
        for h in handles:
            painter.drawRect(h.x() - handle_size // 2,
                             h.y() - handle_size // 2,
                             handle_size, handle_size)

    def _draw_dimensions(self, painter, selection):
        w, h = selection.width(), selection.height()
        text = f"{w} x {h}"
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text) + 16
        text_h = fm.height() + 8
        tx = selection.center().x() - text_w // 2
        ty = selection.bottom() + 8
        if ty + text_h > self.height():
            ty = selection.top() - text_h - 8
        tx = max(4, min(tx, self.width() - text_w - 4))
        painter.setBrush(self.text_bg)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(tx, ty, text_w, text_h, 4, 4)
        painter.setPen(self.text_color)
        painter.drawText(tx + 8, ty + fm.ascent() + 4, text)

    def _draw_crosshair(self, painter):
        pos = self.current_pos
        pen = QPen(self.crosshair_color, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(pos.x(), 0, pos.x(), self.height())
        painter.drawLine(0, pos.y(), self.width(), pos.y())

    def _draw_coordinates(self, painter):
        pos = self.current_pos
        # Get pixel color for readout
        r, g, b = pixel_color_at(self.screenshot, pos.x(), pos.y())
        self._current_color = (r, g, b)
        hex_color = color_to_hex(r, g, b)

        text = f"({pos.x()}, {pos.y()})  {hex_color}"
        font = QFont("Consolas", 9)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text) + 28
        text_h = fm.height() + 6
        tx = pos.x() + 16
        ty = pos.y() - text_h - 8
        if tx + text_w > self.width():
            tx = pos.x() - text_w - 16
        if ty < 0:
            ty = pos.y() + 16

        painter.setBrush(self.text_bg)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(tx, ty, text_w, text_h, 3, 3)

        # Color swatch
        painter.setBrush(QColor(r, g, b))
        painter.setPen(QPen(QColor("#585b70"), 1))
        swatch_x = tx + 6
        swatch_y = ty + (text_h - 10) // 2
        painter.drawRect(swatch_x, swatch_y, 10, 10)

        # Text
        painter.setPen(self.text_color)
        painter.drawText(tx + 22, ty + fm.ascent() + 3, text)

    def _draw_magnifier(self, painter):
        pos = self.current_pos
        size = self.magnifier_size
        zoom = self.magnifier_zoom
        src_size = size // zoom
        src_rect = QRect(pos.x() - src_size // 2, pos.y() - src_size // 2,
                         src_size, src_size)
        mag_x = pos.x() + 24
        mag_y = pos.y() + 24
        if mag_x + size + 4 > self.width():
            mag_x = pos.x() - size - 24
        if mag_y + size + 4 > self.height():
            mag_y = pos.y() - size - 24

        cropped = self.screenshot.copy(src_rect)
        magnified = cropped.scaled(size, size, Qt.IgnoreAspectRatio, Qt.FastTransformation)

        painter.setBrush(QColor(30, 30, 46, 230))
        painter.setPen(QPen(self.selection_border, 2))
        painter.drawRoundedRect(mag_x - 2, mag_y - 2, size + 4, size + 4, 4, 4)
        painter.drawPixmap(mag_x, mag_y, magnified)

        center = QPoint(mag_x + size // 2, mag_y + size // 2)
        pen = QPen(QColor("#f38ba8"), 1)
        painter.setPen(pen)
        painter.drawLine(center.x() - 6, center.y(), center.x() + 6, center.y())
        painter.drawLine(center.x(), center.y() - 6, center.x(), center.y() + 6)

        # Pixel grid lines in magnifier
        pen = QPen(QColor(255, 255, 255, 30), 1)
        painter.setPen(pen)
        pixel_size = zoom
        for gx in range(mag_x, mag_x + size, pixel_size):
            painter.drawLine(gx, mag_y, gx, mag_y + size)
        for gy in range(mag_y, mag_y + size, pixel_size):
            painter.drawLine(mag_x, gy, mag_x + size, gy)

    def _draw_mode_hint(self, painter):
        if self.mode == self.MODE_FREEHAND:
            label = "Freehand Region  |  Space: Window Mode  |  S: toggle snap  |  Esc: cancel"
        else:
            label = "Region  |  Space: Window Mode  |  S: toggle snap  |  Esc: cancel"
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 20
        th = fm.height() + 10
        x = (self.width() - tw) // 2
        y = 10
        painter.setBrush(self.text_bg)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(x, y, tw, th, 5, 5)
        painter.setPen(self.text_color)
        painter.drawText(x + 10, y + fm.ascent() + 5, label)

    # --- Mouse Events ---

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selecting = True
            pos = self._snap_point(event.pos()) if self.mode == self.MODE_RECTANGLE else event.pos()
            self.start_pos = pos
            self.end_pos = pos
            if self.mode == self.MODE_FREEHAND:
                self.freehand_points = [event.pos()]
            self.update()
        elif event.button() == Qt.RightButton:
            self.hide()
            QTimer.singleShot(50, lambda: self.cancelled.emit())

    def mouseMoveEvent(self, event):
        self.current_pos = event.pos()
        if self.selecting:
            if self.mode == self.MODE_RECTANGLE:
                self.end_pos = self._snap_point(event.pos())
            else:
                self.end_pos = event.pos()
            if self.mode == self.MODE_FREEHAND:
                self.freehand_points.append(event.pos())
        else:
            # Update snap indicators even when not selecting
            self._snap_point(event.pos())
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            if self.mode == self.MODE_RECTANGLE:
                self.end_pos = self._snap_point(event.pos())
            else:
                self.end_pos = event.pos()

            if self.mode == self.MODE_FREEHAND and self.freehand_points:
                path = QPainterPath()
                path.moveTo(self.freehand_points[0])
                for pt in self.freehand_points[1:]:
                    path.lineTo(pt)
                bounding = path.boundingRect().toAlignedRect()
                if bounding.width() > 2 and bounding.height() > 2:
                    self.hide()
                    QTimer.singleShot(50, lambda r=QRect(bounding): self.region_selected.emit(r))
                else:
                    self.hide()
                    QTimer.singleShot(50, lambda: self.cancelled.emit())
            else:
                selection = QRect(self.start_pos, self.end_pos).normalized()
                if selection.width() > 2 and selection.height() > 2:
                    self.hide()
                    QTimer.singleShot(50, lambda r=QRect(selection): self.region_selected.emit(r))
                else:
                    self.hide()
                    QTimer.singleShot(50, lambda: self.cancelled.emit())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            QTimer.singleShot(50, lambda: self.cancelled.emit())
        elif event.key() == Qt.Key_Space:
            self.hide()
            QTimer.singleShot(50, lambda: self.switch_to_window.emit())
        elif event.key() == Qt.Key_S:
            self._snap_enabled = not self._snap_enabled
            self.update()
        elif event.key() == Qt.Key_C and not self.selecting:
            # Copy color under cursor to clipboard
            r, g, b = self._current_color
            hex_val = color_to_hex(r, g, b)
            QApplication.clipboard().setText(hex_val)
        else:
            super().keyPressEvent(event)
