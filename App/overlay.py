"""
SwiftShot Region Selector Overlay
Full-screen translucent overlay for selecting a capture region.
Supports rectangle and freehand modes.

Features: crosshair, pixel coordinates, magnifier with color readout,
dimension display, edge snapping, Space to switch to window mode.
"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QPixmap, QFont, QPainterPath, QPalette
)
from PyQt5.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal

from utils import virtual_geometry, color_to_hex, exclude_window_from_capture


class RegionSelector(QWidget):
    """Full-screen overlay for region selection."""

    region_selected = pyqtSignal(QRect)
    # Emits (points, bounding_rect) so the capture can be masked to the
    # drawn shape instead of silently degrading to a rectangle.
    freehand_selected = pyqtSignal(object)
    switch_to_window = pyqtSignal()
    cancelled = pyqtSignal()

    MODE_RECTANGLE = "rectangle"
    MODE_FREEHAND = "freehand"

    # Snap distance in pixels
    SNAP_DISTANCE = 8

    # Aspect-ratio presets cycled with the "A" key. Values are width/height;
    # None means free-form. (R-22 keyboard-complete region capture.)
    ASPECT_PRESETS = [
        (None, "Free"), (1 / 1, "1:1"), (4 / 3, "4:3"), (16 / 9, "16:9"),
        (3 / 2, "3:2"), (2 / 3, "2:3"), (9 / 16, "9:16"),
    ]

    def __init__(self, screenshot: QPixmap, mode="rectangle", parent=None):
        super().__init__(parent)
        self.screenshot = screenshot
        # Cache the QImage once: converting the full multi-monitor pixmap
        # on every repaint (for the color readout) is a large copy.
        self._screenshot_image = screenshot.toImage()
        self.mode = mode
        self.selecting = False
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.current_pos = QPoint()
        self._generation = 0

        # Freehand
        self.freehand_points = []

        # Aspect lock (R-22): index into ASPECT_PRESETS; ratio is width/height.
        self._aspect_index = 0
        self.aspect_ratio = None

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
        self.guide_color = QColor("#a6e3a1")
        self.handle_color = QColor("#89b4fa")
        self.swatch_border = QColor("#585b70")
        self.magnifier_bg = QColor(30, 30, 46, 230)
        self.magnifier_cross = QColor("#f38ba8")
        self.magnifier_grid = QColor(255, 255, 255, 30)
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
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(
            "Freehand capture region" if mode == self.MODE_FREEHAND
            else "Rectangular capture region")
        self.setAccessibleDescription(
            "Move the crosshair with the arrow keys. Press Enter to start, "
            "resize with arrows (Shift = coarse), Ctrl+arrows to move the whole "
            "region, D to type an exact width×height, A to cycle an aspect-ratio "
            "lock, then press Enter to capture. Escape cancels; Space switches "
            "to window capture; S toggles snapping.")

        geo = virtual_geometry()
        self._desktop_geo = geo
        self.setFixedSize(geo.width(), geo.height())
        self.move(geo.x(), geo.y())
        self.current_pos = QPoint(max(0, self.width() // 2),
                                  max(0, self.height() // 2))

        try:
            from theme import is_high_contrast_enabled
            if is_high_contrast_enabled():
                palette = self.palette()
                self.overlay_color = palette.color(QPalette.Window)
                self.overlay_color.setAlpha(180)
                self.selection_border = palette.color(QPalette.Highlight)
                self.freehand_color = palette.color(QPalette.Highlight)
                self.crosshair_color = palette.color(QPalette.WindowText)
                self.text_color = palette.color(QPalette.ToolTipText)
                self.text_bg = palette.color(QPalette.ToolTipBase)
                self.text_bg.setAlpha(240)
                self.guide_color = palette.color(QPalette.Highlight)
                self.handle_color = palette.color(QPalette.Highlight)
                self.swatch_border = palette.color(QPalette.WindowText)
                self.magnifier_bg = palette.color(QPalette.Window)
                self.magnifier_bg.setAlpha(245)
                self.magnifier_cross = palette.color(QPalette.Highlight)
                self.magnifier_grid = palette.color(QPalette.WindowText)
                self.magnifier_grid.setAlpha(80)
        except ImportError:
            pass

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
            user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
            user32.EnumWindows.restype = wintypes.BOOL
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.restype = wintypes.BOOL
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int
            user32.GetWindowRect.argtypes = [
                wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
            user32.GetWindowRect.restype = wintypes.BOOL
            dwmapi.DwmGetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                wintypes.DWORD]
            dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

            edges_h = set()
            edges_v = set()

            def callback(hwnd, lparam):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                # Skip DWM-cloaked windows (other virtual desktops, suspended
                # UWP) — they'd contribute snap edges at invisible positions.
                cloaked = wintypes.DWORD(0)
                if dwmapi.DwmGetWindowAttribute(
                        hwnd, 14, ctypes.byref(cloaked),
                        ctypes.sizeof(cloaked)) == 0 and cloaked.value:
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
        self._generation += 1
        self.show()
        exclude_window_from_capture(self)
        if hasattr(self, '_desktop_geo'):
            self.setGeometry(self._desktop_geo)
        self.activateWindow()
        self.raise_()
        self.setFocus(Qt.ActiveWindowFocusReason)

    def _defer_emit(self, signal, payload=None, has_payload=False):
        """Emit only if this hidden overlay still owns the capture action."""
        generation = self._generation
        self.hide()

        def emit_if_current():
            if generation != self._generation or self.isVisible():
                return
            if has_payload:
                signal.emit(payload)
            else:
                signal.emit()

        QTimer.singleShot(50, emit_if_current)

    def closeEvent(self, event):
        self._generation += 1
        super().closeEvent(event)

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
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(self.palette().color(QPalette.Highlight), 3))
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        painter.end()

    def _draw_snap_guides(self, painter):
        """Draw subtle snap guide lines."""
        if self._snapped_x is not None:
            pen = QPen(self.guide_color, 1, Qt.DotLine)
            painter.setPen(pen)
            painter.drawLine(self._snapped_x, 0, self._snapped_x, self.height())

        if self._snapped_y is not None:
            pen = QPen(self.guide_color, 1, Qt.DotLine)
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
        painter.setBrush(self.handle_color)
        for h in handles:
            painter.drawRect(h.x() - handle_size // 2,
                             h.y() - handle_size // 2,
                             handle_size, handle_size)

    def _draw_dimensions(self, painter, selection):
        w, h = selection.width(), selection.height()
        text = f"{w} x {h}"
        if self.mode == self.MODE_RECTANGLE and self.aspect_ratio:
            text += f"  [{self.ASPECT_PRESETS[self._aspect_index][1]}]"
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
        # Get pixel color for readout (from the cached QImage)
        img = self._screenshot_image
        if 0 <= pos.x() < img.width() and 0 <= pos.y() < img.height():
            c = img.pixelColor(pos.x(), pos.y())
            r, g, b = c.red(), c.green(), c.blue()
        else:
            r, g, b = 0, 0, 0
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
        painter.setPen(QPen(self.swatch_border, 1))
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

        painter.setBrush(self.magnifier_bg)
        painter.setPen(QPen(self.selection_border, 2))
        painter.drawRoundedRect(mag_x - 2, mag_y - 2, size + 4, size + 4, 4, 4)
        # Scale directly from the source rect -- no intermediate copy
        painter.drawPixmap(QRect(mag_x, mag_y, size, size),
                           self.screenshot, src_rect)

        center = QPoint(mag_x + size // 2, mag_y + size // 2)
        pen = QPen(self.magnifier_cross, 1)
        painter.setPen(pen)
        painter.drawLine(center.x() - 6, center.y(), center.x() + 6, center.y())
        painter.drawLine(center.x(), center.y() - 6, center.x(), center.y() + 6)

        # Pixel grid lines in magnifier
        pen = QPen(self.magnifier_grid, 1)
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
            aspect = self.ASPECT_PRESETS[self._aspect_index][1]
            label = (f"Region  |  D: size  |  A: aspect [{aspect}]  |  "
                     "Ctrl+arrows: move  |  S: snap  |  Space: Window  |  Esc: cancel")
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
            self.setFocus(Qt.MouseFocusReason)
            self.selecting = True
            pos = self._snap_point(event.pos()) if self.mode == self.MODE_RECTANGLE else event.pos()
            self.start_pos = pos
            self.end_pos = pos
            if self.mode == self.MODE_FREEHAND:
                self.freehand_points = [event.pos()]
            self.update()
        elif event.button() == Qt.RightButton:
            self._defer_emit(self.cancelled)

    def mouseMoveEvent(self, event):
        self.current_pos = event.pos()
        if self.selecting:
            if self.mode == self.MODE_RECTANGLE:
                self.end_pos = self._apply_aspect_to_end(
                    self._snap_point(event.pos()))
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
                self.end_pos = self._apply_aspect_to_end(
                    self._snap_point(event.pos()))
            else:
                self.end_pos = event.pos()

            self._finish_selection()

    def _finish_selection(self):
        if self.mode == self.MODE_FREEHAND and self.freehand_points:
            path = QPainterPath()
            path.moveTo(self.freehand_points[0])
            for pt in self.freehand_points[1:]:
                path.lineTo(pt)
            bounding = path.boundingRect().toAlignedRect()
            if bounding.width() > 2 and bounding.height() > 2:
                points = [QPoint(p) for p in self.freehand_points]
                self._defer_emit(
                    self.freehand_selected, (points, QRect(bounding)),
                    has_payload=True)
            else:
                self._defer_emit(self.cancelled)
            return
        selection = QRect(self.start_pos, self.end_pos).normalized()
        if selection.width() > 2 and selection.height() > 2:
            self._defer_emit(
                self.region_selected, QRect(selection), has_payload=True)
        else:
            self._defer_emit(self.cancelled)

    # --- Keyboard region geometry (R-22) ---

    @staticmethod
    def _fit_to_ratio(w, h, ratio):
        """Adjust (w, h) so w/h == ratio, deriving height from width. ratio is
        width/height; None/<=0 leaves the size untouched."""
        w = max(1, int(round(w))); h = max(1, int(round(h)))
        if not ratio or ratio <= 0:
            return w, h
        return w, max(1, int(round(w / ratio)))

    @staticmethod
    def _clamp_rect(x, y, w, h, max_w, max_h):
        """Clamp a rect (origin x,y, size w,h) inside 0..max. Keeps the origin
        and shrinks the size to fit — predictable, always on-screen."""
        x = max(0, min(int(x), max_w - 1)); y = max(0, min(int(y), max_h - 1))
        w = max(1, min(int(w), max_w - x)); h = max(1, min(int(h), max_h - y))
        return x, y, w, h

    @staticmethod
    def _translate_rect(x, y, w, h, dx, dy, max_w, max_h):
        """Move a rect by (dx, dy) without letting it leave the bounds or change
        size (it stops at the edge)."""
        x = max(0, min(int(x) + dx, max_w - w))
        y = max(0, min(int(y) + dy, max_h - h))
        return x, y, w, h

    @staticmethod
    def _parse_dimensions(text):
        """Parse 'WxH' / 'W H' / 'W,H' / 'W×H' into (w, h) ints, else None."""
        import re
        m = re.match(r"^\s*(\d+)\s*[x×,\s]\s*(\d+)\s*$", text or "", re.I)
        if not m:
            return None
        w, h = int(m.group(1)), int(m.group(2))
        return (w, h) if w >= 1 and h >= 1 else None

    def _current_rect(self):
        return QRect(self.start_pos, self.end_pos).normalized()

    def _apply_aspect_to_end(self, end):
        """Constrain a drag endpoint so the selection honours the active aspect
        lock: height follows the dragged width, keeping the drag's vertical
        direction, clamped to the overlay."""
        if not self.aspect_ratio or self.mode != self.MODE_RECTANGLE:
            return end
        w = abs(end.x() - self.start_pos.x()) + 1
        h = max(1, int(round(w / self.aspect_ratio)))
        sy = 1 if end.y() >= self.start_pos.y() else -1
        y = self.start_pos.y() + sy * (h - 1)
        return QPoint(end.x(), max(0, min(self.height() - 1, y)))

    def _set_selection_rect(self, x, y, w, h):
        """Point the selection at a clamped rect and refresh the readouts."""
        x, y, w, h = self._clamp_rect(x, y, w, h, self.width(), self.height())
        self.selecting = True
        # QRect(topLeft, bottomRight) is inclusive, so the far corner is
        # (x+w-1, y+h-1) — this makes the captured rect exactly w×h.
        self.start_pos = QPoint(x, y)
        self.end_pos = QPoint(x + w - 1, y + h - 1)
        self.current_pos = QPoint(x + w - 1, y + h - 1)
        lock = self.ASPECT_PRESETS[self._aspect_index][1]
        self.setAccessibleDescription(
            f"Selection {w} by {h} pixels at {x}, {y}. Aspect lock {lock}. "
            "Press Enter to capture.")
        self.update()

    def _cycle_aspect(self):
        self._aspect_index = (self._aspect_index + 1) % len(self.ASPECT_PRESETS)
        self.aspect_ratio = self.ASPECT_PRESETS[self._aspect_index][0]
        if self.selecting and self.aspect_ratio:
            r = self._current_rect()
            w, h = self._fit_to_ratio(r.width(), r.height(), self.aspect_ratio)
            self._set_selection_rect(r.x(), r.y(), w, h)
        else:
            self.update()

    def _prompt_dimensions(self):
        from PyQt5.QtWidgets import QInputDialog
        r = self._current_rect() if self.selecting else \
            QRect(self.current_pos, self.current_pos)
        default = f"{max(r.width(), 1)}x{max(r.height(), 1)}"
        text, ok = QInputDialog.getText(
            self, "Exact Dimensions",
            "Width x Height (e.g. 1920x1080):", text=default)
        if not ok:
            return
        dims = self._parse_dimensions(text)
        if not dims:
            return
        w, h = dims
        if self.aspect_ratio:
            w, h = self._fit_to_ratio(w, h, self.aspect_ratio)
        anchor = self.start_pos if self.selecting else self.current_pos
        self._set_selection_rect(anchor.x(), anchor.y(), w, h)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._defer_emit(self.cancelled)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.selecting:
                self.selecting = False
                self._finish_selection()
            else:
                self.selecting = True
                self.start_pos = QPoint(self.current_pos)
                self.end_pos = QPoint(self.current_pos)
                if self.mode == self.MODE_FREEHAND:
                    self.freehand_points = [QPoint(self.current_pos)]
                self.update()
        elif event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            dx = (-step if event.key() == Qt.Key_Left else
                  step if event.key() == Qt.Key_Right else 0)
            dy = (-step if event.key() == Qt.Key_Up else
                  step if event.key() == Qt.Key_Down else 0)
            ctrl = bool(event.modifiers() & Qt.ControlModifier)
            if self.selecting and ctrl and self.mode == self.MODE_RECTANGLE:
                # Ctrl+arrows move the whole region without resizing it.
                r = self._current_rect()
                x, y, w, h = self._translate_rect(
                    r.x(), r.y(), r.width(), r.height(), dx, dy,
                    self.width(), self.height())
                self._set_selection_rect(x, y, w, h)
            elif self.selecting and self.mode == self.MODE_RECTANGLE:
                # Plain/Shift arrows resize the bottom-right edge; re-apply the
                # aspect lock so height tracks width.
                r = self._current_rect()
                w = max(1, r.width() + dx); h = max(1, r.height() + dy)
                if self.aspect_ratio:
                    w, h = self._fit_to_ratio(w, h, self.aspect_ratio)
                self._set_selection_rect(r.x(), r.y(), w, h)
            else:
                moved = QPoint(
                    max(0, min(self.width() - 1, self.current_pos.x() + dx)),
                    max(0, min(self.height() - 1, self.current_pos.y() + dy)))
                self.current_pos = moved
                if self.selecting:
                    self.end_pos = QPoint(moved)
                    if self.mode == self.MODE_FREEHAND:
                        self.freehand_points.append(QPoint(moved))
                self.update()
        elif event.key() == Qt.Key_D and self.mode == self.MODE_RECTANGLE:
            self._prompt_dimensions()
        elif event.key() == Qt.Key_A and self.mode == self.MODE_RECTANGLE:
            self._cycle_aspect()
        elif event.key() == Qt.Key_Space:
            self._defer_emit(self.switch_to_window)
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
