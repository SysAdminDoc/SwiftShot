"""
SwiftShot Image Editor
Full-featured screenshot editor with annotation tools.

Tools: Select, Crop, Rectangle, Ellipse, Line, Arrow, Freehand,
       Text, Highlight, Obfuscate, Step Number, Eraser,
       Eyedropper, Ruler
Features: Undo/Redo, Copy, Save, Print, Zoom, Color picker,
          Recent Colors, Font Picker, Drag-and-Drop Export,
          Border/Shadow/Rounded Corners, Pin, Image Diff,
          Quick-Annotate Templates, Filled Shapes Toggle,
          Brightness/Contrast/Grayscale/Invert Adjustments,
          Dirty State Tracking
"""

import os
import sys
import math
import copy
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
    QAction, QActionGroup, QStatusBar, QLabel, QSpinBox,
    QColorDialog, QFileDialog, QMessageBox, QScrollArea,
    QSizePolicy, QSlider, QComboBox, QToolButton, QMenu,
    QDialog, QDialogButtonBox, QTextEdit, QFormLayout, QFontComboBox,
    QApplication, QPushButton, QInputDialog, QCheckBox, QGridLayout
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QImage, QFont,
    QIcon, QCursor, QPolygon, QPainterPath, QTransform,
    QKeySequence, QFontMetrics, QRadialGradient, QDrag
)
from PyQt5.QtCore import (
    Qt, QRect, QPoint, QPointF, QSize, QRectF, pyqtSignal,
    QBuffer, QIODevice, QMimeData, QByteArray
)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog

from config import config
from logger import log


# ---------------------------------------------------------------------------
# Drawing Element Classes
# ---------------------------------------------------------------------------

class DrawableElement:
    """Base class for all drawable elements."""

    def __init__(self, color=QColor("#f38ba8"), line_width=2):
        self.color = QColor(color)
        self.line_width = line_width
        self.selected = False

    def draw(self, painter):
        raise NotImplementedError

    def bounding_rect(self):
        return QRect()

    def clone(self):
        return copy.deepcopy(self)


class RectElement(DrawableElement):
    def __init__(self, rect, color, line_width, filled=False):
        super().__init__(color, line_width)
        self.rect = QRect(rect)
        self.filled = filled

    def draw(self, painter):
        pen = QPen(self.color, self.line_width)
        painter.setPen(pen)
        if self.filled:
            painter.setBrush(QBrush(self.color))
        else:
            painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect)

    def bounding_rect(self):
        return self.rect


class EllipseElement(DrawableElement):
    def __init__(self, rect, color, line_width, filled=False):
        super().__init__(color, line_width)
        self.rect = QRect(rect)
        self.filled = filled

    def draw(self, painter):
        pen = QPen(self.color, self.line_width)
        painter.setPen(pen)
        if self.filled:
            painter.setBrush(QBrush(self.color))
        else:
            painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self.rect)

    def bounding_rect(self):
        return self.rect


class LineElement(DrawableElement):
    def __init__(self, p1, p2, color, line_width):
        super().__init__(color, line_width)
        self.p1 = QPoint(p1)
        self.p2 = QPoint(p2)

    def draw(self, painter):
        pen = QPen(self.color, self.line_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(self.p1, self.p2)

    def bounding_rect(self):
        return QRect(self.p1, self.p2).normalized()


class ArrowElement(DrawableElement):
    def __init__(self, p1, p2, color, line_width):
        super().__init__(color, line_width)
        self.p1 = QPoint(p1)
        self.p2 = QPoint(p2)

    def draw(self, painter):
        pen = QPen(self.color, self.line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QBrush(self.color))
        painter.drawLine(self.p1, self.p2)

        dx = self.p2.x() - self.p1.x()
        dy = self.p2.y() - self.p1.y()
        angle = math.atan2(dy, dx)
        arrow_len = max(12, self.line_width * 5)
        arrow_angle = math.pi / 6

        ax1 = self.p2.x() - arrow_len * math.cos(angle - arrow_angle)
        ay1 = self.p2.y() - arrow_len * math.sin(angle - arrow_angle)
        ax2 = self.p2.x() - arrow_len * math.cos(angle + arrow_angle)
        ay2 = self.p2.y() - arrow_len * math.sin(angle + arrow_angle)

        arrow = QPolygon([
            self.p2,
            QPoint(int(ax1), int(ay1)),
            QPoint(int(ax2), int(ay2))
        ])
        painter.drawPolygon(arrow)


class FreehandElement(DrawableElement):
    def __init__(self, points, color, line_width):
        super().__init__(color, line_width)
        self.points = [QPoint(p) for p in points]

    def draw(self, painter):
        if len(self.points) < 2:
            return
        pen = QPen(self.color, self.line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        for i in range(1, len(self.points)):
            painter.drawLine(self.points[i - 1], self.points[i])


class TextElement(DrawableElement):
    def __init__(self, pos, text, color, font):
        super().__init__(color)
        self.pos = QPoint(pos)
        self.text = text
        self.font = QFont(font)

    def draw(self, painter):
        painter.setPen(QPen(self.color))
        painter.setFont(self.font)
        lines = self.text.split('\n')
        fm = QFontMetrics(self.font)
        y = self.pos.y()
        for line in lines:
            painter.drawText(self.pos.x(), y, line)
            y += fm.height()


class HighlightElement(DrawableElement):
    def __init__(self, rect, color):
        super().__init__(color)
        self.rect = QRect(rect)

    def draw(self, painter):
        highlight_color = QColor(self.color)
        highlight_color.setAlpha(100)
        painter.fillRect(self.rect, highlight_color)


class ObfuscateElement(DrawableElement):
    def __init__(self, rect, factor=12, source_pixmap=None, mode="pixelate"):
        super().__init__()
        self.rect = QRect(rect)
        self.factor = factor
        self.source_pixmap = source_pixmap
        self.mode = mode

    def draw(self, painter):
        if self.source_pixmap is None:
            return
        r = self.rect.normalized()
        if r.width() < 1 or r.height() < 1:
            return

        cropped = self.source_pixmap.copy(r)

        if self.mode == "blur":
            for _ in range(3):
                small = cropped.scaled(
                    max(1, r.width() // 4), max(1, r.height() // 4),
                    Qt.IgnoreAspectRatio, Qt.SmoothTransformation
                )
                cropped = small.scaled(
                    r.width(), r.height(),
                    Qt.IgnoreAspectRatio, Qt.SmoothTransformation
                )
        else:
            small = cropped.scaled(
                max(1, r.width() // self.factor),
                max(1, r.height() // self.factor),
                Qt.IgnoreAspectRatio, Qt.FastTransformation
            )
            cropped = small.scaled(
                r.width(), r.height(),
                Qt.IgnoreAspectRatio, Qt.FastTransformation
            )

        painter.drawPixmap(r.topLeft(), cropped)

    def clone(self):
        elem = ObfuscateElement(
            QRect(self.rect), self.factor, self.source_pixmap, self.mode
        )
        elem.color = QColor(self.color)
        elem.line_width = self.line_width
        return elem


class StepNumberElement(DrawableElement):
    def __init__(self, pos, number, color, size=28):
        super().__init__(color)
        self.pos = QPoint(pos)
        self.number = number
        self.size = size

    def draw(self, painter):
        r = QRect(
            self.pos.x() - self.size // 2,
            self.pos.y() - self.size // 2,
            self.size, self.size
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(r)

        painter.setPen(QPen(QColor("white")))
        font = QFont("Segoe UI", self.size // 3, QFont.Bold)
        painter.setFont(font)
        painter.drawText(r, Qt.AlignCenter, str(self.number))


class RulerElement(DrawableElement):
    def __init__(self, p1, p2, color, line_width=2):
        super().__init__(color, line_width)
        self.p1 = QPoint(p1)
        self.p2 = QPoint(p2)

    def draw(self, painter):
        pen = QPen(self.color, self.line_width, Qt.DashDotLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(self.p1, self.p2)

        marker_size = 6
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(self.p1, marker_size // 2, marker_size // 2)
        painter.drawEllipse(self.p2, marker_size // 2, marker_size // 2)

        dx = self.p2.x() - self.p1.x()
        dy = self.p2.y() - self.p1.y()
        dist = math.sqrt(dx * dx + dy * dy)
        text = f"{dist:.1f} px"
        if abs(dx) > 5 or abs(dy) > 5:
            text += f"  ({abs(dx)} x {abs(dy)})"

        mid = QPoint((self.p1.x() + self.p2.x()) // 2,
                      (self.p1.y() + self.p2.y()) // 2)

        font = QFont("Consolas", 9)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(text) + 12
        th = fm.height() + 6

        bg_rect = QRect(mid.x() - tw // 2, mid.y() - th - 4, tw, th)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 30, 46, 200))
        painter.drawRoundedRect(bg_rect, 4, 4)

        painter.setPen(self.color)
        painter.drawText(bg_rect, Qt.AlignCenter, text)

    def bounding_rect(self):
        return QRect(self.p1, self.p2).normalized()


# ---------------------------------------------------------------------------
# Enhanced Text Input Dialog with font picker
# ---------------------------------------------------------------------------

class MultiLineTextDialog(QDialog):
    """Dialog for entering multi-line text annotations with font controls."""

    def __init__(self, font=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Text")
        self.setMinimumSize(440, 300)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; background: transparent; }
            QTextEdit {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 8px; font-size: 11pt;
            }
            QFontComboBox, QSpinBox {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 4px;
                padding: 4px;
            }
            QCheckBox { color: #cdd6f4; spacing: 6px; }
            QPushButton {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 6px 16px;
            }
            QPushButton:hover { background-color: #45475a; border-color: #89b4fa; }
        """)

        layout = QVBoxLayout(self)

        # Font controls row
        font_row = QHBoxLayout()

        self.font_combo = QFontComboBox()
        if font:
            self.font_combo.setCurrentFont(font)
        font_row.addWidget(self.font_combo)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(font.pointSize() if font else 14)
        self.size_spin.setSuffix(" pt")
        font_row.addWidget(self.size_spin)

        self.bold_check = QCheckBox("B")
        self.bold_check.setStyleSheet(
            "QCheckBox { font-weight: bold; font-size: 12pt; }")
        if font:
            self.bold_check.setChecked(font.bold())
        font_row.addWidget(self.bold_check)

        self.italic_check = QCheckBox("I")
        self.italic_check.setStyleSheet(
            "QCheckBox { font-style: italic; font-size: 12pt; }")
        if font:
            self.italic_check.setChecked(font.italic())
        font_row.addWidget(self.italic_check)

        layout.addLayout(font_row)

        # Text area
        lbl = QLabel("Enter text (multi-line supported):")
        lbl.setFont(QFont("Segoe UI", 10))
        layout.addWidget(lbl)

        self.text_edit = QTextEdit()
        if font:
            self.text_edit.setFont(font)
        layout.addWidget(self.text_edit)

        # Update preview font as user changes options
        self.font_combo.currentFontChanged.connect(self._update_preview_font)
        self.size_spin.valueChanged.connect(self._update_preview_font)
        self.bold_check.toggled.connect(self._update_preview_font)
        self.italic_check.toggled.connect(self._update_preview_font)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.text_edit.setFocus()

    def _update_preview_font(self, _=None):
        f = self.get_font()
        self.text_edit.setFont(f)

    def get_text(self):
        return self.text_edit.toPlainText()

    def get_font(self):
        f = QFont(self.font_combo.currentFont())
        f.setPointSize(self.size_spin.value())
        f.setBold(self.bold_check.isChecked())
        f.setItalic(self.italic_check.isChecked())
        return f


# ---------------------------------------------------------------------------
# Recent Colors Widget
# ---------------------------------------------------------------------------

class RecentColorsWidget(QWidget):
    """Row of small color buttons showing recently used colors."""

    color_selected = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._buttons = []
        self.refresh()

    def refresh(self):
        """Rebuild buttons from config."""
        for btn in self._buttons:
            btn.deleteLater()
        self._buttons.clear()

        for hex_color in config.EDITOR_RECENT_COLORS[:12]:
            btn = QPushButton()
            btn.setFixedSize(18, 18)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(hex_color.upper())
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_color}; "
                f"border: 1px solid #45475a; border-radius: 3px; }}"
                f"QPushButton:hover {{ border: 2px solid #89b4fa; }}"
            )
            color = QColor(hex_color)
            btn.clicked.connect(lambda checked, c=color: self.color_selected.emit(c))
            self._layout.addWidget(btn)
            self._buttons.append(btn)

        self._layout.addStretch()


# ---------------------------------------------------------------------------
# Canvas Widget
# ---------------------------------------------------------------------------

class EditorCanvas(QWidget):
    """The drawing canvas where the screenshot and annotations are displayed."""

    zoom_changed = pyqtSignal(float)
    dirty_changed = pyqtSignal(bool)
    color_picked = pyqtSignal(QColor)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap.copy()
        self.base_pixmap = pixmap.copy()
        self.elements = []
        self.undo_stack = []
        self.redo_stack = []
        self._dirty = False

        self.zoom_level = 1.0
        self.current_tool = "select"
        self.current_color = QColor(config.EDITOR_DEFAULT_COLOR)
        self.current_line_width = config.EDITOR_DEFAULT_LINE_WIDTH
        self.current_font = QFont(
            config.EDITOR_DEFAULT_FONT_FAMILY,
            config.EDITOR_DEFAULT_FONT_SIZE
        )
        self.highlight_color = QColor(config.EDITOR_HIGHLIGHT_COLOR)
        self.step_counter = 1
        self.filled_shapes = False

        # Image diff overlay
        self._diff_pixmap = None
        self._diff_opacity = 0.5
        self._diff_enabled = False

        # Interaction state
        self.drawing = False
        self.draw_start = QPoint()
        self.draw_end = QPoint()
        self.freehand_points = []
        self.temp_element = None

        # Crop state
        self.crop_rect = None
        self.crop_active = False

        # Pan state
        self.panning = False
        self.pan_start = QPoint()
        self.pan_scroll_start_h = 0
        self.pan_scroll_start_v = 0
        self.space_held = False

        # Drag-and-drop state
        self._drag_start_pos = None

        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._update_size()

    @property
    def dirty(self):
        return self._dirty

    @dirty.setter
    def dirty(self, value):
        if self._dirty != value:
            self._dirty = value
            self.dirty_changed.emit(value)

    def _update_size(self):
        size = self.base_pixmap.size() * self.zoom_level
        self.setMinimumSize(size)
        self.setMaximumSize(size)
        self.resize(size)
        self.update()

    def set_zoom(self, level):
        self.zoom_level = max(0.25, min(4.0, level))
        self._update_size()
        self.zoom_changed.emit(self.zoom_level)

    def _to_image_coords(self, pos):
        return QPoint(
            int(pos.x() / self.zoom_level),
            int(pos.y() / self.zoom_level)
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        painter.scale(self.zoom_level, self.zoom_level)

        painter.drawPixmap(0, 0, self.base_pixmap)

        if self._diff_enabled and self._diff_pixmap:
            painter.setOpacity(self._diff_opacity)
            scaled_diff = self._diff_pixmap.scaled(
                self.base_pixmap.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            painter.drawPixmap(0, 0, scaled_diff)
            painter.setOpacity(1.0)

        for elem in self.elements:
            elem.draw(painter)

        if self.temp_element:
            self.temp_element.draw(painter)

        if self.crop_active and self.crop_rect:
            self._draw_crop_overlay(painter)

        painter.end()

    def _draw_crop_overlay(self, painter):
        rect = self.crop_rect.normalized()
        path = QPainterPath()
        path.addRect(QRectF(self.base_pixmap.rect()))
        inner = QPainterPath()
        inner.addRect(QRectF(rect))
        path = path.subtracted(inner)
        painter.fillPath(path, QColor(0, 0, 0, 150))

        pen = QPen(QColor("#a6e3a1"), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)

        pen = QPen(QColor(255, 255, 255, 80), 1, Qt.DotLine)
        painter.setPen(pen)
        w3 = rect.width() / 3
        h3 = rect.height() / 3
        for i in range(1, 3):
            x = rect.left() + w3 * i
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
            y = rect.top() + h3 * i
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

    def _get_scroll_area(self):
        parent = self.parent()
        while parent:
            from PyQt5.QtWidgets import QScrollArea
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return None

    def _start_pan(self, event):
        self.panning = True
        self.pan_start = event.globalPos()
        scroll = self._get_scroll_area()
        if scroll:
            self.pan_scroll_start_h = scroll.horizontalScrollBar().value()
            self.pan_scroll_start_v = scroll.verticalScrollBar().value()
        self.setCursor(Qt.ClosedHandCursor)

    def _should_pan(self, event):
        if self.space_held:
            return True
        if self.current_tool == "select":
            return True
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._start_pan(event)
            return

        if event.button() != Qt.LeftButton:
            return

        if self._should_pan(event):
            self._drag_start_pos = event.pos()
            self._start_pan(event)
            return

        pos = self._to_image_coords(event.pos())
        self.drawing = True
        self.draw_start = pos
        self.draw_end = pos

        if self.current_tool == "freehand":
            self.freehand_points = [pos]
        elif self.current_tool == "crop":
            self.crop_active = True
            self.crop_rect = QRect(pos, pos)
        elif self.current_tool == "text":
            self._insert_text(pos)
            self.drawing = False
        elif self.current_tool == "step":
            self._insert_step(pos)
            self.drawing = False
        elif self.current_tool == "eyedropper":
            self._pick_color(pos)
            self.drawing = False

    def mouseMoveEvent(self, event):
        # Drag-and-drop: if in select mode and dragging far enough, start drag
        if (self.panning and self._drag_start_pos is not None and
                self.current_tool == "select" and not self.space_held):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            if dist > 30:
                self._start_drag_export()
                self.panning = False
                self._drag_start_pos = None
                return

        if self.panning:
            delta = event.globalPos() - self.pan_start
            scroll = self._get_scroll_area()
            if scroll:
                scroll.horizontalScrollBar().setValue(
                    self.pan_scroll_start_h - delta.x()
                )
                scroll.verticalScrollBar().setValue(
                    self.pan_scroll_start_v - delta.y()
                )
            return

        if not self.drawing:
            return

        pos = self._to_image_coords(event.pos())
        self.draw_end = pos

        if self.current_tool == "freehand":
            self.freehand_points.append(pos)
            self.temp_element = FreehandElement(
                list(self.freehand_points),
                self.current_color, self.current_line_width
            )
        elif self.current_tool == "crop":
            self.crop_rect = QRect(self.draw_start, pos)
        elif self.current_tool == "rect":
            self.temp_element = RectElement(
                QRect(self.draw_start, pos).normalized(),
                self.current_color, self.current_line_width,
                self.filled_shapes
            )
        elif self.current_tool == "ellipse":
            self.temp_element = EllipseElement(
                QRect(self.draw_start, pos).normalized(),
                self.current_color, self.current_line_width,
                self.filled_shapes
            )
        elif self.current_tool == "line":
            self.temp_element = LineElement(
                self.draw_start, pos,
                self.current_color, self.current_line_width
            )
        elif self.current_tool == "arrow":
            self.temp_element = ArrowElement(
                self.draw_start, pos,
                self.current_color, self.current_line_width
            )
        elif self.current_tool == "highlight":
            self.temp_element = HighlightElement(
                QRect(self.draw_start, pos).normalized(),
                self.highlight_color
            )
        elif self.current_tool == "obfuscate":
            self.temp_element = ObfuscateElement(
                QRect(self.draw_start, pos).normalized(),
                config.EDITOR_OBFUSCATE_FACTOR,
                self.base_pixmap,
                config.EDITOR_OBFUSCATE_MODE
            )
        elif self.current_tool == "ruler":
            self.temp_element = RulerElement(
                self.draw_start, pos,
                self.current_color, self.current_line_width
            )

        self.update()

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None

        if self.panning and (event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton):
            self.panning = False
            if self.current_tool == "select" or self.space_held:
                self.setCursor(Qt.OpenHandCursor)
            return

        if event.button() != Qt.LeftButton or not self.drawing:
            return

        self.drawing = False
        pos = self._to_image_coords(event.pos())
        self.draw_end = pos

        if self.current_tool == "crop":
            self.crop_rect = QRect(self.draw_start, pos).normalized()
            self.update()
            return

        element = self.temp_element
        self.temp_element = None

        if element:
            self._save_undo_state()
            self.elements.append(element)
            self.redo_stack.clear()
            self.dirty = True

        self.update()

    def _start_drag_export(self):
        """Initiate drag-and-drop of the current image out of the editor."""
        try:
            final = self.get_final_image()
            drag = QDrag(self)
            mime = QMimeData()
            mime.setImageData(final.toImage())
            drag.setMimeData(mime)
            # Thumbnail for drag cursor
            thumb = final.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            drag.setPixmap(thumb)
            drag.exec_(Qt.CopyAction)
            log.info("Drag-and-drop export initiated")
        except Exception as e:
            log.error(f"Drag-and-drop failed: {e}")

    def _insert_text(self, pos):
        dlg = MultiLineTextDialog(self.current_font, self.parent())
        if dlg.exec_() == QDialog.Accepted:
            text = dlg.get_text()
            if text:
                self.current_font = dlg.get_font()
                self._save_undo_state()
                elem = TextElement(pos, text, self.current_color, self.current_font)
                self.elements.append(elem)
                self.redo_stack.clear()
                self.dirty = True
                self.update()

    def _insert_step(self, pos):
        self._save_undo_state()
        elem = StepNumberElement(pos, self.step_counter, self.current_color)
        self.elements.append(elem)
        self.step_counter += 1
        self.redo_stack.clear()
        self.dirty = True
        self.update()

    def _pick_color(self, pos):
        img = self.base_pixmap.toImage()
        if 0 <= pos.x() < img.width() and 0 <= pos.y() < img.height():
            color = QColor(img.pixel(pos.x(), pos.y()))
            self.current_color = color
            self.color_picked.emit(color)

    def confirm_crop(self):
        if not self.crop_rect:
            return
        rect = self.crop_rect.normalized()
        if rect.width() < 1 or rect.height() < 1:
            return
        self._save_undo_state()
        self._flatten_elements()
        self.base_pixmap = self.base_pixmap.copy(rect)
        self.crop_rect = None
        self.crop_active = False
        self.redo_stack.clear()
        self.dirty = True
        self._update_size()

    def cancel_crop(self):
        self.crop_rect = None
        self.crop_active = False
        self.update()

    def _flatten_elements(self):
        if not self.elements:
            return
        painter = QPainter(self.base_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        for elem in self.elements:
            elem.draw(painter)
        painter.end()
        self.elements.clear()

    def _save_undo_state(self):
        state = {
            'base_pixmap': self.base_pixmap.copy(),
            'elements': [e.clone() for e in self.elements],
            'step_counter': self.step_counter,
        }
        self.undo_stack.append(state)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return
        current = {
            'base_pixmap': self.base_pixmap.copy(),
            'elements': [e.clone() for e in self.elements],
            'step_counter': self.step_counter,
        }
        self.redo_stack.append(current)
        state = self.undo_stack.pop()
        self.base_pixmap = state['base_pixmap']
        self.elements = state['elements']
        self.step_counter = state['step_counter']
        self.dirty = True
        self._update_size()

    def redo(self):
        if not self.redo_stack:
            return
        current = {
            'base_pixmap': self.base_pixmap.copy(),
            'elements': [e.clone() for e in self.elements],
            'step_counter': self.step_counter,
        }
        self.undo_stack.append(current)
        state = self.redo_stack.pop()
        self.base_pixmap = state['base_pixmap']
        self.elements = state['elements']
        self.step_counter = state['step_counter']
        self.dirty = True
        self._update_size()

    def get_final_image(self):
        result = self.base_pixmap.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        for elem in self.elements:
            elem.draw(painter)
        painter.end()
        return result

    def reset_step_counter(self):
        self.step_counter = 1

    def rotate_image(self, degrees):
        self._save_undo_state()
        self._flatten_elements()
        transform = QTransform().rotate(degrees)
        self.base_pixmap = self.base_pixmap.transformed(transform, Qt.SmoothTransformation)
        self.redo_stack.clear()
        self.dirty = True
        self._update_size()

    def flip_horizontal(self):
        self._save_undo_state()
        self._flatten_elements()
        transform = QTransform().scale(-1, 1)
        self.base_pixmap = self.base_pixmap.transformed(transform)
        self.redo_stack.clear()
        self.dirty = True
        self.update()

    def flip_vertical(self):
        self._save_undo_state()
        self._flatten_elements()
        transform = QTransform().scale(1, -1)
        self.base_pixmap = self.base_pixmap.transformed(transform)
        self.redo_stack.clear()
        self.dirty = True
        self.update()

    def auto_crop(self):
        self._save_undo_state()
        self._flatten_elements()

        image = self.base_pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        w, h = image.width(), image.height()
        if w < 3 or h < 3:
            return

        bpl = image.bytesPerLine()
        ptr = image.bits()
        ptr.setsize(h * bpl)
        data = bytes(ptr)

        bg_b, bg_g, bg_r = data[0], data[1], data[2]
        tolerance = 30

        def row_is_bg(y):
            offset = y * bpl
            for x in range(w):
                px = offset + x * 4
                if (abs(data[px] - bg_b) >= tolerance or
                    abs(data[px + 1] - bg_g) >= tolerance or
                    abs(data[px + 2] - bg_r) >= tolerance):
                    return False
            return True

        def col_is_bg(x):
            base = x * 4
            for y in range(h):
                px = y * bpl + base
                if (abs(data[px] - bg_b) >= tolerance or
                    abs(data[px + 1] - bg_g) >= tolerance or
                    abs(data[px + 2] - bg_r) >= tolerance):
                    return False
            return True

        top, bottom, left, right = 0, h - 1, 0, w - 1

        for y in range(h):
            if not row_is_bg(y):
                top = y
                break
        for y in range(h - 1, -1, -1):
            if not row_is_bg(y):
                bottom = y
                break
        for x in range(w):
            if not col_is_bg(x):
                left = x
                break
        for x in range(w - 1, -1, -1):
            if not col_is_bg(x):
                right = x
                break

        if right > left and bottom > top:
            crop_rect = QRect(left, top, right - left + 1, bottom - top + 1)
            self.base_pixmap = self.base_pixmap.copy(crop_rect)
            self.redo_stack.clear()
            self.dirty = True
            self._update_size()

    def add_border(self):
        self._save_undo_state()
        self._flatten_elements()

        bw = config.BORDER_WIDTH
        color = QColor(config.BORDER_COLOR)
        w = self.base_pixmap.width() + bw * 2
        h = self.base_pixmap.height() + bw * 2

        result = QPixmap(w, h)
        result.fill(color)
        painter = QPainter(result)
        painter.drawPixmap(bw, bw, self.base_pixmap)
        painter.end()

        self.base_pixmap = result
        self.redo_stack.clear()
        self.dirty = True
        self._update_size()

    def add_shadow(self):
        self._save_undo_state()
        self._flatten_elements()

        shadow_r = config.SHADOW_RADIUS
        shadow_color = QColor(config.SHADOW_COLOR)
        shadow_color.setAlpha(config.SHADOW_OPACITY)
        pad = shadow_r * 2

        w = self.base_pixmap.width() + pad * 2
        h = self.base_pixmap.height() + pad * 2

        result = QPixmap(w, h)
        result.fill(Qt.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        for i in range(shadow_r, 0, -2):
            alpha = int(shadow_color.alpha() * (1 - i / shadow_r))
            c = QColor(shadow_color.red(), shadow_color.green(), shadow_color.blue(), alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            painter.drawRoundedRect(
                pad - i + 3, pad - i + 3,
                self.base_pixmap.width() + i * 2,
                self.base_pixmap.height() + i * 2,
                4, 4
            )

        painter.drawPixmap(pad, pad, self.base_pixmap)
        painter.end()

        self.base_pixmap = result
        self.redo_stack.clear()
        self.dirty = True
        self._update_size()

    def add_rounded_corners(self):
        self._save_undo_state()
        self._flatten_elements()

        radius = config.ROUNDED_CORNERS_RADIUS
        w, h = self.base_pixmap.width(), self.base_pixmap.height()

        result = QPixmap(w, h)
        result.fill(Qt.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self.base_pixmap)
        painter.end()

        self.base_pixmap = result
        self.redo_stack.clear()
        self.dirty = True
        self._update_size()

    def apply_grayscale(self):
        self._save_undo_state()
        self._flatten_elements()
        img = self.base_pixmap.toImage().convertToFormat(QImage.Format_Grayscale8)
        self.base_pixmap = QPixmap.fromImage(img.convertToFormat(QImage.Format_ARGB32))
        self.redo_stack.clear()
        self.dirty = True
        self.update()

    def apply_invert(self):
        self._save_undo_state()
        self._flatten_elements()
        img = self.base_pixmap.toImage()
        img.invertPixels()
        self.base_pixmap = QPixmap.fromImage(img)
        self.redo_stack.clear()
        self.dirty = True
        self.update()

    def apply_brightness(self, delta):
        """Adjust brightness by delta (-100 to +100)."""
        self._save_undo_state()
        self._flatten_elements()
        img = self.base_pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        w, h = img.width(), img.height()
        bpl = img.bytesPerLine()
        ptr = img.bits()
        ptr.setsize(h * bpl)
        data = bytearray(ptr)

        for y in range(h):
            for x in range(w):
                px = y * bpl + x * 4
                for c in range(3):  # B, G, R
                    data[px + c] = max(0, min(255, data[px + c] + delta))

        new_img = QImage(bytes(data), w, h, bpl, QImage.Format_ARGB32)
        self.base_pixmap = QPixmap.fromImage(new_img)
        self.redo_stack.clear()
        self.dirty = True
        self.update()

    def set_diff_image(self, pixmap):
        self._diff_pixmap = pixmap
        self._diff_enabled = True
        self.update()

    def toggle_diff(self):
        self._diff_enabled = not self._diff_enabled
        self.update()

    def set_diff_opacity(self, value):
        self._diff_opacity = value / 100.0
        self.update()


# ---------------------------------------------------------------------------
# Color Button
# ---------------------------------------------------------------------------

class ColorButton(QPushButton):
    color_changed = pyqtSignal(QColor)

    def __init__(self, color=QColor("#f38ba8"), parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick_color)
        self._update_style()

    def _update_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._color.name()};
                border: 2px solid #45475a; border-radius: 4px;
                min-width: 24px; max-width: 24px;
            }}
            QPushButton:hover {{ border-color: #89b4fa; }}
        """)

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Choose Color")
        if color.isValid():
            self._color = color
            self._update_style()
            self.color_changed.emit(color)
            config.add_recent_color(color.name())

    def color(self):
        return self._color

    def set_color(self, color):
        self._color = color
        self._update_style()


# ---------------------------------------------------------------------------
# Image Editor Window
# ---------------------------------------------------------------------------

class ImageEditor(QMainWindow):
    """Full-featured image editor window."""

    def __init__(self, pixmap: QPixmap, app_controller=None, parent=None):
        super().__init__(parent)
        self.app_controller = app_controller
        self.saved_path = None

        self.setWindowTitle("SwiftShot Editor")
        self.setMinimumSize(800, 600)

        self.canvas = EditorCanvas(pixmap)
        self.canvas.dirty_changed.connect(self._on_dirty_changed)
        self.canvas.color_picked.connect(self._on_color_picked)

        # Main layout: recent colors bar + scroll area
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Recent colors bar
        self.recent_colors = RecentColorsWidget()
        self.recent_colors.color_selected.connect(self._on_recent_color)
        self.recent_colors.setStyleSheet("background: #181825; padding: 2px 4px;")
        central_layout.addWidget(self.recent_colors)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.canvas)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #11111b; border: none; }")
        central_layout.addWidget(self.scroll_area)

        self.setCentralWidget(central)

        self._create_menubar()
        self._create_toolbar()
        self._create_statusbar()

        if config.WINDOW_GEOMETRY:
            try:
                parts = config.WINDOW_GEOMETRY.split(',')
                self.setGeometry(int(parts[0]), int(parts[1]),
                                 int(parts[2]), int(parts[3]))
            except (ValueError, IndexError):
                self._center_window()
        else:
            self._center_window()

        self.canvas.zoom_changed.connect(self._update_zoom_label)

    def _on_dirty_changed(self, dirty):
        title = "SwiftShot Editor"
        if dirty:
            title += " *"
        self.setWindowTitle(title)

    def _on_color_picked(self, color):
        self.color_btn.set_color(color)
        self.canvas.current_color = color
        config.add_recent_color(color.name())
        self.recent_colors.refresh()
        self.statusBar().showMessage(
            f"  Color picked: {color.name().upper()}", 3000
        )

    def _on_recent_color(self, color):
        self.color_btn.set_color(color)
        self.canvas.current_color = color

    def _center_window(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            w = min(self.canvas.base_pixmap.width() + 100, geo.width() - 100)
            h = min(self.canvas.base_pixmap.height() + 180, geo.height() - 100)
            x = (geo.width() - w) // 2
            y = (geo.height() - h) // 2
            self.setGeometry(x, y, w, h)

    def _create_menubar(self):
        menubar = self.menuBar()

        # --- File ---
        file_menu = menubar.addMenu("&File")

        save_action = QAction("&Save As...", self)
        save_action.setShortcut(QKeySequence.SaveAs)
        save_action.triggered.connect(self.save_as)
        file_menu.addAction(save_action)

        save_default = QAction("&Quick Save", self)
        save_default.setShortcut(QKeySequence.Save)
        save_default.triggered.connect(self.quick_save)
        file_menu.addAction(save_default)

        file_menu.addSeparator()

        copy_action = QAction("&Copy to Clipboard", self)
        copy_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_action.triggered.connect(self.copy_to_clipboard)
        file_menu.addAction(copy_action)

        file_menu.addSeparator()

        print_action = QAction("&Print...", self)
        print_action.setShortcut(QKeySequence.Print)
        print_action.triggered.connect(self.print_image)
        file_menu.addAction(print_action)

        file_menu.addSeparator()

        pin_action = QAction("Pin to Desktop", self)
        pin_action.triggered.connect(self._pin_image)
        file_menu.addAction(pin_action)

        file_menu.addSeparator()

        close_action = QAction("Close", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        # --- Edit ---
        edit_menu = menubar.addMenu("&Edit")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(self.canvas.undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(self.canvas.redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        copy_img = QAction("Copy Image", self)
        copy_img.setShortcut(QKeySequence.Copy)
        copy_img.triggered.connect(self.copy_to_clipboard)
        edit_menu.addAction(copy_img)

        edit_menu.addSeparator()

        auto_crop = QAction("Auto-Crop", self)
        auto_crop.triggered.connect(self.canvas.auto_crop)
        edit_menu.addAction(auto_crop)

        confirm_crop = QAction("Confirm Crop", self)
        confirm_crop.setShortcut(QKeySequence("Return"))
        confirm_crop.triggered.connect(self.canvas.confirm_crop)
        edit_menu.addAction(confirm_crop)

        cancel_crop = QAction("Cancel Crop", self)
        cancel_crop.setShortcut(QKeySequence("Escape"))
        cancel_crop.triggered.connect(self.canvas.cancel_crop)
        edit_menu.addAction(cancel_crop)

        # --- Tools ---
        tools_menu = menubar.addMenu("&Tools")

        ocr_action = QAction("Extract Text (OCR)", self)
        ocr_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        ocr_action.triggered.connect(self._run_ocr)
        tools_menu.addAction(ocr_action)

        tools_menu.addSeparator()

        reset_steps = QAction("Reset Step Counter", self)
        reset_steps.triggered.connect(self.canvas.reset_step_counter)
        tools_menu.addAction(reset_steps)

        # --- Image ---
        image_menu = menubar.addMenu("&Image")

        rotate_cw = QAction("Rotate 90 CW", self)
        rotate_cw.triggered.connect(lambda: self.canvas.rotate_image(90))
        image_menu.addAction(rotate_cw)

        rotate_ccw = QAction("Rotate 90 CCW", self)
        rotate_ccw.triggered.connect(lambda: self.canvas.rotate_image(-90))
        image_menu.addAction(rotate_ccw)

        image_menu.addSeparator()

        flip_h = QAction("Flip Horizontal", self)
        flip_h.triggered.connect(self.canvas.flip_horizontal)
        image_menu.addAction(flip_h)

        flip_v = QAction("Flip Vertical", self)
        flip_v.triggered.connect(self.canvas.flip_vertical)
        image_menu.addAction(flip_v)

        image_menu.addSeparator()

        # Adjustments submenu
        adj_menu = image_menu.addMenu("Adjustments")

        bright_up = QAction("Increase Brightness", self)
        bright_up.triggered.connect(lambda: self.canvas.apply_brightness(20))
        adj_menu.addAction(bright_up)

        bright_down = QAction("Decrease Brightness", self)
        bright_down.triggered.connect(lambda: self.canvas.apply_brightness(-20))
        adj_menu.addAction(bright_down)

        adj_menu.addSeparator()

        grayscale_act = QAction("Grayscale", self)
        grayscale_act.triggered.connect(self.canvas.apply_grayscale)
        adj_menu.addAction(grayscale_act)

        invert_act = QAction("Invert Colors", self)
        invert_act.triggered.connect(self.canvas.apply_invert)
        adj_menu.addAction(invert_act)

        image_menu.addSeparator()

        # Frame submenu
        frame_menu = image_menu.addMenu("Frame")

        border_act = QAction("Add Border", self)
        border_act.triggered.connect(self.canvas.add_border)
        frame_menu.addAction(border_act)

        shadow_act = QAction("Add Shadow", self)
        shadow_act.triggered.connect(self.canvas.add_shadow)
        frame_menu.addAction(shadow_act)

        rounded_act = QAction("Round Corners", self)
        rounded_act.triggered.connect(self.canvas.add_rounded_corners)
        frame_menu.addAction(rounded_act)

        image_menu.addSeparator()

        # Diff overlay
        diff_load = QAction("Load Diff Image...", self)
        diff_load.triggered.connect(self._load_diff_image)
        image_menu.addAction(diff_load)

        diff_toggle = QAction("Toggle Diff Overlay", self)
        diff_toggle.setShortcut(QKeySequence("Ctrl+D"))
        diff_toggle.triggered.connect(self.canvas.toggle_diff)
        image_menu.addAction(diff_toggle)

        # --- Templates ---
        template_menu = menubar.addMenu("Te&mplates")

        bug_template = QAction("Bug Report (arrows + steps + obfuscate)", self)
        bug_template.triggered.connect(lambda: self._apply_template("bug"))
        template_menu.addAction(bug_template)

        tutorial_template = QAction("Tutorial (steps + highlight)", self)
        tutorial_template.triggered.connect(lambda: self._apply_template("tutorial"))
        template_menu.addAction(tutorial_template)

        redact_template = QAction("Redact All (full obfuscate)", self)
        redact_template.triggered.connect(lambda: self._apply_template("redact"))
        template_menu.addAction(redact_template)

        # --- View ---
        view_menu = menubar.addMenu("&View")

        zoom_in = QAction("Zoom In", self)
        zoom_in.setShortcut(QKeySequence("Ctrl+="))
        zoom_in.triggered.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_level + 0.25))
        view_menu.addAction(zoom_in)

        zoom_out = QAction("Zoom Out", self)
        zoom_out.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out.triggered.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_level - 0.25))
        view_menu.addAction(zoom_out)

        zoom_fit = QAction("Zoom to Fit", self)
        zoom_fit.setShortcut(QKeySequence("Ctrl+0"))
        zoom_fit.triggered.connect(self._zoom_to_fit)
        view_menu.addAction(zoom_fit)

        zoom_100 = QAction("Zoom 100%", self)
        zoom_100.setShortcut(QKeySequence("Ctrl+1"))
        zoom_100.triggered.connect(lambda: self.canvas.set_zoom(1.0))
        view_menu.addAction(zoom_100)

    def _create_toolbar(self):
        toolbar = QToolBar("Tools")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        tools = [
            ("select",     "Select / Pan / Drag-Export (V)", "V", "pointer"),
            ("crop",       "Crop Region (C)",                "C", "crop"),
            ("rect",       "Rectangle (R)",                  "R", "rect"),
            ("ellipse",    "Ellipse (E)",                    "E", "ellipse"),
            ("line",       "Line (L)",                       "L", "line"),
            ("arrow",      "Arrow (A)",                      "A", "arrow"),
            ("freehand",   "Freehand Pen (F)",               "F", "freehand"),
            ("text",       "Insert Text (T)",                "T", "text"),
            ("highlight",  "Highlight Region (H)",           "H", "highlight"),
            ("obfuscate",  "Obfuscate / Pixelate (O)",       "O", "obfuscate"),
            ("step",       "Step Number Badge (N)",          "N", "step"),
            ("ruler",      "Pixel Ruler / Measure (M)",      "M", "ruler"),
            ("eyedropper", "Eyedropper / Color Pick (I)",    "I", "eyedropper"),
        ]

        for tool_id, tooltip, shortcut, icon_name in tools:
            action = QAction(self._make_tool_icon(icon_name), tooltip, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setData(tool_id)
            action.setToolTip(tooltip)
            action.triggered.connect(lambda checked, tid=tool_id: self._set_tool(tid))
            tool_group.addAction(action)
            toolbar.addAction(action)

            if tool_id == "select":
                action.setChecked(True)

        toolbar.addSeparator()

        # Color picker
        self.color_btn = ColorButton(self.canvas.current_color)
        self.color_btn.color_changed.connect(self._on_color_changed)
        self.color_btn.setToolTip("Drawing Color (click to change)")
        self.color_btn.setAccessibleName("Drawing Color")
        toolbar.addWidget(self.color_btn)

        # Line width
        toolbar.addSeparator()
        lw_label = QLabel(" Width: ")
        lw_label.setStyleSheet("background: transparent;")
        toolbar.addWidget(lw_label)

        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 20)
        self.line_width_spin.setValue(config.EDITOR_DEFAULT_LINE_WIDTH)
        self.line_width_spin.setFixedWidth(60)
        self.line_width_spin.setToolTip("Stroke width for drawing tools")
        self.line_width_spin.setAccessibleName("Line Width")
        self.line_width_spin.valueChanged.connect(
            lambda v: setattr(self.canvas, 'current_line_width', v)
        )
        toolbar.addWidget(self.line_width_spin)

        toolbar.addSeparator()

        # Filled shapes toggle
        self.fill_check = QCheckBox(" Fill")
        self.fill_check.setToolTip("Fill rectangles and ellipses with color")
        self.fill_check.setAccessibleName("Fill Shapes")
        self.fill_check.setStyleSheet("QCheckBox { color: #cdd6f4; background: transparent; spacing: 4px; }")
        self.fill_check.toggled.connect(lambda v: setattr(self.canvas, 'filled_shapes', v))
        toolbar.addWidget(self.fill_check)

        toolbar.addSeparator()

        # Step counter indicator
        self.step_label = QLabel(" Step: 1 ")
        self.step_label.setStyleSheet("background: transparent; color: #f38ba8; font-weight: bold;")
        self.step_label.setToolTip("Current step number for Step Badge tool")
        toolbar.addWidget(self.step_label)

        toolbar.addSeparator()

        # Undo / Redo
        undo_btn = QAction("Undo", self)
        undo_btn.setToolTip("Undo last action (Ctrl+Z)")
        undo_btn.triggered.connect(self.canvas.undo)
        toolbar.addAction(undo_btn)

        redo_btn = QAction("Redo", self)
        redo_btn.setToolTip("Redo last undone action (Ctrl+Y)")
        redo_btn.triggered.connect(self.canvas.redo)
        toolbar.addAction(redo_btn)

        toolbar.addSeparator()

        # Quick actions
        save_btn = QAction("Save", self)
        save_btn.setToolTip("Quick Save (Ctrl+S)")
        save_btn.triggered.connect(self.quick_save)
        toolbar.addAction(save_btn)

        clip_btn = QAction("Clipboard", self)
        clip_btn.setToolTip("Copy image to clipboard (Ctrl+Shift+C)")
        clip_btn.triggered.connect(self.copy_to_clipboard)
        toolbar.addAction(clip_btn)

        print_btn = QAction("Print", self)
        print_btn.setToolTip("Print image (Ctrl+P)")
        print_btn.triggered.connect(self.print_image)
        toolbar.addAction(print_btn)

        toolbar.addSeparator()

        pin_btn = QAction("Pin", self)
        pin_btn.setToolTip("Pin image to desktop as always-on-top window")
        pin_btn.triggered.connect(self._pin_image)
        toolbar.addAction(pin_btn)

        ocr_btn = QAction("OCR", self)
        ocr_btn.setToolTip("Extract text from image (Ctrl+Shift+O)")
        ocr_btn.triggered.connect(self._run_ocr)
        toolbar.addAction(ocr_btn)

        # Frame dropdown
        frame_btn = QToolButton()
        frame_btn.setText("Frame")
        frame_btn.setToolTip("Add border, shadow, or rounded corners")
        frame_btn.setAccessibleName("Frame Options")
        frame_btn.setPopupMode(QToolButton.InstantPopup)
        frame_menu = QMenu()
        frame_menu.setStyleSheet("""
            QMenu { background-color: #1e1e2e; color: #cdd6f4;
                    border: 1px solid #45475a; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #45475a; }
        """)
        frame_menu.addAction("Add Border").triggered.connect(self.canvas.add_border)
        frame_menu.addAction("Add Shadow").triggered.connect(self.canvas.add_shadow)
        frame_menu.addAction("Round Corners").triggered.connect(self.canvas.add_rounded_corners)
        frame_btn.setMenu(frame_menu)
        toolbar.addWidget(frame_btn)

    def _make_tool_icon(self, icon_name):
        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#cdd6f4"), 1.5)
        painter.setPen(pen)

        if icon_name == "pointer":
            points = [QPoint(4, 2), QPoint(4, 16), QPoint(8, 12),
                      QPoint(13, 17), QPoint(15, 15), QPoint(10, 10),
                      QPoint(14, 8), QPoint(4, 2)]
            for i in range(len(points) - 1):
                painter.drawLine(points[i], points[i + 1])
        elif icon_name == "crop":
            painter.drawLine(6, 2, 6, 14)
            painter.drawLine(2, 6, 14, 6)
            painter.drawLine(14, 6, 14, 18)
            painter.drawLine(6, 14, 18, 14)
        elif icon_name == "rect":
            painter.drawRect(3, 4, 14, 12)
        elif icon_name == "ellipse":
            painter.drawEllipse(2, 3, 16, 14)
        elif icon_name == "line":
            painter.drawLine(3, 17, 17, 3)
        elif icon_name == "arrow":
            painter.drawLine(3, 17, 17, 3)
            painter.drawLine(17, 3, 11, 3)
            painter.drawLine(17, 3, 17, 9)
        elif icon_name == "freehand":
            path = QPainterPath()
            path.moveTo(3, 14)
            path.cubicTo(6, 4, 10, 18, 17, 6)
            painter.drawPath(path)
        elif icon_name == "text":
            painter.setFont(QFont("Segoe UI", 14, QFont.Bold))
            painter.drawText(3, 17, "T")
        elif icon_name == "highlight":
            painter.setBrush(QColor("#f9e2af"))
            painter.setPen(Qt.NoPen)
            painter.setOpacity(0.6)
            painter.drawRect(2, 6, 16, 8)
        elif icon_name == "obfuscate":
            for x in range(0, 20, 5):
                for y in range(0, 20, 5):
                    c = QColor("#6c7086") if (x + y) % 10 == 0 else QColor("#45475a")
                    painter.fillRect(x, y, 4, 4, c)
        elif icon_name == "step":
            painter.setBrush(QColor("#f38ba8"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 16, 16)
            painter.setPen(QColor("white"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(QRect(2, 2, 16, 16), Qt.AlignCenter, "1")
        elif icon_name == "ruler":
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(2, 16, 18, 4)
            painter.setBrush(QColor("#cdd6f4"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(1, 15, 4, 4)
            painter.drawEllipse(16, 2, 4, 4)
        elif icon_name == "eyedropper":
            painter.setPen(QPen(QColor("#cdd6f4"), 1.5))
            painter.drawLine(4, 16, 10, 10)
            painter.drawLine(10, 10, 14, 6)
            painter.setBrush(QColor("#89b4fa"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(12, 2, 6, 6)

        painter.end()
        return QIcon(pixmap)

    def _set_tool(self, tool_id):
        self.canvas.current_tool = tool_id

        if tool_id == "select":
            self.canvas.setCursor(Qt.OpenHandCursor)
        elif tool_id == "crop":
            self.canvas.setCursor(Qt.CrossCursor)
        elif tool_id == "text":
            self.canvas.setCursor(Qt.IBeamCursor)
        elif tool_id == "eyedropper":
            self.canvas.setCursor(Qt.CrossCursor)
        else:
            self.canvas.setCursor(Qt.CrossCursor)

        self._update_status()

    def _on_color_changed(self, color):
        self.canvas.current_color = color
        self.recent_colors.refresh()

    def _update_zoom_label(self, zoom):
        self._update_status()

    def _update_status(self):
        img = self.canvas.base_pixmap
        zoom = int(self.canvas.zoom_level * 100)
        tool = self.canvas.current_tool.capitalize()
        self.step_label.setText(f" Step: {self.canvas.step_counter} ")
        self.statusBar().showMessage(
            f"  {img.width()} x {img.height()} px  |  "
            f"Zoom: {zoom}%  |  Tool: {tool}  |  "
            f"Format: {config.OUTPUT_FILE_FORMAT.upper()}"
        )

    def _create_statusbar(self):
        status = QStatusBar()
        self.setStatusBar(status)
        self._update_status()

    # --- File operations ---

    def save_as(self):
        filters = (
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;"
            "GIF (*.gif);;TIFF (*.tiff *.tif);;All Files (*)"
        )
        default_path = config.get_filename()
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Screenshot", default_path, filters
        )
        if filepath:
            self._save_to_file(filepath)

    def quick_save(self):
        if self.saved_path:
            self._save_to_file(self.saved_path)
        else:
            filepath = config.get_filename()
            self._save_to_file(filepath)

    def _save_to_file(self, filepath):
        try:
            final = self.canvas.get_final_image()
            ext = os.path.splitext(filepath)[1].lower()
            fmt_map = {
                '.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG',
                '.bmp': 'BMP', '.gif': 'GIF', '.tiff': 'TIFF', '.tif': 'TIFF'
            }
            fmt = fmt_map.get(ext, 'PNG')
            quality = config.OUTPUT_JPEG_QUALITY if fmt == 'JPEG' else -1

            os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

            success = final.save(filepath, fmt, quality)
            if success:
                self.saved_path = filepath
                config.LAST_SAVE_DIR = os.path.dirname(filepath)
                config.save()
                self.canvas.dirty = False
                self.statusBar().showMessage(f"  Saved: {filepath}", 3000)
                QApplication.processEvents()
                log.info(f"Image saved: {filepath}")
            else:
                QMessageBox.warning(self, "Save Error", f"Could not save to:\n{filepath}")
                log.error(f"Failed to save image: {filepath}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving file:\n{e}")
            log.error(f"Save exception: {e}")

    def copy_to_clipboard(self):
        final = self.canvas.get_final_image()
        QApplication.clipboard().setPixmap(final)
        self.statusBar().showMessage("  Copied to clipboard", 2000)

    def print_image(self):
        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec_() == QPrintDialog.Accepted:
                final = self.canvas.get_final_image()
                painter = QPainter(printer)
                rect = painter.viewport()
                size = final.size()
                size.scale(rect.size(), Qt.KeepAspectRatio)
                painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
                painter.setWindow(final.rect())
                painter.drawPixmap(0, 0, final)
                painter.end()
                self.statusBar().showMessage("  Printed successfully", 2000)
        except Exception as e:
            log.error(f"Print failed: {e}")

    def _pin_image(self):
        try:
            from pin_window import PinWindow
            final = self.canvas.get_final_image()
            pin = PinWindow(final)
            pin.show()
            if self.app_controller:
                self.app_controller._pin_windows.append(pin)
                pin.closed.connect(lambda pw: self.app_controller._pin_windows.remove(pw)
                                   if pw in self.app_controller._pin_windows else None)
        except Exception as e:
            log.error(f"Pin failed: {e}")

    def _zoom_to_fit(self):
        scroll_size = self.scroll_area.viewport().size()
        img_size = self.canvas.base_pixmap.size()
        if img_size.width() == 0 or img_size.height() == 0:
            return
        zoom_w = scroll_size.width() / img_size.width()
        zoom_h = scroll_size.height() / img_size.height()
        self.canvas.set_zoom(min(zoom_w, zoom_h) * 0.95)

    def _run_ocr(self):
        try:
            from ocr import ocr_pixmap
            final = self.canvas.get_final_image()
            self.statusBar().showMessage("  Running OCR...", 0)
            QApplication.processEvents()

            text = ocr_pixmap(final)
            if text:
                QApplication.clipboard().setText(text)
                from ocr_dialog import OcrResultDialog
                dlg = OcrResultDialog(text, self)
                dlg.exec_()
                self.statusBar().showMessage("  OCR complete - text copied to clipboard", 3000)
            else:
                self.statusBar().showMessage("  OCR: no text detected", 3000)
                QMessageBox.information(self, "OCR", "No text detected in the image.")
        except Exception as e:
            self.statusBar().showMessage("  OCR failed", 3000)
            QMessageBox.warning(self, "OCR Error", f"Could not extract text:\n\n{str(e)}")
            log.error(f"OCR failed: {e}")

    def _load_diff_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Comparison Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All Files (*)"
        )
        if filepath:
            pixmap = QPixmap(filepath)
            if not pixmap.isNull():
                self.canvas.set_diff_image(pixmap)
                self.statusBar().showMessage(
                    "  Diff overlay loaded. Ctrl+D to toggle. Adjust in Image menu.", 3000
                )

    def _apply_template(self, template_name):
        if template_name == "bug":
            self.canvas.current_color = QColor("#f38ba8")
            self.color_btn.set_color(QColor("#f38ba8"))
            self.canvas.current_line_width = 3
            self.line_width_spin.setValue(3)
            self._set_tool("arrow")
            self.statusBar().showMessage(
                "  Bug Report template: Arrow tool active. "
                "Use N for step numbers, O to obfuscate sensitive areas.", 5000
            )
        elif template_name == "tutorial":
            self.canvas.current_color = QColor("#89b4fa")
            self.color_btn.set_color(QColor("#89b4fa"))
            self.canvas.current_line_width = 2
            self.canvas.step_counter = 1
            self.line_width_spin.setValue(2)
            self._set_tool("step")
            self.statusBar().showMessage(
                "  Tutorial template: Step tool active (counter reset). "
                "Use H to highlight areas.", 5000
            )
        elif template_name == "redact":
            self._set_tool("obfuscate")
            self.statusBar().showMessage(
                "  Redact template: Obfuscate tool active. "
                "Drag over sensitive areas to pixelate them.", 5000
            )

    def closeEvent(self, event):
        if self.canvas.dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )
            if reply == QMessageBox.Save:
                self.quick_save()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        # Save recent colors
        config.save()

        geo = self.geometry()
        config.WINDOW_GEOMETRY = f"{geo.x()},{geo.y()},{geo.width()},{geo.height()}"
        config.save()

        if self.app_controller:
            self.app_controller.editor_closed(self)

        event.accept()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.canvas.set_zoom(self.canvas.zoom_level + 0.1)
            else:
                self.canvas.set_zoom(self.canvas.zoom_level - 0.1)
            event.accept()
        elif event.modifiers() & Qt.ShiftModifier:
            delta = event.angleDelta().y()
            hbar = self.scroll_area.horizontalScrollBar()
            hbar.setValue(hbar.value() - delta)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.canvas.space_held = True
            self.canvas.setCursor(Qt.OpenHandCursor)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.canvas.space_held = False
            self._set_tool(self.canvas.current_tool)
        else:
            super().keyReleaseEvent(event)
