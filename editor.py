"""
SwiftShot Image Editor
Full-featured screenshot editor with annotation tools.

Tools: Select, Crop, Rectangle, Ellipse, Line, Arrow, Freehand,
       Text, Highlight, Obfuscate, Step Number, Eraser
Features: Undo/Redo, Copy, Save, Print, Zoom, Color picker
"""

import os
import sys
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar,
    QAction, QActionGroup, QStatusBar, QLabel, QSpinBox,
    QColorDialog, QFileDialog, QMessageBox, QScrollArea,
    QSizePolicy, QSlider, QComboBox, QToolButton, QMenu,
    QDialog, QDialogButtonBox, QTextEdit, QFormLayout, QFontComboBox,
    QApplication, QPushButton, QInputDialog
)
from PyQt5.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QImage, QFont,
    QIcon, QCursor, QPolygon, QPainterPath, QTransform,
    QKeySequence, QFontMetrics
)
from PyQt5.QtCore import (
    Qt, QRect, QPoint, QPointF, QSize, QRectF, pyqtSignal, QBuffer, QIODevice
)
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog

from config import config


# ---------------------------------------------------------------------------
# Drawing Element Classes
# ---------------------------------------------------------------------------

class DrawableElement:
    """Base class for all drawable elements."""
    
    def __init__(self, color=QColor("#f38ba8"), line_width=2):
        self.color = color
        self.line_width = line_width
        self.selected = False
    
    def draw(self, painter):
        raise NotImplementedError
    
    def bounding_rect(self):
        return QRect()


class RectElement(DrawableElement):
    def __init__(self, rect, color, line_width, filled=False):
        super().__init__(color, line_width)
        self.rect = rect
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
        self.rect = rect
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
        self.p1 = p1
        self.p2 = p2
    
    def draw(self, painter):
        pen = QPen(self.color, self.line_width, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(self.p1, self.p2)
    
    def bounding_rect(self):
        return QRect(self.p1, self.p2).normalized()


class ArrowElement(DrawableElement):
    def __init__(self, p1, p2, color, line_width):
        super().__init__(color, line_width)
        self.p1 = p1
        self.p2 = p2
    
    def draw(self, painter):
        pen = QPen(self.color, self.line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QBrush(self.color))
        painter.drawLine(self.p1, self.p2)
        
        # Arrowhead
        import math
        dx = self.p2.x() - self.p1.x()
        dy = self.p2.y() - self.p1.y()
        angle = math.atan2(dy, dx)
        arrow_len = max(12, self.line_width * 5)
        arrow_angle = math.pi / 6  # 30 degrees
        
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
        self.points = points  # list of QPoint
    
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
        self.pos = pos
        self.text = text
        self.font = font
    
    def draw(self, painter):
        painter.setPen(QPen(self.color))
        painter.setFont(self.font)
        painter.drawText(self.pos, self.text)


class HighlightElement(DrawableElement):
    """Semi-transparent highlight rectangle."""
    def __init__(self, rect, color):
        super().__init__(color)
        self.rect = rect
    
    def draw(self, painter):
        highlight_color = QColor(self.color)
        highlight_color.setAlpha(100)
        painter.fillRect(self.rect, highlight_color)


class ObfuscateElement(DrawableElement):
    """Pixelate/blur a region."""
    def __init__(self, rect, factor=12, source_pixmap=None):
        super().__init__()
        self.rect = rect
        self.factor = factor
        self.source_pixmap = source_pixmap
    
    def draw(self, painter):
        if self.source_pixmap is None:
            return
        
        r = self.rect.normalized()
        if r.width() < 1 or r.height() < 1:
            return
        
        # Extract source region
        cropped = self.source_pixmap.copy(r)
        
        # Scale down then back up for pixelation effect
        small = cropped.scaled(
            max(1, r.width() // self.factor),
            max(1, r.height() // self.factor),
            Qt.IgnoreAspectRatio, Qt.FastTransformation
        )
        pixelated = small.scaled(
            r.width(), r.height(),
            Qt.IgnoreAspectRatio, Qt.FastTransformation
        )
        
        painter.drawPixmap(r.topLeft(), pixelated)


class StepNumberElement(DrawableElement):
    """Numbered circle for step-by-step annotations."""
    def __init__(self, pos, number, color, size=28):
        super().__init__(color)
        self.pos = pos
        self.number = number
        self.size = size
    
    def draw(self, painter):
        r = QRect(
            self.pos.x() - self.size // 2,
            self.pos.y() - self.size // 2,
            self.size, self.size
        )
        
        # Circle
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(r)
        
        # Number
        painter.setPen(QPen(QColor("white")))
        font = QFont("Segoe UI", self.size // 3, QFont.Bold)
        painter.setFont(font)
        painter.drawText(r, Qt.AlignCenter, str(self.number))


# ---------------------------------------------------------------------------
# Canvas Widget
# ---------------------------------------------------------------------------

class EditorCanvas(QWidget):
    """The drawing canvas where the screenshot and annotations are displayed."""
    
    zoom_changed = pyqtSignal(float)
    
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap.copy()
        self.base_pixmap = pixmap.copy()  # Base image (after crops/confirmed edits)
        self.elements = []
        self.undo_stack = []
        self.redo_stack = []
        
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
        
        # Interaction state
        self.drawing = False
        self.draw_start = QPoint()
        self.draw_end = QPoint()
        self.freehand_points = []
        self.temp_element = None
        
        # Crop state
        self.crop_rect = None
        self.crop_active = False
        
        # Pan state (click-drag to pan the canvas view)
        self.panning = False
        self.pan_start = QPoint()
        self.pan_scroll_start_h = 0
        self.pan_scroll_start_v = 0
        self.space_held = False  # Space+drag panning
        
        self.setMouseTracking(True)
        self._update_size()
    
    def _update_size(self):
        """Update widget size based on zoom level."""
        size = self.base_pixmap.size() * self.zoom_level
        self.setMinimumSize(size)
        self.setMaximumSize(size)
        self.resize(size)
        self.update()
    
    def set_zoom(self, level):
        """Set zoom level (0.25 to 4.0)."""
        self.zoom_level = max(0.25, min(4.0, level))
        self._update_size()
        self.zoom_changed.emit(self.zoom_level)
    
    def _to_image_coords(self, pos):
        """Convert widget coordinates to image coordinates."""
        return QPoint(
            int(pos.x() / self.zoom_level),
            int(pos.y() / self.zoom_level)
        )
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # Scale for zoom
        painter.scale(self.zoom_level, self.zoom_level)
        
        # Draw base image
        painter.drawPixmap(0, 0, self.base_pixmap)
        
        # Draw all elements
        for elem in self.elements:
            elem.draw(painter)
        
        # Draw temporary element (while drawing)
        if self.temp_element:
            self.temp_element.draw(painter)
        
        # Draw crop overlay
        if self.crop_active and self.crop_rect:
            self._draw_crop_overlay(painter)
        
        painter.end()
    
    def _draw_crop_overlay(self, painter):
        """Draw the crop selection overlay."""
        rect = self.crop_rect.normalized()
        
        # Darken outside crop area
        path = QPainterPath()
        path.addRect(QRectF(self.base_pixmap.rect()))
        inner = QPainterPath()
        inner.addRect(QRectF(rect))
        path = path.subtracted(inner)
        painter.fillPath(path, QColor(0, 0, 0, 150))
        
        # Crop border
        pen = QPen(QColor("#a6e3a1"), 2, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        
        # Rule of thirds grid
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
        """Get the parent QScrollArea (for panning)."""
        parent = self.parent()
        while parent:
            from PyQt5.QtWidgets import QScrollArea
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parent() if hasattr(parent, 'parent') else None
        return None
    
    def _start_pan(self, event):
        """Begin a pan operation."""
        self.panning = True
        self.pan_start = event.globalPos()
        scroll = self._get_scroll_area()
        if scroll:
            self.pan_scroll_start_h = scroll.horizontalScrollBar().value()
            self.pan_scroll_start_v = scroll.verticalScrollBar().value()
        self.setCursor(Qt.ClosedHandCursor)
    
    def _should_pan(self, event):
        """Check if this left-click should start panning instead of drawing."""
        # Space held = always pan
        if self.space_held:
            return True
        # Select tool + no element hit = pan
        if self.current_tool == "select":
            return True
        return False
    
    def mousePressEvent(self, event):
        # Middle mouse button: always pan
        if event.button() == Qt.MiddleButton:
            self._start_pan(event)
            return
        
        if event.button() != Qt.LeftButton:
            return
        
        # Check if we should pan instead of draw
        if self._should_pan(event):
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
    
    def mouseMoveEvent(self, event):
        # Handle panning
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
                self.current_color, self.current_line_width
            )
        elif self.current_tool == "ellipse":
            self.temp_element = EllipseElement(
                QRect(self.draw_start, pos).normalized(),
                self.current_color, self.current_line_width
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
                self.base_pixmap
            )
        
        self.update()
    
    def mouseReleaseEvent(self, event):
        # Handle pan release (middle button or left when panning)
        if self.panning and (event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton):
            self.panning = False
            # Restore cursor based on current tool
            if self.current_tool == "select":
                self.setCursor(Qt.OpenHandCursor)
            elif self.space_held:
                self.setCursor(Qt.OpenHandCursor)
            else:
                # Let the tool set its own cursor
                pass
            return
        
        if event.button() != Qt.LeftButton or not self.drawing:
            return
        
        self.drawing = False
        pos = self._to_image_coords(event.pos())
        self.draw_end = pos
        
        if self.current_tool == "crop":
            # Crop stays active until confirmed
            self.crop_rect = QRect(self.draw_start, pos).normalized()
            self.update()
            return
        
        # Finalize the element
        element = self.temp_element
        self.temp_element = None
        
        if element:
            self._save_undo_state()
            self.elements.append(element)
            self.redo_stack.clear()
        
        self.update()
    
    def _insert_text(self, pos):
        """Show text input dialog and insert text element."""
        text, ok = QInputDialog.getText(
            self, "Insert Text", "Enter text:",
            text=""
        )
        if ok and text:
            self._save_undo_state()
            elem = TextElement(pos, text, self.current_color, self.current_font)
            self.elements.append(elem)
            self.redo_stack.clear()
            self.update()
    
    def _insert_step(self, pos):
        """Insert a step number circle."""
        self._save_undo_state()
        elem = StepNumberElement(pos, self.step_counter, self.current_color)
        self.elements.append(elem)
        self.step_counter += 1
        self.redo_stack.clear()
        self.update()
    
    def confirm_crop(self):
        """Apply the current crop."""
        if not self.crop_rect:
            return
        
        rect = self.crop_rect.normalized()
        if rect.width() < 1 or rect.height() < 1:
            return
        
        self._save_undo_state()
        
        # Flatten current elements onto base pixmap
        self._flatten_elements()
        
        # Crop the base image
        self.base_pixmap = self.base_pixmap.copy(rect)
        self.crop_rect = None
        self.crop_active = False
        self.redo_stack.clear()
        self._update_size()
    
    def cancel_crop(self):
        """Cancel the current crop operation."""
        self.crop_rect = None
        self.crop_active = False
        self.update()
    
    def _flatten_elements(self):
        """Render all elements onto the base pixmap."""
        if not self.elements:
            return
        
        painter = QPainter(self.base_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        for elem in self.elements:
            elem.draw(painter)
        painter.end()
        self.elements.clear()
    
    def _save_undo_state(self):
        """Save current state for undo."""
        state = {
            'base_pixmap': self.base_pixmap.copy(),
            'elements': list(self.elements),
            'step_counter': self.step_counter,
        }
        self.undo_stack.append(state)
        # Limit undo stack
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
    
    def undo(self):
        """Undo the last action."""
        if not self.undo_stack:
            return
        
        # Save current state for redo
        current = {
            'base_pixmap': self.base_pixmap.copy(),
            'elements': list(self.elements),
            'step_counter': self.step_counter,
        }
        self.redo_stack.append(current)
        
        state = self.undo_stack.pop()
        self.base_pixmap = state['base_pixmap']
        self.elements = state['elements']
        self.step_counter = state['step_counter']
        self._update_size()
    
    def redo(self):
        """Redo the last undone action."""
        if not self.redo_stack:
            return
        
        current = {
            'base_pixmap': self.base_pixmap.copy(),
            'elements': list(self.elements),
            'step_counter': self.step_counter,
        }
        self.undo_stack.append(current)
        
        state = self.redo_stack.pop()
        self.base_pixmap = state['base_pixmap']
        self.elements = state['elements']
        self.step_counter = state['step_counter']
        self._update_size()
    
    def get_final_image(self):
        """Get the final composed image as QPixmap."""
        result = self.base_pixmap.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        for elem in self.elements:
            elem.draw(painter)
        painter.end()
        return result
    
    def reset_step_counter(self):
        """Reset the step number counter."""
        self.step_counter = 1
    
    def rotate_image(self, degrees):
        """Rotate the image."""
        self._save_undo_state()
        self._flatten_elements()
        transform = QTransform().rotate(degrees)
        self.base_pixmap = self.base_pixmap.transformed(transform, Qt.SmoothTransformation)
        self.redo_stack.clear()
        self._update_size()
    
    def flip_horizontal(self):
        """Flip the image horizontally."""
        self._save_undo_state()
        self._flatten_elements()
        transform = QTransform().scale(-1, 1)
        self.base_pixmap = self.base_pixmap.transformed(transform)
        self.redo_stack.clear()
        self.update()
    
    def flip_vertical(self):
        """Flip the image vertically."""
        self._save_undo_state()
        self._flatten_elements()
        transform = QTransform().scale(1, -1)
        self.base_pixmap = self.base_pixmap.transformed(transform)
        self.redo_stack.clear()
        self.update()
    
    def auto_crop(self):
        """Auto-crop borders of solid background color."""
        self._save_undo_state()
        self._flatten_elements()
        
        image = self.base_pixmap.toImage()
        w, h = image.width(), image.height()
        
        if w < 3 or h < 3:
            return
        
        # Get corner color as reference
        bg_color = image.pixelColor(0, 0)
        tolerance = 30
        
        def color_matches(c1, c2):
            return (abs(c1.red() - c2.red()) < tolerance and
                    abs(c1.green() - c2.green()) < tolerance and
                    abs(c1.blue() - c2.blue()) < tolerance)
        
        # Find bounds
        top, bottom, left, right = 0, h - 1, 0, w - 1
        
        # Top
        for y in range(h):
            found = False
            for x in range(w):
                if not color_matches(image.pixelColor(x, y), bg_color):
                    found = True
                    break
            if found:
                top = y
                break
        
        # Bottom
        for y in range(h - 1, -1, -1):
            found = False
            for x in range(w):
                if not color_matches(image.pixelColor(x, y), bg_color):
                    found = True
                    break
            if found:
                bottom = y
                break
        
        # Left
        for x in range(w):
            found = False
            for y in range(h):
                if not color_matches(image.pixelColor(x, y), bg_color):
                    found = True
                    break
            if found:
                left = x
                break
        
        # Right
        for x in range(w - 1, -1, -1):
            found = False
            for y in range(h):
                if not color_matches(image.pixelColor(x, y), bg_color):
                    found = True
                    break
            if found:
                right = x
                break
        
        if right > left and bottom > top:
            crop_rect = QRect(left, top, right - left + 1, bottom - top + 1)
            self.base_pixmap = self.base_pixmap.copy(crop_rect)
            self.redo_stack.clear()
            self._update_size()


# ---------------------------------------------------------------------------
# Color Button
# ---------------------------------------------------------------------------

class ColorButton(QPushButton):
    """Button that shows and lets you pick a color."""
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
                border: 2px solid #45475a;
                border-radius: 4px;
                min-width: 24px;
                max-width: 24px;
            }}
            QPushButton:hover {{
                border-color: #89b4fa;
            }}
        """)
    
    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Choose Color")
        if color.isValid():
            self._color = color
            self._update_style()
            self.color_changed.emit(color)
    
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
        
        # Canvas
        self.canvas = EditorCanvas(pixmap)
        
        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.canvas)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #11111b;
                border: none;
            }
        """)
        
        self.setCentralWidget(self.scroll_area)
        
        # Build UI
        self._create_menubar()
        self._create_toolbar()
        self._create_statusbar()
        
        # Restore window geometry
        if config.WINDOW_GEOMETRY:
            try:
                parts = config.WINDOW_GEOMETRY.split(',')
                self.setGeometry(int(parts[0]), int(parts[1]),
                                 int(parts[2]), int(parts[3]))
            except (ValueError, IndexError):
                self._center_window()
        else:
            self._center_window()
        
        # Connect signals
        self.canvas.zoom_changed.connect(self._update_zoom_label)
    
    def _center_window(self):
        """Center the window on screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            w = min(self.canvas.base_pixmap.width() + 100, geo.width() - 100)
            h = min(self.canvas.base_pixmap.height() + 180, geo.height() - 100)
            x = (geo.width() - w) // 2
            y = (geo.height() - h) // 2
            self.setGeometry(x, y, w, h)
    
    def _create_menubar(self):
        """Create the menu bar."""
        menubar = self.menuBar()
        
        # --- File Menu ---
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
        
        close_action = QAction("Close", self)
        close_action.setShortcut(QKeySequence("Ctrl+W"))
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)
        
        # --- Edit Menu ---
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
        
        # --- Tools Menu ---
        tools_menu = menubar.addMenu("&Tools")
        
        ocr_action = QAction("Extract Text (OCR)", self)
        ocr_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        ocr_action.triggered.connect(self._run_ocr)
        tools_menu.addAction(ocr_action)
        
        # --- Image Menu ---
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
        
        # --- View Menu ---
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
        """Create the main toolbar with drawing tools."""
        toolbar = QToolBar("Tools")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)
        
        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)
        
        tools = [
            ("select", "Select (V)", "V", "pointer"),
            ("crop", "Crop (C)", "C", "crop"),
            ("rect", "Rectangle (R)", "R", "rect"),
            ("ellipse", "Ellipse (E)", "E", "ellipse"),
            ("line", "Line (L)", "L", "line"),
            ("arrow", "Arrow (A)", "A", "arrow"),
            ("freehand", "Freehand (F)", "F", "freehand"),
            ("text", "Text (T)", "T", "text"),
            ("highlight", "Highlight (H)", "H", "highlight"),
            ("obfuscate", "Obfuscate (O)", "O", "obfuscate"),
            ("step", "Step Number (N)", "N", "step"),
        ]
        
        for tool_id, tooltip, shortcut, icon_name in tools:
            action = QAction(self._make_tool_icon(icon_name), tooltip, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setData(tool_id)
            action.triggered.connect(lambda checked, tid=tool_id: self._set_tool(tid))
            tool_group.addAction(action)
            toolbar.addAction(action)
            
            if tool_id == "select":
                action.setChecked(True)
        
        toolbar.addSeparator()
        
        # Color picker
        self.color_btn = ColorButton(self.canvas.current_color)
        self.color_btn.color_changed.connect(self._on_color_changed)
        self.color_btn.setToolTip("Drawing Color")
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
        self.line_width_spin.valueChanged.connect(
            lambda v: setattr(self.canvas, 'current_line_width', v)
        )
        toolbar.addWidget(self.line_width_spin)
        
        toolbar.addSeparator()
        
        # Undo / Redo
        undo_btn = QAction("Undo", self)
        undo_btn.setShortcut(QKeySequence.Undo)
        undo_btn.triggered.connect(self.canvas.undo)
        toolbar.addAction(undo_btn)
        
        redo_btn = QAction("Redo", self)
        redo_btn.setShortcut(QKeySequence.Redo)
        redo_btn.triggered.connect(self.canvas.redo)
        toolbar.addAction(redo_btn)
        
        toolbar.addSeparator()
        
        # Quick actions
        save_btn = QAction("Save", self)
        save_btn.triggered.connect(self.quick_save)
        toolbar.addAction(save_btn)
        
        clip_btn = QAction("Clipboard", self)
        clip_btn.triggered.connect(self.copy_to_clipboard)
        toolbar.addAction(clip_btn)
        
        print_btn = QAction("Print", self)
        print_btn.triggered.connect(self.print_image)
        toolbar.addAction(print_btn)
        
        toolbar.addSeparator()
        
        # OCR
        ocr_btn = QAction("OCR", self)
        ocr_btn.setToolTip("Extract Text (OCR)  Ctrl+Shift+O")
        ocr_btn.triggered.connect(self._run_ocr)
        toolbar.addAction(ocr_btn)
    
    def _make_tool_icon(self, icon_name):
        """Generate a simple icon for each tool."""
        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#cdd6f4"), 1.5)
        painter.setPen(pen)
        
        if icon_name == "pointer":
            # Arrow cursor
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
        
        painter.end()
        return QIcon(pixmap)
    
    def _set_tool(self, tool_id):
        """Set the active drawing tool."""
        self.canvas.current_tool = tool_id
        
        if tool_id == "select":
            self.canvas.setCursor(Qt.OpenHandCursor)
        elif tool_id == "crop":
            self.canvas.setCursor(Qt.CrossCursor)
        elif tool_id == "text":
            self.canvas.setCursor(Qt.IBeamCursor)
        elif tool_id in ("freehand", "highlight", "obfuscate"):
            self.canvas.setCursor(Qt.CrossCursor)
        else:
            self.canvas.setCursor(Qt.CrossCursor)
        
        self._update_status()
    
    def _on_color_changed(self, color):
        """Handle color change from the color button."""
        self.canvas.current_color = color
    
    def _update_zoom_label(self, zoom):
        """Update zoom display in status bar."""
        self._update_status()
    
    def _update_status(self):
        """Update the status bar."""
        img = self.canvas.base_pixmap
        zoom = int(self.canvas.zoom_level * 100)
        tool = self.canvas.current_tool.capitalize()
        self.statusBar().showMessage(
            f"  {img.width()} x {img.height()} px  |  "
            f"Zoom: {zoom}%  |  Tool: {tool}  |  "
            f"Format: {config.OUTPUT_FILE_FORMAT.upper()}"
        )
    
    def _create_statusbar(self):
        """Create the status bar."""
        status = QStatusBar()
        self.setStatusBar(status)
        self._update_status()
    
    # --- File operations ---
    
    def save_as(self):
        """Save with file dialog."""
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
        """Quick save to default location."""
        if self.saved_path:
            self._save_to_file(self.saved_path)
        else:
            filepath = config.get_filename()
            self._save_to_file(filepath)
    
    def _save_to_file(self, filepath):
        """Save the final image to file."""
        final = self.canvas.get_final_image()
        
        # Determine format
        ext = os.path.splitext(filepath)[1].lower()
        fmt_map = {
            '.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG',
            '.bmp': 'BMP', '.gif': 'GIF', '.tiff': 'TIFF', '.tif': 'TIFF'
        }
        fmt = fmt_map.get(ext, 'PNG')
        quality = config.OUTPUT_JPEG_QUALITY if fmt == 'JPEG' else -1
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        
        success = final.save(filepath, fmt, quality)
        if success:
            self.saved_path = filepath
            config.LAST_SAVE_DIR = os.path.dirname(filepath)
            config.save()
            self.statusBar().showMessage(f"  Saved: {filepath}", 3000)
            QApplication.processEvents()
        else:
            QMessageBox.warning(self, "Save Error", f"Could not save to:\n{filepath}")
    
    def copy_to_clipboard(self):
        """Copy the final image to clipboard."""
        final = self.canvas.get_final_image()
        QApplication.clipboard().setPixmap(final)
        self.statusBar().showMessage("  Copied to clipboard", 2000)
    
    def print_image(self):
        """Print the image."""
        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        
        if dialog.exec_() == QPrintDialog.Accepted:
            final = self.canvas.get_final_image()
            painter = QPainter(printer)
            rect = painter.viewport()
            size = final.size()
            size.scale(rect.size(), Qt.KeepAspectRatio)
            painter.setViewport(
                rect.x(), rect.y(), size.width(), size.height()
            )
            painter.setWindow(final.rect())
            painter.drawPixmap(0, 0, final)
            painter.end()
            self.statusBar().showMessage("  Printed successfully", 2000)
    
    def _zoom_to_fit(self):
        """Zoom to fit the image in the scroll area."""
        scroll_size = self.scroll_area.viewport().size()
        img_size = self.canvas.base_pixmap.size()
        
        if img_size.width() == 0 or img_size.height() == 0:
            return
        
        zoom_w = scroll_size.width() / img_size.width()
        zoom_h = scroll_size.height() / img_size.height()
        self.canvas.set_zoom(min(zoom_w, zoom_h) * 0.95)
    
    def _run_ocr(self):
        """Extract text from the current image using OCR."""
        try:
            from ocr import ocr_pixmap
            final = self.canvas.get_final_image()
            self.statusBar().showMessage("  Running OCR...", 0)
            QApplication.processEvents()
            
            text = ocr_pixmap(final)
            if text:
                QApplication.clipboard().setText(text)
                from app import OcrResultDialog
                dlg = OcrResultDialog(text, self)
                dlg.exec_()
                self.statusBar().showMessage("  OCR complete - text copied to clipboard", 3000)
            else:
                self.statusBar().showMessage("  OCR: no text detected", 3000)
                QMessageBox.information(self, "OCR", "No text detected in the image.")
        except Exception as e:
            self.statusBar().showMessage("  OCR failed", 3000)
            QMessageBox.warning(self, "OCR Error", f"Could not extract text:\n\n{str(e)}")
    
    def closeEvent(self, event):
        """Handle window close."""
        geo = self.geometry()
        config.WINDOW_GEOMETRY = f"{geo.x()},{geo.y()},{geo.width()},{geo.height()}"
        config.save()
        
        if self.app_controller:
            self.app_controller.editor_closed(self)
        
        event.accept()
    
    def wheelEvent(self, event):
        """Handle scroll wheel: Ctrl+Scroll = zoom, plain scroll = pan vertically, Shift+Scroll = pan horizontally."""
        if event.modifiers() & Qt.ControlModifier:
            # Zoom
            delta = event.angleDelta().y()
            if delta > 0:
                self.canvas.set_zoom(self.canvas.zoom_level + 0.1)
            else:
                self.canvas.set_zoom(self.canvas.zoom_level - 0.1)
            event.accept()
        elif event.modifiers() & Qt.ShiftModifier:
            # Horizontal scroll
            delta = event.angleDelta().y()
            hbar = self.scroll_area.horizontalScrollBar()
            hbar.setValue(hbar.value() - delta)
            event.accept()
        else:
            # Vertical scroll (default behavior - pass to scroll area)
            super().wheelEvent(event)
    
    def keyPressEvent(self, event):
        """Handle Space key for pan mode."""
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.canvas.space_held = True
            self.canvas.setCursor(Qt.OpenHandCursor)
        else:
            super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """Handle Space key release."""
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self.canvas.space_held = False
            # Restore cursor for current tool
            self._set_tool(self.canvas.current_tool)
        else:
            super().keyReleaseEvent(event)
