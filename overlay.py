"""
SwiftShot Region Selector Overlay
Full-screen translucent overlay for selecting a capture region.
Supports two modes:
  - Rectangle (default): drag to select a rectangular area
  - Freehand: draw a freehand shape, captures bounding box

Features: crosshair cursor, pixel coordinates, magnifier, dimension display.
Press Space to switch to interactive window capture mode.
"""

from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QPixmap, QFont, QPainterPath, QPolygon
)
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal


class RegionSelector(QWidget):
    """Full-screen overlay for region selection."""

    region_selected = pyqtSignal(QRect)
    switch_to_window = pyqtSignal()    # Space pressed
    cancelled = pyqtSignal()

    MODE_RECTANGLE = "rectangle"
    MODE_FREEHAND = "freehand"

    def __init__(self, screenshot: QPixmap, mode="rectangle", parent=None):
        super().__init__(parent)
        self.screenshot = screenshot
        self.mode = mode
        self.selecting = False
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.current_pos = QPoint()

        # Freehand points
        self.freehand_points = []

        # UI settings
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

        # Span ALL monitors using the virtual desktop geometry.
        # We use show() + setGeometry() instead of showFullScreen() because
        # showFullScreen() forces the window onto a single monitor.
        desktop = QApplication.desktop()
        if desktop:
            geo = desktop.geometry()
            self._desktop_geo = geo
            self.setFixedSize(geo.width(), geo.height())
            self.move(geo.x(), geo.y())
        else:
            self._desktop_geo = self.screen().geometry() if self.screen() else QRect(0, 0, 1920, 1080)

    def show_spanning(self):
        """Show the overlay spanning all monitors. Use this instead of show()/showFullScreen()."""
        self.show()
        # Re-apply geometry after show() in case the WM adjusted it
        if hasattr(self, '_desktop_geo'):
            geo = self._desktop_geo
            self.setGeometry(geo)
        self.activateWindow()
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw screenshot as background
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

        self._draw_coordinates(painter)
        self._draw_magnifier(painter)
        self._draw_mode_hint(painter)
        painter.end()

    def _draw_freehand_overlay(self, painter):
        """Draw freehand path with dark overlay outside."""
        if len(self.freehand_points) < 2:
            painter.fillRect(self.rect(), self.overlay_color)
            return

        # Build path from freehand points
        path = QPainterPath()
        path.moveTo(self.freehand_points[0])
        for pt in self.freehand_points[1:]:
            path.lineTo(pt)
        path.closeSubpath()

        # Get bounding rect
        bounding = path.boundingRect().toAlignedRect()

        # Dark overlay with hole at bounding rect
        overlay_path = QPainterPath()
        overlay_path.addRect(0, 0, self.width(), self.height())
        hole = QPainterPath()
        hole.addRect(bounding.x(), bounding.y(), bounding.width(), bounding.height())
        overlay_path = overlay_path.subtracted(hole)
        painter.fillPath(overlay_path, self.overlay_color)

        # Draw the freehand path
        pen = QPen(self.freehand_color, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # Draw bounding rect dashed outline
        pen = QPen(self.selection_border, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRect(bounding)

        # Dimensions
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
        text = f"({pos.x()}, {pos.y()})"
        font = QFont("Consolas", 9)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(text) + 12
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
        painter.setPen(self.text_color)
        painter.drawText(tx + 6, ty + fm.ascent() + 3, text)

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

    def _draw_mode_hint(self, painter):
        """Show mode and Space toggle hint."""
        if self.mode == self.MODE_FREEHAND:
            label = "Freehand Region  |  Space: switch to Window Mode  |  Esc: cancel"
        else:
            label = "Region  |  Space: switch to Window Mode  |  Esc: cancel"
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
            self.start_pos = event.pos()
            self.end_pos = event.pos()
            if self.mode == self.MODE_FREEHAND:
                self.freehand_points = [event.pos()]
            self.update()
        elif event.button() == Qt.RightButton:
            self.cancelled.emit()

    def mouseMoveEvent(self, event):
        self.current_pos = event.pos()
        if self.selecting:
            self.end_pos = event.pos()
            if self.mode == self.MODE_FREEHAND:
                self.freehand_points.append(event.pos())
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.selecting:
            self.selecting = False
            self.end_pos = event.pos()

            if self.mode == self.MODE_FREEHAND and self.freehand_points:
                # Use bounding rect of freehand path
                path = QPainterPath()
                path.moveTo(self.freehand_points[0])
                for pt in self.freehand_points[1:]:
                    path.lineTo(pt)
                bounding = path.boundingRect().toAlignedRect()
                if bounding.width() > 2 and bounding.height() > 2:
                    self.region_selected.emit(bounding)
                else:
                    self.cancelled.emit()
            else:
                selection = QRect(self.start_pos, self.end_pos).normalized()
                if selection.width() > 2 and selection.height() > 2:
                    self.region_selected.emit(selection)
                else:
                    self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
        elif event.key() == Qt.Key_Space:
            self.switch_to_window.emit()
        else:
            super().keyPressEvent(event)
