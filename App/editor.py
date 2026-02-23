#!/usr/bin/env python3
"""
SwiftShot Image Editor v2.6.5
Photoshop-inspired PyQt5 / PIL layer-based editor.

Tools: Select/Move, Brush, Pencil, Spray, Eraser, Clone Stamp, Healing Brush,
       Dodge, Burn, Sponge, Smudge, Pen, Rectangle, Ellipse, Line, Arrow,
       Triangle, Polygon, Star, Text, Gradient, Fill, Pattern, Eyedropper,
       Magic Wand, Rect/Ellipse Select, Lasso, Crop, Measure, Pan, Zoom
Adjustments: Brightness/Contrast, Hue/Saturation, Levels, Curves, Color Balance,
             Vibrance, Threshold, Gamma, Invert, Grayscale, Auto Contrast,
             Auto Levels, Sepia, Color Lookup
Filters: Gaussian/Box/Motion Blur, Sharpen, Unsharp Mask, Edge Detect, Emboss,
         Contour, Posterize, Solarize, Pixelate, Noise, Vignette, Oil Paint,
         Halftone, Duotone, Tilt Shift, Chromatic Aberration, Noise Generator
AI Tools: Background Removal (rembg), Smart Upscale 2x/4x, Depth Map, Object Detect
Selection: Expand, Contract, Feather, Smooth, Color Range
UI: Rulers, Grid, Navigator, Histogram, Command Palette
Integrations: OCR, Imgur, Project Save/Load, Clipboard
"""

import sys, os, math, random, threading, json
import subprocess

def _bootstrap():
    pkgs = {"PyQt5": "PyQt5", "PIL": "Pillow", "numpy": "numpy"}
    for mod, pkg in pkgs.items():
        try:
            __import__(mod)
        except ImportError:
            for flags in [[], ["--user"], ["--break-system-packages"]]:
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", pkg, "-q"] + flags,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except subprocess.CalledProcessError:
                    continue

_bootstrap()

import numpy as np
from collections import deque
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont, ImageOps, ImageChops

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QAction, QActionGroup, QFileDialog, QLabel, QSlider,
    QSpinBox, QDoubleSpinBox, QColorDialog, QDockWidget, QListWidget,
    QListWidgetItem, QPushButton, QCheckBox, QComboBox, QScrollArea,
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QMenu,
    QStatusBar, QFrame, QInputDialog, QMessageBox, QSizePolicy,
    QToolButton, QWidgetAction, QGridLayout, QLineEdit, QTextEdit,
    QAbstractItemView, QTabWidget, QSplitter, QStackedWidget
)
from PyQt5.QtCore import (
    Qt, QPoint, QRect, QSize, QTimer, pyqtSignal, QPointF, QRectF,
    QByteArray, QBuffer, QIODevice, QThread, QObject
)
from PyQt5.QtGui import (
    QImage, QPixmap, QPainter, QPen, QBrush, QColor, QIcon,
    QCursor, QFont, QKeySequence, QPainterPath, QTransform,
    qRgba, QPolygon, QFontMetrics, QLinearGradient, QRadialGradient,
    QPolygonF
)
from PyQt5.QtSvg import QSvgRenderer

try:
    from logger import log
except ImportError:
    import logging; log = logging.getLogger("editor")

try:
    import config as _config
    config = _config.config if hasattr(_config, "config") else _config
except ImportError:
    config = None

# ── DPI / UI Scale helpers ───────────────────────────────────────────────────
_UI_SCALE = 1.0   # set by init_ui_scale() at startup, overridable from View menu

def _dpi():
    app = QApplication.instance()
    if app:
        screen = app.primaryScreen()
        if screen:
            return screen.logicalDotsPerInch()
    return 96.0

def _screen_w():
    app = QApplication.instance()
    if app:
        screen = app.primaryScreen()
        if screen:
            return screen.size().width()
    return 1920

def init_ui_scale(force=None):
    """Auto-detect best UI scale from screen resolution + DPI, or use forced value."""
    global _UI_SCALE
    if force is not None:
        _UI_SCALE = float(force)
        return _UI_SCALE
    dpi = _dpi()
    dpi_scale = dpi / 96.0          # Windows/system scaling
    sw = _screen_w()
    # Resolution bonus on top of OS scaling
    if sw >= 3840:     res_bonus = 1.45   # 4K UHD
    elif sw >= 3440:   res_bonus = 1.30   # ultrawide 3440
    elif sw >= 2560:   res_bonus = 1.15   # 1440p / ultrawide 2560
    elif sw >= 1920:   res_bonus = 1.0    # 1080p
    else:              res_bonus = 0.9    # small laptop
    # Combine: take the larger of OS scale vs resolution bonus
    _UI_SCALE = max(dpi_scale, res_bonus)
    # Round to nearest 0.25 to avoid blurry icons
    _UI_SCALE = round(_UI_SCALE * 4) / 4
    _UI_SCALE = max(0.75, min(3.0, _UI_SCALE))
    return _UI_SCALE

def get_ui_scale():
    return _UI_SCALE

def dp(px):
    """Scale a CSS-pixel value to logical pixels using combined DPI + resolution scale."""
    return max(1, int(px * _UI_SCALE))

def dpf(px):
    """Float version of dp()."""
    return px * _UI_SCALE

# ── PIL ↔ QPixmap ─────────────────────────────────────────────────────────────
def qpixmap_to_pil(pixmap):
    qimg = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.bits(); ptr.setsize(h * qimg.bytesPerLine())
    return Image.frombuffer("RGBA", (w, h), bytes(ptr), "raw", "RGBA", qimg.bytesPerLine(), 1).copy()

def pil_to_qpixmap(pil_image):
    img = pil_image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, 4 * img.width, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())

# ── Photoshop-inspired Color Variables ───────────────────────────────────────
class C:
    """Photoshop-inspired dark palette."""
    BG0      = "#1b1b1b"   # deepest background (panel floors)
    BG1      = "#252525"   # panel backgrounds
    BG2      = "#2d2d2d"   # raised surfaces
    BG3      = "#383838"   # hover / selection backgrounds
    BORDER   = "#424242"   # borders and separators
    TEXT_PRI = "#e8e8e8"   # primary text
    TEXT_SEC = "#a0a0a0"   # secondary text
    TEXT_MUT = "#606060"   # muted / placeholder text
    ACCENT   = "#4d9bff"   # Photoshop-like blue accent
    ACCENT_D = "#1a3260"   # accent dim (selection bg)
    ACCENT_H = "#6cb2ff"   # accent hover
    RED      = "#ff6060"
    GREEN    = "#60cc80"
    YELLOW   = "#ffcc44"
    # Canvas background (PS medium gray)
    CANVAS_BG = "#3c3c3c"

# ── QSS Stylesheet ────────────────────────────────────────────────────────────
def build_ss():
    """Photoshop-inspired dark QSS theme."""
    return f"""
QMainWindow, QWidget {{
    background-color: {C.BG1};
    color: {C.TEXT_PRI};
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: {dp(12)}px;
}}
QMenuBar {{
    background-color: {C.BG0};
    color: {C.TEXT_PRI};
    border-bottom: 1px solid {C.BORDER};
    padding: 2px 4px;
    spacing: 0px;
}}
QMenuBar::item {{ padding: 5px 10px; border-radius: 3px; }}
QMenuBar::item:selected {{ background-color: {C.ACCENT}; color: #ffffff; }}
QMenuBar::item:pressed {{ background-color: {C.ACCENT_D}; }}
QMenu {{
    background-color: {C.BG2};
    color: {C.TEXT_PRI};
    border: 1px solid {C.BORDER};
    border-radius: 4px;
    padding: 4px 0px;
}}
QMenu::item {{ padding: {dp(5)}px {dp(28)}px {dp(5)}px {dp(16)}px; }}
QMenu::item:selected {{ background-color: {C.ACCENT}; color: #ffffff; border-radius: 0; }}
QMenu::separator {{ height: 1px; background: {C.BORDER}; margin: 4px 0px; }}
QMenu::icon {{ padding-left: 8px; }}
QToolBar {{
    background-color: {C.BG0};
    border: none;
    spacing: 1px;
    padding: 4px 2px;
}}
/* Left tool strip gets its right border via inline style */
QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px;
    color: {C.TEXT_SEC};
    min-width: {dp(28)}px;
    min-height: {dp(28)}px;
}}
QToolButton:hover {{
    background-color: {C.BG3};
    color: {C.TEXT_PRI};
    border-color: {C.BORDER};
}}
QToolButton:checked {{
    background-color: {C.ACCENT_D};
    color: {C.ACCENT};
    border-color: {C.ACCENT};
    border-width: 1px;
}}
QToolButton:pressed {{ background-color: {C.ACCENT_D}; }}
QPushButton {{
    background-color: {C.BG2};
    color: {C.TEXT_PRI};
    border: 1px solid {C.BORDER};
    border-radius: 4px;
    padding: {dp(4)}px {dp(12)}px;
    min-height: {dp(24)}px;
}}
QPushButton:hover {{ background-color: {C.BG3}; border-color: {C.ACCENT}; }}
QPushButton:pressed {{ background-color: {C.ACCENT_D}; color: {C.ACCENT}; }}
QPushButton#accent {{
    background-color: {C.ACCENT};
    color: #ffffff;
    border: none;
    font-weight: 600;
}}
QPushButton#accent:hover {{ background-color: {C.ACCENT_H}; }}
QSlider::groove:horizontal {{
    height: 3px;
    background: {C.BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {C.ACCENT};
    width: {dp(13)}px;
    height: {dp(13)}px;
    margin: -{dp(5)}px 0;
    border-radius: {dp(7)}px;
    border: 1px solid #1a1a1a;
}}
QSlider::handle:horizontal:hover {{ background: {C.ACCENT_H}; }}
QSlider::sub-page:horizontal {{ background: {C.ACCENT}; border-radius: 2px; }}
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {{
    background-color: {C.BG0};
    color: {C.TEXT_PRI};
    border: 1px solid {C.BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    min-height: {dp(22)}px;
    selection-background-color: {C.ACCENT};
}}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {{
    border-color: {C.ACCENT};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: {C.BG2};
    border: none;
    width: {dp(14)}px;
}}
QComboBox::drop-down {{ border: none; width: {dp(20)}px; }}
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C.TEXT_SEC};
}}
QComboBox QAbstractItemView {{
    background-color: {C.BG2};
    color: {C.TEXT_PRI};
    border: 1px solid {C.BORDER};
    selection-background-color: {C.ACCENT};
    selection-color: #ffffff;
    outline: none;
    padding: 2px;
}}
QScrollBar:vertical {{
    background: {C.BG0};
    width: {dp(8)}px;
    border: none;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C.BORDER};
    min-height: {dp(20)}px;
    border-radius: {dp(4)}px;
}}
QScrollBar::handle:vertical:hover {{ background: {C.TEXT_MUT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar:horizontal {{
    background: {C.BG0};
    height: {dp(8)}px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {C.BORDER};
    min-width: {dp(20)}px;
    border-radius: {dp(4)}px;
}}
QScrollBar::handle:horizontal:hover {{ background: {C.TEXT_MUT}; }}
QTabWidget::pane {{
    border: none;
    background: {C.BG1};
}}
QTabBar {{
    background: {C.BG0};
    border-bottom: 1px solid {C.BORDER};
}}
QTabBar::tab {{
    background: transparent;
    color: {C.TEXT_MUT};
    padding: {dp(6)}px {dp(8)}px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: {dp(11)}px;
    font-weight: 500;
    min-width: 0px;
}}
QTabBar::tab:selected {{
    color: {C.ACCENT};
    background: {C.BG1};
    border-bottom: 2px solid {C.ACCENT};
}}
QTabBar::tab:hover:!selected {{ color: {C.TEXT_PRI}; background: {C.BG2}; }}
QListWidget {{
    background-color: {C.BG1};
    color: {C.TEXT_PRI};
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: {dp(4)}px {dp(8)}px;
    border-bottom: 1px solid {C.BG0};
}}
QListWidget::item:selected {{
    background-color: {C.ACCENT_D};
    color: {C.ACCENT};
}}
QListWidget::item:hover {{ background-color: {C.BG2}; }}
QCheckBox {{ color: {C.TEXT_PRI}; spacing: 6px; }}
QCheckBox::indicator {{
    width: {dp(14)}px;
    height: {dp(14)}px;
    border: 1px solid {C.BORDER};
    border-radius: 2px;
    background: {C.BG0};
}}
QCheckBox::indicator:checked {{
    background: {C.ACCENT};
    border-color: {C.ACCENT};
}}
QGroupBox {{
    color: {C.TEXT_SEC};
    border: 1px solid {C.BORDER};
    border-radius: 5px;
    margin-top: {dp(16)}px;
    padding: {dp(10)}px {dp(8)}px {dp(8)}px {dp(8)}px;
    font-size: {dp(10)}px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: {dp(8)}px;
    padding: 0 {dp(4)}px;
    color: {C.TEXT_SEC};
    background: {C.BG1};
}}
QTextEdit {{
    background-color: {C.BG0};
    color: {C.TEXT_PRI};
    border: 1px solid {C.BORDER};
    border-radius: 3px;
}}
QStatusBar {{
    background-color: {C.BG0};
    color: {C.TEXT_SEC};
    border-top: 1px solid {C.BORDER};
    font-size: {dp(11)}px;
    font-family: 'Consolas', 'JetBrains Mono', monospace;
}}
QDockWidget::title {{
    background-color: {C.BG0};
    padding: 5px 8px;
    border-bottom: 1px solid {C.BORDER};
    color: {C.TEXT_MUT};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}}
QSplitter::handle {{ background: {C.BORDER}; width: 1px; height: 1px; }}
QToolTip {{
    background-color: {C.BG3};
    color: {C.TEXT_PRI};
    border: 1px solid {C.BORDER};
    border-radius: 3px;
    padding: {dp(4)}px {dp(8)}px;
    font-size: {dp(11)}px;
}}
QProgressBar {{
    background: {C.BG0};
    border: 1px solid {C.BORDER};
    border-radius: 3px;
    height: {dp(6)}px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C.ACCENT}, stop:1 {C.ACCENT_H});
    border-radius: 3px;
}}
"""

# ── SVG Icons (exact OpenShop paths) ─────────────────────────────────────────
_SVG_ICONS = {
    "select":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/><path d="M13 13l6 6"/></svg>',
    "move":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/><path d="M13 13l6 6"/></svg>',
    "marquee-rect": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2"><rect x="3" y="3" width="18" height="18" rx="1"/></svg>',
    "marquee-ellipse":'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-dasharray="3 2"><ellipse cx="12" cy="12" rx="10" ry="7"/></svg>',
    "lasso":        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12c0 4.97 4.03 9 9 9s9-4.03 9-9-4.03-9-9-9c-3.04 0-5.73 1.51-7.36 3.82"/><circle cx="7" cy="20" r="2" fill="currentColor"/></svg>',
    "magic-wand":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 4V2m0 14v-2M8 9H6m14 0h-2m-2.8-3.8L14 4m-4.2 9.8L8.6 15m9.8-1.2L19.6 15M9.8 5.2L8.6 4"/><path d="M2 22l10-10"/><circle cx="15" cy="9" r="1" fill="currentColor"/></svg>',
    "crop":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6.13 1L6 16a2 2 0 0 0 2 2h15"/><path d="M1 6.13L16 6a2 2 0 0 1 2 2v15"/></svg>',
    "measure":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 20L20 2"/><path d="M6 16l2-2"/><path d="M10 12l2-2"/><path d="M14 8l2-2"/><circle cx="2" cy="20" r="1.5" fill="currentColor"/><circle cx="20" cy="2" r="1.5" fill="currentColor"/></svg>',
    "brush":        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/></svg>',
    "pencil":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>',
    "spray":        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="12" width="10" height="10" rx="2"/><path d="M11 12V8"/><circle cx="7" cy="4" r="1" fill="currentColor"/><circle cx="11" cy="3" r="1" fill="currentColor"/><circle cx="15" cy="4" r="1" fill="currentColor"/></svg>',
    "eraser":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 20H7L3 16l9-9 8 8-4 4z"/><path d="M6 11l8 8"/></svg>',
    "clone":        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4m-10-10h4m12 0h4"/><circle cx="12" cy="12" r="9" stroke-dasharray="2 3"/></svg>',
    "healing":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 2l4 4-12 12H6v-4L18 2z"/><path d="M14 6l4 4"/><line x1="2" y1="22" x2="22" y2="22"/></svg>',
    "dodge":        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 3v18"/><path d="M3 12h9" fill="currentColor" stroke="none" opacity=".3"/></svg>',
    "burn":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 3v18"/><path d="M12 12h9" fill="currentColor" stroke="none" opacity=".5"/></svg>',
    "sponge":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M8 8V6a4 4 0 0 1 8 0v2"/><line x1="8" y1="12" x2="16" y2="12"/></svg>',
    "smudge":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 4l-4 4c-2 2-5 2-8 5s-1 6 2 7 5-1 7-4 3-6 5-8l4-4z"/></svg>',
    "rect":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>',
    "ellipse":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>',
    "triangle":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3L2 21h20L12 3z"/></svg>',
    "line":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="19" x2="19" y2="5"/></svg>',
    "arrow":        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="19" x2="19" y2="5"/><polyline points="10 5 19 5 19 14"/></svg>',
    "polygon":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l8.5 6.2-3.2 10H6.7L3.5 8.2z"/></svg>',
    "star":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"/></svg>',
    "text":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9.5" y1="20" x2="14.5" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>',
    "gradient":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="21" x2="21" y2="3" stroke-width="1" opacity=".4"/></svg>',
    "fill":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21v-3l9-9 3 3-9 9H3z"/><path d="M14 6l3-3 3 3"/><path d="M20 12.5a1.5 1.5 0 0 0 3 0c0-1.5-3-4-3-4s-3 2.5-3 4a1.5 1.5 0 0 0 3 0z"/></svg>',
    "pattern":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/></svg>',
    "eyedropper":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21v-3l9-9 3 3-9 9H3z"/><path d="M14.5 6.5l3-3a2.12 2.12 0 0 1 3 3l-3 3"/></svg>',
    "pan":          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 11V6a2 2 0 0 0-4 0v5"/><path d="M14 10V4a2 2 0 0 0-4 0v6"/><path d="M10 10.5V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 0 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></svg>',
    "zoom":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>',
    "pen":          '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/></svg>',
    "note":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15.5 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8.5L15.5 3z"/><polyline points="14 3 14 8 21 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>',
    "transform":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="1" stroke-dasharray="4 2"/><circle cx="4" cy="4" r="2" fill="currentColor"/><circle cx="20" cy="4" r="2" fill="currentColor"/><circle cx="20" cy="20" r="2" fill="currentColor"/><circle cx="4" cy="20" r="2" fill="currentColor"/></svg>',
    "perspective":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 20L7 4h10l4 16H3z"/><circle cx="7" cy="4" r="1.5" fill="currentColor"/><circle cx="17" cy="4" r="1.5" fill="currentColor"/><circle cx="20" cy="20" r="1.5" fill="currentColor"/><circle cx="3" cy="20" r="1.5" fill="currentColor"/></svg>',
    "warp":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12 C6 5, 11 4, 12 12 S18 20, 21 12"/><circle cx="12" cy="12" r="3"/></svg>',
    "blur-sharpen": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="7" stroke-dasharray="3 2"/><line x1="12" y1="5" x2="12" y2="2"/><line x1="12" y1="22" x2="12" y2="19"/><line x1="5" y1="12" x2="2" y2="12"/><line x1="22" y1="12" x2="19" y2="12"/></svg>',
    "select-color":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5" stroke-dasharray="3 2"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>',
    "magnetic-lasso": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12c0 3.31 2.69 6 6 6 1.5 0 2.87-.55 3.9-1.46"/><path d="M21 12c0-3.31-2.69-6-6-6-1.5 0-2.87.55-3.9 1.46"/><polyline points="17 8 21 12 17 16"/><circle cx="9" cy="12" r="1.5" fill="currentColor"/><circle cx="15" cy="12" r="1.5" fill="currentColor"/></svg>',
    "ai":           '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4m-10-10h4m12 0h4m-3.07-7.07-2.83 2.83m-8.2 8.2-2.83 2.83m14.14 0-2.83-2.83m-8.2-8.2L2.93 4.93"/></svg>',
    "grid":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>',
    "ruler":        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="10" rx="1"/><line x1="6" y1="7" x2="6" y2="12"/><line x1="10" y1="7" x2="10" y2="11"/><line x1="14" y1="7" x2="14" y2="12"/><line x1="18" y1="7" x2="18" y2="11"/></svg>',
    "histogram":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="20" x2="21" y2="20"/><rect x="3" y="14" width="3" height="6" fill="currentColor" stroke="none" opacity=".5"/><rect x="8" y="8" width="3" height="12" fill="currentColor" stroke="none" opacity=".7"/><rect x="13" y="5" width="3" height="15" fill="currentColor" stroke="none"/><rect x="18" y="11" width="3" height="9" fill="currentColor" stroke="none" opacity=".6"/></svg>',
    "navigator":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><rect x="7" y="7" width="10" height="6" stroke="currentColor" stroke-width="1.5"/><line x1="2" y1="20" x2="22" y2="20"/></svg>',
    "remove-bg":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a9 9 0 1 0 0 18A9 9 0 0 0 12 3z"/><path d="M4 12s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5z" fill="currentColor" opacity=".2"/><circle cx="12" cy="12" r="3" fill="currentColor" opacity=".5"/></svg>',
    # Layer panel
    "layer-new":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" opacity=".3" fill="currentColor" stroke="none"/><rect x="3" y="11" width="18" height="9" rx="1.5"/><line x1="12" y1="14" x2="12" y2="17"/><line x1="10.5" y1="15.5" x2="13.5" y2="15.5"/><rect x="5" y="6" width="14" height="7" rx="1.5" opacity=".5" fill="currentColor" stroke="none"/><rect x="7" y="3" width="10" height="5" rx="1" opacity=".25" fill="currentColor" stroke="none"/></svg>',
    "layer-dup":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="8" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    "layer-merge":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="5" rx="1" opacity=".4" fill="currentColor" stroke="none"/><rect x="3" y="16" width="18" height="5" rx="1" fill="currentColor" stroke="none" opacity=".9"/><polyline points="8 11 12 15 16 11"/><line x1="12" y1="8" x2="12" y2="15"/></svg>',
    "layer-del":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>',
    "eye-open":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
    "eye-closed":   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
    "lock-open":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>',
    "lock-closed":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    # Align
    "al-left":      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="3" y1="3" x2="3" y2="21"/><rect x="5" y="7" width="9" height="4" rx="1" fill="currentColor" stroke="none" opacity=".8"/><rect x="5" y="13" width="14" height="4" rx="1" fill="currentColor" stroke="none" opacity=".4"/></svg>',
    "al-center-h":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="12" y1="3" x2="12" y2="21"/><rect x="5" y="7" width="14" height="4" rx="1" fill="currentColor" stroke="none" opacity=".8"/><rect x="7" y="13" width="10" height="4" rx="1" fill="currentColor" stroke="none" opacity=".4"/></svg>',
    "al-right":     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="21" y1="3" x2="21" y2="21"/><rect x="10" y="7" width="9" height="4" rx="1" fill="currentColor" stroke="none" opacity=".8"/><rect x="5" y="13" width="14" height="4" rx="1" fill="currentColor" stroke="none" opacity=".4"/></svg>',
    "al-top":       '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="3" y1="3" x2="21" y2="3"/><rect x="7" y="5" width="4" height="9" rx="1" fill="currentColor" stroke="none" opacity=".8"/><rect x="13" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none" opacity=".4"/></svg>',
    "al-center-v":  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="3" y1="12" x2="21" y2="12"/><rect x="7" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none" opacity=".8"/><rect x="13" y="7" width="4" height="10" rx="1" fill="currentColor" stroke="none" opacity=".4"/></svg>',
    "al-bottom":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="3" y1="21" x2="21" y2="21"/><rect x="7" y="10" width="4" height="9" rx="1" fill="currentColor" stroke="none" opacity=".8"/><rect x="13" y="5" width="4" height="14" rx="1" fill="currentColor" stroke="none" opacity=".4"/></svg>',
    # Misc
    "clipboard":    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="2" width="6" height="4" rx="1"/><path d="M9 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2h-3"/><path d="M9 12h6"/><path d="M9 16h4"/></svg>',
    "undo":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>',
    "redo":         '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13"/></svg>',
}

def svg_icon(key, color=C.TEXT_SEC, size=None):
    """Render an SVG icon from _SVG_ICONS dict to a QIcon."""
    sz = size or dp(18)
    raw = _SVG_ICONS.get(key, "")
    if not raw:
        px = QPixmap(sz, sz); px.fill(Qt.transparent); return QIcon(px)
    colored = raw.replace("currentColor", color)
    data = colored.encode("utf-8")
    renderer = QSvgRenderer(QByteArray(data))
    px = QPixmap(sz, sz); px.fill(Qt.transparent)
    p = QPainter(px)
    renderer.render(p)
    p.end()
    return QIcon(px)

# ── Layer ─────────────────────────────────────────────────────────────────────
class Layer:
    BLEND_MODES = ["Normal", "Multiply", "Screen", "Overlay", "Darken",
                   "Lighten", "Difference", "Color Dodge", "Color Burn"]

    def __init__(self, name="Layer", width=800, height=600, image=None):
        self.name = name
        self.visible = True
        self.opacity = 255
        self.blend_mode = "Normal"
        self.locked = False
        self.image = image.convert("RGBA") if image is not None else Image.new("RGBA", (width, height), (0, 0, 0, 0))
        # ── Layer mask ────────────────────────────────────────────────────────
        self.mask          = None    # PIL Image "L" — None means no mask
        self.mask_enabled  = True    # toggle without deleting
        self.editing_mask  = False   # True → paint strokes go to mask, not image
        # ── Layer effects (fx stack) ──────────────────────────────────────────
        self.effects       = []      # list of effect dicts (ordered, non-destructive)

    def copy(self):
        l = Layer(self.name + " copy")
        l.image = self.image.copy()
        l.visible = self.visible
        l.opacity = self.opacity
        l.blend_mode = self.blend_mode
        l.locked = self.locked
        if self.mask is not None:
            l.mask = self.mask.copy()
        l.mask_enabled = self.mask_enabled
        l.editing_mask = False   # never copy the "editing" state
        l.effects = [dict(fx) for fx in self.effects]  # deep copy effect dicts
        return l

    def add_mask(self, mode="white"):
        """Add a layer mask. mode: 'white'=fully visible, 'black'=fully hidden, 'selection'=from caller."""
        iw, ih = self.image.size
        if mode == "black":
            self.mask = Image.new("L", (iw, ih), 0)
        else:
            self.mask = Image.new("L", (iw, ih), 255)
        self.mask_enabled = True

    def apply_mask(self):
        """Bake the mask into the layer alpha and remove it."""
        if self.mask is None: return
        r, g, b, a = self.image.split()
        new_a = ImageChops.multiply(a, self.mask) if self.mask_enabled else a
        self.image = Image.merge("RGBA", (r, g, b, new_a))
        self.mask = None
        self.editing_mask = False

    def delete_mask(self):
        self.mask = None
        self.editing_mask = False

    def mask_from_selection(self, sel_mask):
        """Set mask from an L-mode selection mask."""
        iw, ih = self.image.size
        if sel_mask.size != (iw, ih):
            sel_mask = sel_mask.resize((iw, ih), Image.LANCZOS)
        self.mask = sel_mask.copy()
        self.mask_enabled = True

# ── History ───────────────────────────────────────────────────────────────────
class HistoryManager:
    def __init__(self, max_states=30):
        self.undo_stack = deque(maxlen=max_states)
        self.redo_stack = deque(maxlen=max_states)
        self.labels = deque(maxlen=max_states)

    def save_state(self, layers, active_index, label="Edit"):
        state = self._snap(layers, active_index)
        self.undo_stack.append((state, label))
        self.redo_stack.clear()

    def undo(self, current_layers, current_index):
        if not self.undo_stack: return None, None, None
        (restore, lbl) = self.undo_stack.pop()
        self.redo_stack.append((self._snap(current_layers, current_index), lbl))
        return restore[0], restore[1], lbl

    def redo(self, current_layers, current_index):
        if not self.redo_stack: return None, None, None
        (restore, lbl) = self.redo_stack.pop()
        self.undo_stack.append((self._snap(current_layers, current_index), lbl))
        return restore[0], restore[1], lbl

    def _snap(self, layers, idx):
        state = []
        for l in layers:
            s = Layer(l.name)
            s.image = l.image.copy()
            s.visible = l.visible
            s.opacity = l.opacity
            s.blend_mode = l.blend_mode
            s.locked = l.locked
            state.append(s)
        return (state, idx)

    def all_labels(self):
        return [lbl for (_, lbl) in self.undo_stack]

# ── Marching Ants ─────────────────────────────────────────────────────────────
def build_marching_path(mask_np):
    h, w = mask_np.shape
    if mask_np.max() == 0: return None
    binary = (mask_np > 127).astype(np.uint8)
    path = QPainterPath()
    padded_h = np.pad(binary, ((1, 1), (0, 0)), mode="constant", constant_values=0)
    diff_h = padded_h[1:, :] != padded_h[:-1, :]
    for y in range(h + 1):
        row = diff_h[y]
        if not np.any(row): continue
        pr = np.concatenate(([0], row.astype(np.uint8), [0]))
        d = np.diff(pr); starts = np.where(d == 1)[0]; ends = np.where(d == -1)[0]
        for s, e in zip(starts, ends):
            path.moveTo(s, y); path.lineTo(e, y)
    padded_v = np.pad(binary, ((0, 0), (1, 1)), mode="constant", constant_values=0)
    diff_v = padded_v[:, 1:] != padded_v[:, :-1]
    for x in range(w + 1):
        col = diff_v[:, x]
        if not np.any(col): continue
        pc = np.concatenate(([0], col.astype(np.uint8), [0]))
        d = np.diff(pc); starts = np.where(d == 1)[0]; ends = np.where(d == -1)[0]
        for s, e in zip(starts, ends):
            path.moveTo(x, s); path.lineTo(x, e)
    return path

# ── FlyoutToolButton ──────────────────────────────────────────────────────────
class FlyoutToolButton(QToolButton):
    """Tool button with flyout sub-tool menu on press-hold (300 ms)."""
    tool_selected = pyqtSignal(str)

    def __init__(self, primary_tool, flyout_tools, editor_ref, parent=None):
        super().__init__(parent)
        self.primary_tool = primary_tool
        self.flyout_tools = flyout_tools
        self.editor_ref = editor_ref
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._show_flyout)
        self._active_tool = primary_tool
        self._has_flyout = len(flyout_tools) > 1
        sz = dp(34)
        self.setFixedSize(sz, sz)
        self.setCheckable(True)
        self._update_icon()

    def _update_icon(self):
        col = C.ACCENT if self.isChecked() else C.TEXT_SEC
        self.setIcon(svg_icon(self._active_tool, col, dp(18)))
        label = self._active_tool.replace("-", " ").replace("_", " ").title()
        suffix = "  [hold for more]" if self._has_flyout else ""
        self.setToolTip(f"{label}{suffix}")

    def set_active_tool(self, tool_id):
        if tool_id in [t for t, _ in self.flyout_tools]:
            self._active_tool = tool_id
            self._update_icon()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._has_flyout:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            col = QColor(C.ACCENT) if self.isChecked() else QColor(C.TEXT_MUT)
            p.setBrush(col)
            p.setPen(Qt.NoPen)
            s = 4
            x, y = self.width() - 2, self.height() - 2
            pts = QPolygon([QPoint(x - s, y), QPoint(x, y - s), QPoint(x, y)])
            p.drawPolygon(pts)
            p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._hold_timer.start(300)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._hold_timer.isActive():
            self._hold_timer.stop()
            self.tool_selected.emit(self._active_tool)
        super().mouseReleaseEvent(e)

    def _show_flyout(self):
        menu = QMenu(self)
        for tool_id, tip in self.flyout_tools:
            act = menu.addAction(svg_icon(tool_id, C.TEXT_PRI, dp(15)), "  " + tip)
            act.setData(tool_id)
            if tool_id == self._active_tool:
                act.setCheckable(True); act.setChecked(True)
        chosen = menu.exec_(self.mapToGlobal(self.rect().bottomRight() + QPoint(2, 0)))
        if chosen and chosen.data():
            self._active_tool = chosen.data()
            self._update_icon()
            self.tool_selected.emit(self._active_tool)

# ── LayerGroup ───────────────────────────────────────────────────────────────
class LayerGroup(Layer):
    """A layer that contains child layers composited together."""

    def __init__(self, name="Group", width=800, height=600):
        # Don't call Layer.__init__ image creation — we compute image from children
        self.name         = name
        self.visible      = True
        self.opacity      = 255
        self.blend_mode   = "Normal"
        self.locked       = False
        self.mask         = None
        self.mask_enabled = True
        self.editing_mask = False
        self.effects      = []
        self.children     = []   # list of Layer objects
        self.collapsed    = False
        self._w           = width
        self._h           = height

    @property
    def image(self):
        """Composite children into a single RGBA image (live)."""
        result = Image.new("RGBA", (self._w, self._h), (0, 0, 0, 0))
        for child in self.children:
            if not child.visible: continue
            img = child.image.copy()
            if child.mask is not None and child.mask_enabled:
                r, g, b, a = img.split()
                img = Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, child.mask)))
            if child.opacity < 255:
                r, g, b, a = img.split()
                a = a.point(lambda x: int(x * child.opacity / 255))
                img = Image.merge("RGBA", (r, g, b, a))
            result.paste(img, (0, 0), img)
        return result

    @image.setter
    def image(self, val):
        pass  # groups don't have a pixel buffer to set directly

    def copy(self):
        g = LayerGroup(self.name + " copy", self._w, self._h)
        g.visible      = self.visible
        g.opacity      = self.opacity
        g.blend_mode   = self.blend_mode
        g.locked       = self.locked
        g.effects      = [dict(fx) for fx in self.effects]
        g.collapsed    = self.collapsed
        g.children     = [c.copy() for c in self.children]
        if self.mask: g.mask = self.mask.copy()
        g.mask_enabled = self.mask_enabled
        return g


# ── CanvasWidget ──────────────────────────────────────────────────────────────
class CanvasWidget(QWidget):
    color_picked = pyqtSignal(QColor)
    status_update = pyqtSignal(str)
    zoom_changed = pyqtSignal(float, float, float)  # zoom, pan_x, pan_y

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.zoom = 1.0
        self.pan_offset = QPointF(0, 0)
        self.panning = False
        self.pan_start = QPointF()
        self.last_pos = None
        self._cursor_pos = None
        self.drawing = False
        self.selection_start = None
        self.selection_rect = None
        self.selection_mask = None
        self.marching_ants_path = None
        self.marching_offset = 0
        self.crop_rect = None
        self._lasso_points = []
        self._checker_tile = None
        self._shape_start = None
        self._measure_start = None
        self._measure_end = None
        # ── Quick Mask state ──────────────────────────────────────────────────
        self._quick_mask_prev = None  # saved selection before entering quick mask
        self._quick_mask_layer = None # PIL L image used as the mask canvas
        # ── Magnetic Scissors state ───────────────────────────────────────────
        self._mag_anchors = []        # list of QPointF (image coords)
        self._mag_preview = None      # cursor QPointF for live edge preview
        self._mag_edge_map = None     # computed edge-strength numpy array
        # ── Rotate View ───────────────────────────────────────────────────────
        self.canvas_angle = 0.0       # degrees — view-only rotation, not destructive
        # ── Guides ────────────────────────────────────────────────────────────
        self._guides = []             # list of {'orientation': 'h'|'v', 'pos': int}
        self._dragging_guide = None   # index into _guides while dragging
        self._snap_to_guides = True
        self.snap_threshold_px = 8    # pixels in screen space
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"background-color: {C.CANVAS_BG};")
        self.march_timer = QTimer()
        self.march_timer.timeout.connect(self._march_tick)
        self.march_timer.start(100)
        # Grid
        self._show_grid = False
        self._grid_size = 32  # pixels
        # Navigator callback
        self._nav_update_cb = None

    def _march_tick(self):
        if self.marching_ants_path is not None or self.selection_rect is not None:
            self.marching_offset = (self.marching_offset + 1) % 12
            self.update()
        elif self.editor.current_tool == "crop":
            # Keep crop overlay repainting while drawing selection
            if self.drawing:
                self.update()

    def _update_marching_path(self):
        if self.selection_mask is None:
            self.marching_ants_path = None
            return
        self.marching_ants_path = build_marching_path(np.array(self.selection_mask))

    def set_selection_mask(self, mask):
        self.selection_mask = mask
        self._update_marching_path()

    def canvas_to_image(self, pos):
        return QPointF((pos.x() - self.pan_offset.x()) / self.zoom,
                       (pos.y() - self.pan_offset.y()) / self.zoom)

    def image_to_canvas(self, pos):
        return QPointF(pos.x() * self.zoom + self.pan_offset.x(),
                       pos.y() * self.zoom + self.pan_offset.y())

    def image_to_canvas_f(self, x, y):
        """image_to_canvas for raw floats."""
        return QPointF(x * self.zoom + self.pan_offset.x(),
                       y * self.zoom + self.pan_offset.y())

    def fit_in_view(self):
        if not self.editor.layers: return
        iw, ih = self.editor.layers[0].image.size
        vw, vh = self.width(), self.height()
        self.zoom = min(vw / iw, vh / ih) * 0.9
        self.pan_offset = QPointF((vw - iw * self.zoom) / 2, (vh - ih * self.zoom) / 2)
        self.zoom_changed.emit(self.zoom, self.pan_offset.x(), self.pan_offset.y())
        self.update()

    def _get_checker(self):
        if self._checker_tile is None:
            cs = dp(16)
            self._checker_tile = QPixmap(cs * 2, cs * 2)
            tp = QPainter(self._checker_tile)
            tp.fillRect(0, 0, cs, cs, QColor("#2a2a2a"))
            tp.fillRect(cs, 0, cs, cs, QColor("#222222"))
            tp.fillRect(0, cs, cs, cs, QColor("#222222"))
            tp.fillRect(cs, cs, cs, cs, QColor("#2a2a2a"))
            tp.end()
        return self._checker_tile

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(C.CANVAS_BG))
        if not self.editor.layers:
            painter.setPen(QColor(C.TEXT_MUT))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(self.rect(), Qt.AlignCenter, "Open or create an image to begin")
            painter.end()
            return
        composite = self.editor.get_composite()
        if composite is None:
            painter.end()
            return
        data = composite.tobytes("raw", "RGBA")
        qimg = QImage(data, composite.width, composite.height, QImage.Format_RGBA8888)
        painter.save()
        # Rotate view around canvas center
        if self.canvas_angle != 0.0:
            cx, cy = self.width() / 2, self.height() / 2
            painter.translate(cx, cy)
            painter.rotate(self.canvas_angle)
            painter.translate(-cx, -cy)
        painter.translate(self.pan_offset)
        painter.scale(self.zoom, self.zoom)
        # Checkerboard
        tile = self._get_checker()
        tw, th = tile.width(), tile.height()
        for y in range(0, composite.height, th):
            for x in range(0, composite.width, tw):
                dw = min(tw, composite.width - x)
                dh = min(th, composite.height - y)
                painter.drawPixmap(x, y, dw, dh, tile, 0, 0, dw, dh)
        painter.drawImage(0, 0, qimg)
        # Marching ants
        if self.marching_ants_path is not None:
            pen_b = QPen(QColor(0, 0, 0), 1.0); pen_b.setCosmetic(True)
            painter.setPen(pen_b); painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.marching_ants_path)
            pen_w = QPen(QColor(255, 255, 255), 1.0, Qt.DashLine); pen_w.setCosmetic(True)
            pen_w.setDashPattern([4, 4]); pen_w.setDashOffset(self.marching_offset)
            painter.setPen(pen_w); painter.drawPath(self.marching_ants_path)
        elif self.selection_rect is not None:
            pen_b = QPen(QColor(0, 0, 0), 1.0); pen_b.setCosmetic(True)
            painter.setPen(pen_b); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.selection_rect)
            pen_w = QPen(QColor(255, 255, 255), 1.0, Qt.DashLine); pen_w.setCosmetic(True)
            pen_w.setDashPattern([4, 4]); pen_w.setDashOffset(self.marching_offset)
            painter.setPen(pen_w); painter.drawRect(self.selection_rect)
        # Lasso in-progress
        if self.drawing and self.editor.current_tool == "lasso" and len(self._lasso_points) > 1:
            pen_l = QPen(QColor(C.ACCENT), 1.0, Qt.DashLine); pen_l.setCosmetic(True)
            painter.setPen(pen_l)
            for i in range(len(self._lasso_points) - 1):
                painter.drawLine(self._lasso_points[i], self._lasso_points[i + 1])
        # Shape preview
        if (self.drawing and self._shape_start and self.last_pos and
                self.editor.current_tool in ("rect", "ellipse", "line", "arrow", "triangle")):
            pen_s = QPen(QColor(C.ACCENT), 1.5, Qt.DashLine); pen_s.setCosmetic(True)
            painter.setPen(pen_s); painter.setBrush(Qt.NoBrush)
            s, e = self._shape_start, self.last_pos
            t = self.editor.current_tool
            r = QRectF(min(s.x(), e.x()), min(s.y(), e.y()), abs(e.x() - s.x()), abs(e.y() - s.y()))
            if t == "rect": painter.drawRect(r)
            elif t == "ellipse": painter.drawEllipse(r)
            elif t in ("line", "arrow"): painter.drawLine(s, e)
            elif t == "triangle":
                pts = [QPointF((s.x() + e.x()) / 2, min(s.y(), e.y())),
                       QPointF(min(s.x(), e.x()), max(s.y(), e.y())),
                       QPointF(max(s.x(), e.x()), max(s.y(), e.y()))]
                painter.drawPolygon(QPolygonF(pts))
        # Gradient preview line
        if (self.drawing and self._shape_start and self.last_pos and
                self.editor.current_tool == "gradient"):
            pen_g = QPen(QColor(C.RED), 1.5, Qt.DashLine); pen_g.setCosmetic(True)
            painter.setPen(pen_g); painter.drawLine(self._shape_start, self.last_pos)
        # Crop overlay
        _in_crop_mode = self.editor.current_tool == "crop"
        if _in_crop_mode and self.crop_rect is None:
            # Tool selected but no rect drawn yet — dim entire image to signal mode
            painter.fillRect(QRectF(0, 0, composite.width, composite.height),
                             QColor(0, 0, 0, 80))
        elif self.crop_rect is not None:
            # 1. Dim the outside first so border draws on top
            ov = QPainterPath()
            ov.addRect(QRectF(0, 0, composite.width, composite.height))
            inn = QPainterPath(); inn.addRect(self.crop_rect)
            painter.fillPath(ov.subtracted(inn), QColor(0, 0, 0, 130))
            # 2. Rule-of-thirds grid inside crop rect
            r = self.crop_rect
            pen_g = QPen(QColor(255, 255, 255, 55), 0.5); pen_g.setCosmetic(True)
            painter.setPen(pen_g)
            for i in (1, 2):
                painter.drawLine(QPointF(r.x() + r.width() * i / 3, r.y()),
                                 QPointF(r.x() + r.width() * i / 3, r.y() + r.height()))
                painter.drawLine(QPointF(r.x(), r.y() + r.height() * i / 3),
                                 QPointF(r.x() + r.width(), r.y() + r.height() * i / 3))
            # 3. Border on top
            pen_c = QPen(QColor(C.ACCENT), 2.0); pen_c.setCosmetic(True)
            painter.setPen(pen_c); painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.crop_rect)
            # 4. Corner + midpoint handles
            hw = 8
            handles = [
                QPointF(r.x(), r.y()), QPointF(r.x() + r.width(), r.y()),
                QPointF(r.x(), r.y() + r.height()), QPointF(r.x() + r.width(), r.y() + r.height()),
                QPointF(r.x() + r.width() / 2, r.y()), QPointF(r.x() + r.width() / 2, r.y() + r.height()),
                QPointF(r.x(), r.y() + r.height() / 2), QPointF(r.x() + r.width(), r.y() + r.height() / 2),
            ]
            painter.setPen(QPen(QColor(C.ACCENT), 1.5)); painter.setBrush(QColor(C.BG0))
            for h in handles:
                painter.drawRect(QRectF(h.x() - hw / 2, h.y() - hw / 2, hw, hw))
            # 5. Size label inside rect
            painter.setPen(QColor(255, 255, 255, 200))
            painter.setFont(QFont("Segoe UI", 8))
            lbl = f"{int(r.width())} × {int(r.height())}  ·  Enter to apply  ·  Esc to cancel"
            painter.drawText(QPointF(r.x() + 6, r.y() + r.height() - 6), lbl)
        # Measure line
        if self._measure_start and self._measure_end:
            pen_m = QPen(QColor(C.YELLOW), 2.0); pen_m.setCosmetic(True)
            painter.setPen(pen_m)
            painter.drawLine(self._measure_start, self._measure_end)
            dx = self._measure_end.x() - self._measure_start.x()
            dy = self._measure_end.y() - self._measure_start.y()
            dist = math.sqrt(dx * dx + dy * dy)
            angle = math.degrees(math.atan2(dy, dx))
            mid = QPointF((self._measure_start.x() + self._measure_end.x()) / 2,
                          (self._measure_start.y() + self._measure_end.y()) / 2)
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(mid + QPointF(4, -6), f"{dist:.1f}px  {angle:.1f}°")
        # Grid overlay
        if self._show_grid and self.editor.layers:
            w, h = self.editor.layers[0].image.size
            gs = self._grid_size
            pen_g = QPen(QColor(255, 255, 255, 30), 0.5); pen_g.setCosmetic(True)
            painter.setPen(pen_g)
            for x in range(0, w + gs, gs):
                painter.drawLine(QPointF(x, 0), QPointF(x, h))
            for y in range(0, h + gs, gs):
                painter.drawLine(QPointF(0, y), QPointF(w, y))
        # ── Guide lines ───────────────────────────────────────────────────────
        if self._guides:
            self._paint_guides(painter)
        painter.restore()
        # ── Guide overlay labels (screen-space) ───────────────────────────────
        if self._guides:
            self._paint_guide_labels(painter)
        # ── Layer mask rubylith overlay ────────────────────────────────────────
        layer = self.editor.active_layer() if self.editor.layers else None
        if layer and getattr(layer, 'editing_mask', False) and layer.mask is not None:
            self._paint_rubylith(painter, layer)
        # ── Quick Mask overlay ────────────────────────────────────────────────
        if getattr(self.editor, 'quick_mask_active', False) and self._quick_mask_layer is not None:
            self._paint_quick_mask(painter)
        # ── Magnetic Scissors preview ─────────────────────────────────────────
        if self.editor.current_tool == "magnetic-lasso" and self._mag_anchors:
            self._paint_mag_scissors(painter)
        # ── Free Transform overlay ────────────────────────────────────────────
        if getattr(self, '_xform_active', False) and self.editor.layers:
            self._paint_xform_overlay(painter)
        # ── Perspective Transform overlay ──────────────────────────────────────
        if getattr(self, '_persp_active', False) and self.editor.layers:
            self._paint_persp_overlay(painter)
        # Brush-size cursor ring — drawn in widget (screen) space using the same painter
        # so we avoid QPainter reentrancy issues from opening a second painter.
        _brush_tools = ("brush", "pencil", "spray", "eraser", "clone", "healing",
                        "dodge", "burn", "sponge", "smudge", "pen")
        if (getattr(self, "_cursor_pos", None) is not None and
                self.editor.current_tool in _brush_tools and
                not self.panning):
            sz = self.editor.brush_size
            radius_screen = max(2, sz * self.zoom / 2.0)
            cp = self._cursor_pos
            painter.save()
            painter.resetTransform()   # back to widget coordinates
            painter.setRenderHint(QPainter.Antialiasing, True)
            # White outer ring
            pen_w = QPen(QColor(255, 255, 255, 200), 1.2)
            pen_w.setCosmetic(True)
            painter.setPen(pen_w)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(cp, radius_screen, radius_screen)
            # Black inner ring (offset 1 px smaller for contrast)
            if radius_screen > 3:
                pen_b = QPen(QColor(0, 0, 0, 140), 1.0)
                pen_b.setCosmetic(True)
                painter.setPen(pen_b)
                painter.drawEllipse(cp, radius_screen - 1, radius_screen - 1)
            # Crosshair at centre (small cross)
            ch = dp(3)
            painter.setPen(QPen(QColor(255, 255, 255, 160), 1.0))
            painter.drawLine(QPointF(cp.x() - ch, cp.y()), QPointF(cp.x() + ch, cp.y()))
            painter.drawLine(QPointF(cp.x(), cp.y() - ch), QPointF(cp.x(), cp.y() + ch))
            painter.restore()
        # Update navigator
        if self._nav_update_cb:
            self._nav_update_cb()
        painter.end()

    def mousePressEvent(self, event):
        img_pos = self.canvas_to_image(QPointF(event.pos()))
        tool = self.editor.current_tool
        if (event.button() == Qt.MiddleButton or
                (event.button() == Qt.LeftButton and
                 event.modifiers() & Qt.AltModifier and
                 tool not in ("clone", "healing"))):
            self.panning = True
            self.pan_start = QPointF(event.pos()) - self.pan_offset
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            if not self.editor.layers: return
            # Snap to guides
            img_pos = self._snap_point(img_pos)
            ix, iy = int(img_pos.x()), int(img_pos.y())
            layer = self.editor.active_layer()
            if layer is None: return
            w, h = layer.image.size
            if tool == "move":
                self.last_pos = img_pos; self.drawing = True
            elif tool in ("brush", "pencil", "spray"):
                self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, tool.title())
                self.drawing = True; self.last_pos = img_pos
                if layer and getattr(layer, 'editing_mask', False) and layer.mask is not None:
                    self._draw_brush_on_mask(ix, iy)
                else:
                    self._draw_brush(ix, iy)
                self.update()
            elif tool == "eraser":
                self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Erase")
                self.drawing = True; self.last_pos = img_pos
                if layer and getattr(layer, 'editing_mask', False) and layer.mask is not None:
                    # Eraser on mask = paint black (hide)
                    orig_fg = self.editor.fg_color
                    self.editor.fg_color = QColor(0, 0, 0)
                    self._draw_brush_on_mask(ix, iy)
                    self.editor.fg_color = orig_fg
                else:
                    self._draw_eraser(ix, iy)
                self.update()
            elif tool == "eyedropper":
                if 0 <= ix < w and 0 <= iy < h:
                    comp = self.editor.get_composite()
                    if comp:
                        r, g, b, a = comp.getpixel((ix, iy))
                        self.color_picked.emit(QColor(r, g, b))
            elif tool == "fill":
                self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Fill")
                self._flood_fill(ix, iy); self.update()
            elif tool == "magic-wand":
                self._magic_wand_select(ix, iy); self.update()
            elif tool in ("marquee-rect", "marquee-ellipse"):
                self.selection_start = img_pos; self.selection_rect = None
                self.set_selection_mask(None); self.drawing = True
            elif tool == "crop":
                self.selection_start = img_pos; self.crop_rect = None; self.drawing = True
            elif tool == "text":
                self.editor.insert_text_at(ix, iy)
            elif tool == "lasso":
                self._lasso_points = [img_pos]; self.drawing = True
            elif tool == "clone":
                if event.modifiers() & Qt.AltModifier:
                    self.editor.clone_source = (ix, iy)
                    self.status_update.emit(f"Clone source → ({ix}, {iy})")
                elif self.editor.clone_source:
                    self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Clone Stamp")
                    self.drawing = True; self.last_pos = img_pos; self._draw_clone_stamp(ix, iy)
            elif tool == "healing":
                if event.modifiers() & Qt.AltModifier:
                    self.editor.clone_source = (ix, iy)
                    self.status_update.emit(f"Healing source → ({ix}, {iy})")
                else:
                    self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Healing")
                    self.drawing = True; self.last_pos = img_pos; self._draw_healing(ix, iy)
            elif tool in ("dodge", "burn", "sponge", "smudge"):
                self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, tool.title())
                self.drawing = True; self.last_pos = img_pos; self._draw_retouch(tool, ix, iy)
            elif tool in ("rect", "ellipse", "line", "arrow", "triangle", "polygon", "star"):
                self._shape_start = img_pos; self.last_pos = img_pos; self.drawing = True
            elif tool == "gradient":
                self._shape_start = img_pos; self.last_pos = img_pos; self.drawing = True
            elif tool == "pattern":
                self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Pattern Fill")
                self._draw_pattern_fill(ix, iy)
            elif tool == "measure":
                self._measure_start = img_pos; self._measure_end = img_pos; self.drawing = True
            elif tool == "pen":
                # Pen tool draws bezier-like smooth strokes
                if not self.drawing:
                    self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Pen")
                    self.drawing = True
                self.last_pos = img_pos
            elif tool == "note":
                self.editor.insert_note_at(ix, iy)
            elif tool == "transform":
                if self._xform_active:
                    hit = self._xform_hit_test(QPointF(event.pos()))
                    if hit:
                        self._xform_handle = hit
                        self._xform_drag_wp = QPointF(event.pos())
                        self._xform_start = (self._xform_cx, self._xform_cy,
                                             self._xform_w, self._xform_h,
                                             self._xform_angle)
                else:
                    self.xform_enter()
            elif tool == "perspective":
                if self._persp_active:
                    # Find nearest corner
                    wp = QPointF(event.pos())
                    best, best_d = -1, float("inf")
                    for i, corner in enumerate(self._persp_corners):
                        cw = self.image_to_canvas(corner)
                        d = (wp - cw).manhattanLength()
                        if d < best_d:
                            best_d, best = d, i
                    if best_d < dp(12):
                        self._persp_drag_i = best
                else:
                    self.persp_enter()
            elif tool == "warp":
                layer = self.editor.active_layer()
                if layer and not layer.locked:
                    if self._warp_orig is None:
                        self._warp_orig = layer.image.copy()
                        self.editor.history.save_state(self.editor.layers,
                            self.editor.active_layer_index, "Warp Transform")
                    self.drawing = True; self.last_pos = img_pos
                    self._apply_warp(layer, ix, iy, 0, 0)
            elif tool == "blur-sharpen":
                layer = self.editor.active_layer()
                if layer and not layer.locked:
                    self.editor.history.save_state(self.editor.layers,
                        self.editor.active_layer_index, "Blur/Sharpen")
                    self.drawing = True; self.last_pos = img_pos
                    self._apply_blur_sharpen(layer, ix, iy)
            elif tool == "red-eye":
                self.editor.history.save_state(
                    self.editor.layers, self.editor.active_layer_index, "Red Eye Removal")
                self._apply_red_eye(ix, iy)
            elif tool == "magnetic-lasso":
                if event.modifiers() & Qt.ControlModifier and len(self._mag_anchors) >= 3:
                    # Ctrl+Click = close and finalize
                    self.mag_scissors_finalize()
                else:
                    # Single click = place anchor (snapped to edge)
                    snapped = self._mag_snap_to_edge(img_pos)
                    self._mag_anchors.append(snapped)
                    self._mag_edge_map = None  # recompute on next snap
                self.update()
            elif tool == "select-color":
                self._select_by_color(ix, iy)
            elif tool in ("brush", "pencil", "spray", "eraser") and self.editor.quick_mask_active:
                # Quick mask: redirect strokes to the mask layer
                self.drawing = True; self.last_pos = img_pos
                self._paint_quick_mask_stroke(ix, iy); self.update()

    def mouseMoveEvent(self, event):
        img_pos = self.canvas_to_image(QPointF(event.pos()))
        ix, iy = int(img_pos.x()), int(img_pos.y())
        # Track cursor position for brush ring overlay
        self._cursor_pos = QPointF(event.pos())
        _brush_tools = ("brush", "pencil", "spray", "eraser", "clone", "healing",
                        "dodge", "burn", "sponge", "smudge", "pen")
        tool = self.editor.current_tool
        if not self.panning:
            _cursors = {
                "brush": Qt.CrossCursor, "pencil": Qt.CrossCursor,
                "spray": Qt.CrossCursor, "eraser": Qt.CrossCursor,
                "clone": Qt.CrossCursor, "healing": Qt.CrossCursor,
                "dodge": Qt.CrossCursor, "burn": Qt.CrossCursor,
                "sponge": Qt.CrossCursor, "smudge": Qt.CrossCursor,
                "pen": Qt.CrossCursor,
                "eyedropper": Qt.CrossCursor,
                "pan": Qt.OpenHandCursor,
                "zoom": Qt.SizeAllCursor,
                "text": Qt.IBeamCursor,
                "crop": Qt.CrossCursor,
                "measure": Qt.CrossCursor,
                "move": Qt.SizeAllCursor,
                "transform": Qt.SizeAllCursor,
                "perspective": Qt.CrossCursor,
                "warp": Qt.CrossCursor,
                "blur-sharpen": Qt.CrossCursor,
                "select-color":   Qt.CrossCursor,
                "magnetic-lasso": Qt.CrossCursor,
                "red-eye":        Qt.CrossCursor,
            }
            # Dynamic cursor for transform handles
            if tool == "transform" and self._xform_active:
                hit = self._xform_hit_test(QPointF(event.pos()))
                if hit == "rot":
                    self.setCursor(Qt.ForbiddenCursor)
                elif hit in ("tl", "br"):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif hit in ("tr", "bl"):
                    self.setCursor(Qt.SizeBDiagCursor)
                elif hit in ("tc", "bc"):
                    self.setCursor(Qt.SizeVerCursor)
                elif hit in ("ml", "mr"):
                    self.setCursor(Qt.SizeHorCursor)
                elif hit == "body":
                    self.setCursor(Qt.SizeAllCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            else:
                self.setCursor(_cursors.get(tool, Qt.ArrowCursor))
        self.update()
        if self.editor.layers:
            layer = self.editor.active_layer()
            if layer:
                w, h = layer.image.size
                if 0 <= ix < w and 0 <= iy < h:
                    self.status_update.emit(
                        f"  {layer.image.width} × {layer.image.height} px  |  "
                        f"Zoom {self.zoom:.0%}  |  X:{ix}  Y:{iy}  |  "
                        f"{self.editor.current_tool.replace('-',' ').title()}")
        # Update ruler crosshairs
        cp = event.pos()
        if hasattr(self.editor, "_ruler_h") and self.editor._ruler_h.isVisible():
            self.editor._ruler_h.set_mouse_pos(cp.x())
        if hasattr(self.editor, "_ruler_v") and self.editor._ruler_v.isVisible():
            self.editor._ruler_v.set_mouse_pos(cp.y())
        if self.panning:
            self.pan_offset = QPointF(event.pos()) - self.pan_start
            self.update()
            return
        tool = self.editor.current_tool
        if self.drawing and event.buttons() & Qt.LeftButton:
            if tool in ("brush", "pencil", "spray"):
                _layer = self.editor.active_layer()
                if _layer and getattr(_layer, 'editing_mask', False) and _layer.mask is not None:
                    self._draw_brush_line_on_mask(self.last_pos, img_pos)
                else:
                    # Expand canvas if off-canvas painting is enabled
                    if getattr(self.editor, 'off_canvas_paint', False):
                        _ix2, _iy2 = self._expand_canvas_for_stroke(int(img_pos.x()), int(img_pos.y()))
                        img_pos = QPointF(_ix2, _iy2)
                    self._draw_brush_line(self.last_pos, img_pos)
                self.last_pos = img_pos; self.update()
            elif tool == "eraser":
                _layer = self.editor.active_layer()
                if _layer and getattr(_layer, 'editing_mask', False) and _layer.mask is not None:
                    orig_fg = self.editor.fg_color
                    self.editor.fg_color = QColor(0, 0, 0)
                    self._draw_brush_line_on_mask(self.last_pos, img_pos)
                    self.editor.fg_color = orig_fg
                else:
                    self._draw_eraser_line(self.last_pos, img_pos)
                self.last_pos = img_pos; self.update()
            elif tool == "move":
                dx = img_pos.x() - self.last_pos.x()
                dy = img_pos.y() - self.last_pos.y()
                layer = self.editor.active_layer()
                if layer and not layer.locked:
                    # Accumulate offset to avoid rounding drift per step
                    if not hasattr(self, "_move_accum"):
                        self._move_accum = [0.0, 0.0]
                    self._move_accum[0] += dx; self._move_accum[1] += dy
                    ix, iy = int(self._move_accum[0]), int(self._move_accum[1])
                    if ix != 0 or iy != 0:
                        ni = Image.new("RGBA", layer.image.size, (0, 0, 0, 0))
                        ni.paste(layer.image, (ix, iy)); layer.image = ni
                        self._move_accum[0] -= ix; self._move_accum[1] -= iy
                    self.last_pos = img_pos; self.update()
            elif tool in ("marquee-rect", "marquee-ellipse") and self.selection_start:
                x1, y1 = self.selection_start.x(), self.selection_start.y()
                x2, y2 = img_pos.x(), img_pos.y()
                self.selection_rect = QRectF(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
                self.update()
            elif tool == "crop" and self.selection_start:
                x1, y1 = self.selection_start.x(), self.selection_start.y()
                x2, y2 = img_pos.x(), img_pos.y()
                rw, rh = abs(x2 - x1), abs(y2 - y1)
                ratio_str = getattr(self.editor, "crop_ratio", "Free")
                ratio_map = {"Square (1:1)": (1, 1), "4:3": (4, 3), "3:2": (3, 2),
                             "16:9": (16, 9), "16:10": (16, 10), "2:1": (2, 1)}
                if ratio_str in ratio_map:
                    ar_w, ar_h = ratio_map[ratio_str]
                    # Maintain aspect ratio: take larger dimension as reference
                    if rw / max(1, ar_w) > rh / max(1, ar_h):
                        rh = rw * ar_h / ar_w
                    else:
                        rw = rh * ar_w / ar_h
                self.crop_rect = QRectF(min(x1, x2), min(y1, y2), rw, rh)
                self.update()
            elif tool == "lasso":
                self._lasso_points.append(img_pos); self.update()
            elif tool == "clone":
                self._draw_clone_stamp(ix, iy); self.last_pos = img_pos; self.update()
            elif tool == "healing":
                self._draw_healing(ix, iy); self.last_pos = img_pos; self.update()
            elif tool in ("dodge", "burn", "sponge", "smudge"):
                self._draw_retouch(tool, ix, iy); self.last_pos = img_pos; self.update()
            elif tool in ("rect", "ellipse", "line", "arrow", "triangle", "polygon", "star"):
                self.last_pos = img_pos; self.update()
            elif tool == "gradient":
                self.last_pos = img_pos; self.update()
            elif tool == "measure":
                self._measure_end = img_pos; self.update()
            elif tool == "pen":
                if self.last_pos:
                    layer = self.editor.active_layer()
                    if layer and not layer.locked:
                        draw = ImageDraw.Draw(layer.image)
                        c = self.editor.fg_color
                        flow = getattr(self.editor, "pen_flow", 100) / 100.0
                        alpha = int(self.editor.brush_opacity * flow)
                        color = (c.red(), c.green(), c.blue(), alpha)
                        sw = max(1, self.editor.brush_size)
                        x1, y1 = int(self.last_pos.x()), int(self.last_pos.y())
                        x2, y2 = int(img_pos.x()), int(img_pos.y())
                        dist = max(1, int(math.hypot(x2 - x1, y2 - y1)))
                        step = max(1, sw // 3)
                        for i in range(0, dist + 1, step):
                            tv = i / dist
                            px = int(x1 + (x2 - x1) * tv)
                            py = int(y1 + (y2 - y1) * tv)
                            r = sw // 2
                            draw.ellipse((px - r, py - r, px + r, py + r), fill=color)
                    self.last_pos = img_pos; self.update()
            elif tool == "transform" and self._xform_active and self._xform_handle:
                self._xform_drag(QPointF(event.pos()))
            elif tool == "perspective" and self._persp_active and self._persp_drag_i >= 0:
                # Move the dragged corner to new image position
                self._persp_corners[self._persp_drag_i] = img_pos
                self.update()
            elif tool == "magnetic-lasso":
                self._mag_preview = self._mag_snap_to_edge(img_pos, search_radius=14)
                self.update()
            elif (tool in ("brush", "pencil", "spray", "eraser")
                  and self.editor.quick_mask_active and self.drawing):
                self._paint_quick_mask_line(self.last_pos, img_pos)
                self.last_pos = img_pos; self.update()
            elif tool == "warp" and self.drawing:
                layer = self.editor.active_layer()
                if layer and self.last_pos:
                    ddx = int(img_pos.x() - self.last_pos.x())
                    ddy = int(img_pos.y() - self.last_pos.y())
                    self._apply_warp(layer, ix, iy, ddx, ddy)
                    self.last_pos = img_pos; self.update()
            elif tool == "blur-sharpen" and self.drawing:
                layer = self.editor.active_layer()
                if layer:
                    self._apply_blur_sharpen(layer, ix, iy)
                    self.last_pos = img_pos; self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton or (self.panning and event.button() == Qt.LeftButton):
            self.panning = False
            # Restore correct cursor for current tool after panning
            _brush_tools = ("brush", "pencil", "spray", "eraser", "clone", "healing",
                            "dodge", "burn", "sponge", "smudge", "pen")
            tool = self.editor.current_tool
            _cursors = {
                "brush": Qt.CrossCursor, "pencil": Qt.CrossCursor,
                "spray": Qt.CrossCursor, "eraser": Qt.CrossCursor,
                "clone": Qt.CrossCursor, "healing": Qt.CrossCursor,
                "dodge": Qt.CrossCursor, "burn": Qt.CrossCursor,
                "sponge": Qt.CrossCursor, "smudge": Qt.CrossCursor,
                "pen": Qt.CrossCursor,
                "eyedropper": Qt.CrossCursor,
                "pan": Qt.OpenHandCursor, "zoom": Qt.SizeAllCursor,
                "text": Qt.IBeamCursor, "crop": Qt.CrossCursor,
                "measure": Qt.CrossCursor, "move": Qt.SizeAllCursor,
            }
            self.setCursor(_cursors.get(tool, Qt.ArrowCursor))
            return
        if event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())
            return
        if event.button() == Qt.LeftButton:
            tool = self.editor.current_tool
            img_pos = self.canvas_to_image(QPointF(event.pos()))
            if tool in ("marquee-rect", "marquee-ellipse") and self.selection_rect:
                layer = self.editor.active_layer()
                if layer:
                    w, h = layer.image.size
                    mask = Image.new("L", (w, h), 0)
                    draw = ImageDraw.Draw(mask)
                    r = self.selection_rect
                    box = (int(r.x()), int(r.y()), int(r.x() + r.width()), int(r.y() + r.height()))
                    if tool == "marquee-rect": draw.rectangle(box, fill=255)
                    else: draw.ellipse(box, fill=255)
                    # Anti-alias ellipse
                    if tool == "marquee-ellipse" and self.editor.sel_anti_alias:
                        mask = mask.filter(ImageFilter.GaussianBlur(0.6))
                    new_mask = self._apply_feather(mask)
                    self._apply_selection_mode(new_mask)
            elif tool == "lasso" and len(self._lasso_points) > 2:
                layer = self.editor.active_layer()
                if layer:
                    w, h = layer.image.size
                    mask = Image.new("L", (w, h), 0)
                    draw = ImageDraw.Draw(mask)
                    pts = [(int(pt.x()), int(pt.y())) for pt in self._lasso_points]
                    draw.polygon(pts, fill=255)
                    new_mask = self._apply_feather(mask)
                    self._apply_selection_mode(new_mask)
                self._lasso_points = []
            elif tool in ("rect", "ellipse", "line", "arrow", "triangle", "polygon", "star"):
                if self._shape_start and self.last_pos:
                    self._commit_shape(); self._shape_start = None
            elif tool == "gradient" and self._shape_start and self.last_pos:
                self._draw_gradient(self._shape_start, img_pos); self._shape_start = None
            elif tool == "measure":
                if self._measure_start and self._measure_end:
                    dx = self._measure_end.x() - self._measure_start.x()
                    dy = self._measure_end.y() - self._measure_start.y()
                    dist = math.sqrt(dx * dx + dy * dy)
                    angle = math.degrees(math.atan2(dy, dx))
                    self.status_update.emit(f"Measure: {dist:.1f} px  at  {angle:.1f}°")
            elif tool == "transform":
                self._xform_handle = None
                self._xform_drag_wp = None
            elif tool == "perspective":
                self._persp_drag_i = -1
            elif tool == "warp":
                # Done with this warp stroke; keep _warp_orig so user can keep painting
                pass
            elif tool == "blur-sharpen":
                pass
            self.drawing = False; self.update()
            self.editor.update_layer_panel()
            self.editor.update_history_panel()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Q:
            # Toggle Quick Mask
            if self.editor.quick_mask_active:
                self.quick_mask_exit()
            else:
                self.quick_mask_enter()
        elif key == Qt.Key_Escape:
            if self.editor.current_tool == "magnetic-lasso" and self._mag_anchors:
                self._mag_anchors = []
                self._mag_preview = None
                self._mag_edge_map = None
                self.update()
            elif self.editor.current_tool == "transform" and self._xform_active:
                self.xform_cancel()
            elif self.editor.current_tool == "perspective" and self._persp_active:
                self.persp_cancel()
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            if self.editor.current_tool == "magnetic-lasso" and len(self._mag_anchors) >= 3:
                self.mag_scissors_finalize()
            elif self.editor.current_tool == "transform" and self._xform_active:
                self.xform_commit()
            elif self.editor.current_tool == "perspective" and self._persp_active:
                self.persp_commit()
        else:
            super().keyPressEvent(event)

    def leaveEvent(self, event):
        """Clear brush cursor ring and restore normal cursor when leaving canvas."""
        self._cursor_pos = None
        self.setCursor(Qt.ArrowCursor)   # always restore — OS takes over outside widget
        self.update()

    def _show_context_menu(self, global_pos):
        """Right-click context menu on canvas."""
        menu = QMenu(self)
        has_sel = self.selection_mask is not None
        has_layer = self.editor.active_layer() is not None
        menu.addAction("Cut",   self.editor.cut_selection).setEnabled(has_sel and has_layer)
        menu.addAction("Copy",  self.editor.copy_selection).setEnabled(has_sel and has_layer)
        menu.addAction("Paste", self.editor.paste_clipboard).setEnabled(has_layer)
        menu.addAction("Delete", self.editor.delete_selection).setEnabled(has_sel and has_layer)
        menu.addSeparator()
        menu.addAction("Select All",   self.editor.select_all)
        menu.addAction("Deselect",     self.editor.deselect).setEnabled(has_sel)
        menu.addAction("Invert Selection", self.editor.invert_selection).setEnabled(has_layer)
        menu.addSeparator()
        lm = menu.addMenu("New Layer from Selection") if has_sel and has_layer else None
        if lm:
            lm.addAction("Via Copy", self._ctx_layer_via_copy)
            lm.addAction("Via Cut",  self._ctx_layer_via_cut)
        menu.addAction("Flatten Image", self.editor.flatten_image).setEnabled(len(self.editor.layers) > 1)
        menu.exec_(global_pos)

    def _ctx_layer_via_copy(self):
        self.editor.copy_selection()
        self.editor.paste_clipboard()

    def _ctx_layer_via_cut(self):
        self.editor.cut_selection()
        self.editor.paste_clipboard()

    def wheelEvent(self, event):
        old_zoom = self.zoom
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom = max(0.05, min(50.0, self.zoom * factor))
        cp = QPointF(event.pos())
        self.pan_offset = cp - (cp - self.pan_offset) * (self.zoom / old_zoom)
        self.zoom_changed.emit(self.zoom, self.pan_offset.x(), self.pan_offset.y())
        self.update()

    # ── Drawing helpers ───────────────────────────────────────────────────────
    def _make_brush_stamp(self, sz, color):
        """Create a brush stamp image — hard or soft based on brush_hardness."""
        hardness = getattr(self.editor, "brush_hardness", 100) / 100.0
        d = max(2, sz)
        stamp = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        if hardness >= 1.0:
            # Hard brush: simple filled ellipse
            ImageDraw.Draw(stamp).ellipse((0, 0, d - 1, d - 1), fill=color)
        else:
            # Soft brush: radial alpha gradient
            arr = np.zeros((d, d, 4), dtype=np.float64)
            cx, cy = d / 2.0, d / 2.0
            for py in range(d):
                for px in range(d):
                    dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2) / (d / 2.0)
                    if dist >= 1.0: continue
                    # Alpha falloff: hard_edge → 1, soft_edge → cosine falloff
                    if dist <= hardness:
                        alpha = 1.0
                    else:
                        t = (dist - hardness) / (1.0 - hardness)
                        alpha = 0.5 * (1.0 + math.cos(math.pi * t))
                    arr[py, px] = [color[0], color[1], color[2], color[3] * alpha]
            stamp = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        return stamp

    def _draw_brush(self, x, y):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        draw = ImageDraw.Draw(layer.image)
        t = self.editor.current_tool
        sz = self.editor.brush_size if t != "pencil" else max(1, self.editor.shape_stroke_width)
        c = self.editor.fg_color
        color = (c.red(), c.green(), c.blue(), self.editor.brush_opacity)
        if t == "spray":
            density = max(4, sz * 3)
            for _ in range(density):
                ox = random.randint(-sz, sz); oy = random.randint(-sz, sz)
                if ox * ox + oy * oy <= sz * sz:
                    draw.point((x + ox, y + oy), fill=color)
        elif getattr(self.editor, "brush_hardness", 100) < 100:
            stamp = self._make_brush_stamp(sz, color)
            px = x - sz // 2; py = y - sz // 2
            layer.image.paste(stamp, (px, py), stamp)
        else:
            r = sz // 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    def _draw_brush_line(self, p1, p2):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        draw = ImageDraw.Draw(layer.image)
        t = self.editor.current_tool
        sz = self.editor.brush_size if t != "pencil" else max(1, self.editor.shape_stroke_width)
        c = self.editor.fg_color
        color = (c.red(), c.green(), c.blue(), self.editor.brush_opacity)
        x1, y1 = int(p1.x()), int(p1.y())
        x2, y2 = int(p2.x()), int(p2.y())
        dist = max(1, int(math.hypot(x2 - x1, y2 - y1)))
        hardness = getattr(self.editor, "brush_hardness", 100)
        use_soft = (hardness < 100) and (t not in ("spray", "pencil"))
        # Step every brush_size/2 pixels for smooth stroke
        step = max(1, sz // 3)
        for i in range(0, dist + 1, step):
            tv = i / dist
            x, y = int(x1 + (x2 - x1) * tv), int(y1 + (y2 - y1) * tv)
            if t == "spray":
                density = max(2, sz)
                for _ in range(density):
                    ox = random.randint(-sz, sz); oy = random.randint(-sz, sz)
                    if ox * ox + oy * oy <= sz * sz:
                        draw.point((x + ox, y + oy), fill=color)
            elif use_soft:
                stamp = self._make_brush_stamp(sz, color)
                layer.image.paste(stamp, (x - sz // 2, y - sz // 2), stamp)
            else:
                r = sz // 2
                draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    def _draw_eraser(self, x, y):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        sz = self.editor.brush_size
        ImageDraw.Draw(layer.image).ellipse(
            (x - sz // 2, y - sz // 2, x + sz // 2, y + sz // 2), fill=(0, 0, 0, 0))

    def _draw_eraser_line(self, p1, p2):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        draw = ImageDraw.Draw(layer.image)
        sz = self.editor.brush_size
        x1, y1 = int(p1.x()), int(p1.y())
        x2, y2 = int(p2.x()), int(p2.y())
        dist = max(1, int(math.hypot(x2 - x1, y2 - y1)))
        for i in range(dist + 1):
            t = i / dist
            x, y = int(x1 + (x2 - x1) * t), int(y1 + (y2 - y1) * t)
            draw.ellipse((x - sz // 2, y - sz // 2, x + sz // 2, y + sz // 2), fill=(0, 0, 0, 0))

    def _flood_fill(self, x, y):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        w, h = layer.image.size
        if x < 0 or x >= w or y < 0 or y >= h: return
        pixels = layer.image.load()
        target = pixels[x, y]
        c = self.editor.fg_color
        fill_color = (c.red(), c.green(), c.blue(), self.editor.brush_opacity)
        if target == fill_color: return
        tol = self.editor.magic_wand_tolerance

        def match(c1, c2):
            return all(abs(a - b) <= tol for a, b in zip(c1[:3], c2[:3]))

        visited = set(); stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in visited: continue
            if cx < 0 or cx >= w or cy < 0 or cy >= h: continue
            if not match(pixels[cx, cy], target): continue
            visited.add((cx, cy)); pixels[cx, cy] = fill_color
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])

    def _magic_wand_select(self, x, y):
        layer = self.editor.active_layer()
        if not layer: return
        w, h = layer.image.size
        if x < 0 or x >= w or y < 0 or y >= h: return
        source = self.editor.get_composite() if self.editor.magic_wand_sample_all else layer.image
        src_np = np.array(source).astype(np.int16)
        target = src_np[y, x, :3].copy()
        tol = self.editor.magic_wand_tolerance
        diff = np.abs(src_np[:, :, :3] - target.reshape(1, 1, 3))
        match_all = np.all(diff <= tol, axis=2)
        if self.editor.magic_wand_contiguous:
            mask = np.zeros((h, w), dtype=np.uint8)
            if match_all[y, x]:
                stack = [(x, y)]; mask[y, x] = 255
                while stack:
                    sx, sy = stack.pop(); lx = sx
                    while lx > 0 and match_all[sy, lx - 1] and mask[sy, lx - 1] == 0:
                        lx -= 1; mask[sy, lx] = 255
                    rx = sx
                    while rx < w - 1 and match_all[sy, rx + 1] and mask[sy, rx + 1] == 0:
                        rx += 1; mask[sy, rx] = 255
                    for ny in [sy - 1, sy + 1]:
                        if ny < 0 or ny >= h: continue
                        ss = False
                        for nx in range(lx, rx + 1):
                            if match_all[ny, nx] and mask[ny, nx] == 0:
                                if not ss: stack.append((nx, ny)); mask[ny, nx] = 255; ss = True
                            else: ss = False
            new_mask = Image.fromarray(mask, "L")
        else:
            mask = np.where(match_all, 255, 0).astype(np.uint8)
            new_mask = Image.fromarray(mask, "L")
        # Apply feather + selection mode
        new_mask = self._apply_feather(new_mask)
        mods = QApplication.keyboardModifiers()
        if mods & Qt.ShiftModifier:
            orig_mode = self.editor.sel_mode; self.editor.sel_mode = 'add'
            self._apply_selection_mode(new_mask); self.editor.sel_mode = orig_mode
        elif mods & Qt.AltModifier:
            orig_mode = self.editor.sel_mode; self.editor.sel_mode = 'subtract'
            self._apply_selection_mode(new_mask); self.editor.sel_mode = orig_mode
        else:
            self._apply_selection_mode(new_mask)
        self.status_update.emit(f"Magic Wand: {np.count_nonzero(mask)} px selected (tol={tol})")

    def _draw_clone_stamp(self, x, y):
        layer = self.editor.active_layer()
        if not layer or layer.locked or not self.editor.clone_source: return
        sx, sy = self.editor.clone_source
        sz = self.editor.brush_size
        if self.last_pos:
            dx, dy = x - int(self.last_pos.x()), y - int(self.last_pos.y())
        else:
            dx, dy = 0, 0
        self.editor.clone_source = (sx + dx, sy + dy)
        try:
            src = layer.image.crop((sx - sz // 2, sy - sz // 2, sx + sz // 2, sy + sz // 2))
            m = Image.new("L", (sz, sz), 0)
            ImageDraw.Draw(m).ellipse((0, 0, sz, sz), fill=255)
            layer.image.paste(src, (x - sz // 2, y - sz // 2), m)
        except Exception:
            pass

    def _draw_healing(self, x, y):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        w, h = layer.image.size
        sz = self.editor.brush_size; r = sz // 2
        if x - r < 0 or y - r < 0 or x + r >= w or y + r >= h: return
        arr = np.array(layer.image).astype(np.float64)
        region = arr[y - r:y + r, x - r:x + r].copy()
        mask_ring = np.zeros((2 * r, 2 * r), dtype=bool)
        mask_inner = np.zeros((2 * r, 2 * r), dtype=bool)
        for py in range(2 * r):
            for px in range(2 * r):
                d = math.sqrt((px - r) ** 2 + (py - r) ** 2)
                if d < r * 0.6: mask_inner[py, px] = True
                elif d < r: mask_ring[py, px] = True
        if mask_ring.sum() > 0:
            avg = region[mask_ring].mean(axis=0)
            for py in range(2 * r):
                for px in range(2 * r):
                    if mask_inner[py, px]:
                        d = math.sqrt((px - r) ** 2 + (py - r) ** 2)
                        blend = d / (r * 0.6)
                        region[py, px] = region[py, px] * blend + avg * (1 - blend)
            arr[y - r:y + r, x - r:x + r] = region
            layer.image = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")

    def _draw_retouch(self, tool, x, y):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        w, h = layer.image.size
        sz = self.editor.brush_size; r = sz // 2
        exposure = self.editor.retouch_exposure / 100.0
        x0, y0 = max(0, x - r), max(0, y - r)
        x1, y1 = min(w, x + r), min(h, y + r)
        if x1 <= x0 or y1 <= y0: return
        arr = np.array(layer.image).astype(np.float64)
        region = arr[y0:y1, x0:x1]
        for py in range(region.shape[0]):
            for px in range(region.shape[1]):
                d = math.sqrt((px + x0 - x) ** 2 + (py + y0 - y) ** 2)
                if d > r: continue
                falloff = 1 - d / r; strength = exposure * falloff * 0.2
                if tool == "dodge":
                    for ch in range(3):
                        region[py, px, ch] = min(255, region[py, px, ch] + (255 - region[py, px, ch]) * strength)
                elif tool == "burn":
                    for ch in range(3):
                        region[py, px, ch] = max(0, region[py, px, ch] * (1 - strength))
                elif tool == "sponge":
                    # Saturate (increase color distance from gray) or desaturate
                    # Pressing Alt key desaturates; normal saturates
                    gray = 0.299 * region[py, px, 0] + 0.587 * region[py, px, 1] + 0.114 * region[py, px, 2]
                    saturate = True  # could tie to modifier key
                    for ch in range(3):
                        if saturate:
                            region[py, px, ch] = max(0, min(255, region[py, px, ch] + (region[py, px, ch] - gray) * strength * 1.5))
                        else:
                            region[py, px, ch] = max(0, min(255, region[py, px, ch] + (gray - region[py, px, ch]) * strength * 1.5))
                elif tool == "smudge":
                    # Smear toward drag direction
                    b = min(0.9, strength * 0.7)
                    if self.last_pos is not None:
                        ddx = int(img_pos.x() - self.last_pos.x()) if hasattr(self, '_smudge_dir') else 0
                        ddy = int(img_pos.y() - self.last_pos.y()) if hasattr(self, '_smudge_dir') else 0
                    else:
                        ddx, ddy = 0, 0
                    spx = max(0, min(region.shape[1] - 1, px - ddx))
                    spy = max(0, min(region.shape[0] - 1, py - ddy))
                    for ch in range(3):
                        region[py, px, ch] = region[py, px, ch] * (1 - b) + region[spy, spx, ch] * b
        arr[y0:y1, x0:x1] = region
        layer.image = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")

    def _commit_shape(self):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Shape")
        draw = ImageDraw.Draw(layer.image)
        s, e = self._shape_start, self.last_pos
        c = self.editor.fg_color
        stroke = (c.red(), c.green(), c.blue(), self.editor.brush_opacity)
        sw = self.editor.shape_stroke_width
        filled = self.editor.shape_filled
        fill_c = stroke if filled else None
        t = self.editor.current_tool
        sx, sy, ex, ey = int(s.x()), int(s.y()), int(e.x()), int(e.y())
        box = (min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey))
        if t == "rect":
            draw.rectangle(box, fill=fill_c, outline=stroke, width=sw)
        elif t == "ellipse":
            draw.ellipse(box, fill=fill_c, outline=stroke, width=sw)
        elif t == "line":
            draw.line([(sx, sy), (ex, ey)], fill=stroke, width=sw)
        elif t == "arrow":
            draw.line([(sx, sy), (ex, ey)], fill=stroke, width=sw)
            angle = math.atan2(ey - sy, ex - sx); hl = 12; ha = math.pi / 6
            p1 = (int(ex - hl * math.cos(angle - ha)), int(ey - hl * math.sin(angle - ha)))
            p2 = (int(ex - hl * math.cos(angle + ha)), int(ey - hl * math.sin(angle + ha)))
            draw.polygon([(ex, ey), p1, p2], fill=stroke)
        elif t == "triangle":
            pts = [((sx + ex) // 2, min(sy, ey)), (min(sx, ex), max(sy, ey)), (max(sx, ex), max(sy, ey))]
            draw.polygon(pts, fill=fill_c, outline=stroke)
        elif t == "polygon":
            sides = self.editor.polygon_sides
            cx, cy = (sx + ex) // 2, (sy + ey) // 2
            r = min(abs(ex - sx), abs(ey - sy)) // 2
            pts = [(int(cx + r * math.cos(2 * math.pi * i / sides - math.pi / 2)),
                    int(cy + r * math.sin(2 * math.pi * i / sides - math.pi / 2))) for i in range(sides)]
            draw.polygon(pts, fill=fill_c, outline=stroke)
        elif t == "star":
            points = self.editor.star_points
            cx, cy = (sx + ex) // 2, (sy + ey) // 2
            outer_r = min(abs(ex - sx), abs(ey - sy)) // 2
            inner_pct = getattr(self.editor, "star_inner_ratio", 40) / 100.0
            inner_r = max(1, int(outer_r * inner_pct))
            pts = []
            for i in range(points * 2):
                a = math.pi * i / points - math.pi / 2
                rad = outer_r if i % 2 == 0 else inner_r
                pts.append((int(cx + rad * math.cos(a)), int(cy + rad * math.sin(a))))
            draw.polygon(pts, fill=fill_c, outline=stroke)
        self.update()

    def _draw_gradient(self, start, end):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Gradient")
        w, h = layer.image.size
        arr = np.array(layer.image).astype(np.float64)
        sx, sy, ex, ey = start.x(), start.y(), end.x(), end.y()
        c1 = self.editor.fg_color; c2 = self.editor.bg_color
        from_c = np.array([c1.red(), c1.green(), c1.blue(), self.editor.brush_opacity], dtype=np.float64)
        to_c = np.array([c2.red(), c2.green(), c2.blue(), self.editor.brush_opacity], dtype=np.float64)
        grad_type = self.editor.gradient_type
        Y, X = np.mgrid[0:h, 0:w].astype(np.float64)
        if grad_type == "linear":
            dx, dy = ex - sx, ey - sy
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1: return
            t = np.clip(((X - sx) * dx + (Y - sy) * dy) / (length * length), 0, 1)
        elif grad_type == "radial":
            radius = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
            if radius < 1: return
            t = np.clip(np.sqrt((X - sx) ** 2 + (Y - sy) ** 2) / radius, 0, 1)
        elif grad_type == "angle":
            t = (np.arctan2(Y - sy, X - sx) / (2 * math.pi) + 0.5) % 1.0
        elif grad_type == "reflected":
            dx, dy = ex - sx, ey - sy
            length = math.sqrt(dx * dx + dy * dy)
            if length < 1: return
            raw = ((X - sx) * dx + (Y - sy) * dy) / (length * length)
            t = np.abs(np.clip(raw, -1, 1))
        elif grad_type == "diamond":
            # Diamond: max of abs(x-dist) and abs(y-dist) normalised
            angle = math.atan2(ey - sy, ex - sx)
            radius = math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2)
            if radius < 1: return
            dx = (X - sx) * math.cos(-angle) - (Y - sy) * math.sin(-angle)
            dy = (X - sx) * math.sin(-angle) + (Y - sy) * math.cos(-angle)
            t = np.clip((np.abs(dx) + np.abs(dy)) / radius, 0, 1)
        else:
            t = np.zeros((h, w))
        for ch in range(3):
            color_ch = from_c[ch] * (1 - t) + to_c[ch] * t
            alpha = (from_c[3] * (1 - t) + to_c[3] * t) / 255.0
            arr[:, :, ch] = arr[:, :, ch] * (1 - alpha) + color_ch * alpha
        layer.image = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        self.update()

    def _draw_pattern_fill(self, x, y):
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        w, h = layer.image.size; sz = self.editor.pattern_scale
        pat = Image.new("RGBA", (sz * 2, sz * 2), (255, 255, 255, 255))
        draw = ImageDraw.Draw(pat); c = self.editor.fg_color
        fc = (c.red(), c.green(), c.blue(), 255)
        pt = self.editor.pattern_type
        if pt == "checkerboard":
            draw.rectangle((0, 0, sz, sz), fill=fc)
            draw.rectangle((sz, sz, sz * 2, sz * 2), fill=fc)
        elif pt == "stripes":
            draw.rectangle((0, 0, sz, sz * 2), fill=fc)
        elif pt == "dots":
            draw.ellipse((sz // 4, sz // 4, 3 * sz // 4, 3 * sz // 4), fill=fc)
            draw.ellipse((sz + sz // 4, sz + sz // 4, sz + 3 * sz // 4, sz + 3 * sz // 4), fill=fc)
        elif pt == "grid":
            draw.rectangle((0, 0, 2, sz * 2), fill=fc)
            draw.rectangle((0, 0, sz * 2, 2), fill=fc)
            draw.rectangle((sz, 0, sz + 2, sz * 2), fill=fc)
            draw.rectangle((0, sz, sz * 2, sz + 2), fill=fc)
        for ty in range(0, h, sz * 2):
            for tx in range(0, w, sz * 2):
                layer.image.paste(pat, (tx, ty), pat)
        self.update()

    # ── Guides & Rotate View ─────────────────────────────────────────────────

    def _paint_guides(self, painter):
        """Paint guide lines in image-space (inside painter.save block)."""
        if not self.editor.layers: return
        iw, ih = self.editor.layers[0].image.size
        pen = QPen(QColor(80, 180, 255, 180), 0)
        pen.setCosmetic(True)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for g in self._guides:
            if g['orientation'] == 'h':
                y = g['pos']
                painter.drawLine(QPointF(0, y), QPointF(iw, y))
            else:
                x = g['pos']
                painter.drawLine(QPointF(x, 0), QPointF(x, ih))

    def _paint_guide_labels(self, painter):
        """Paint position labels in screen-space."""
        painter.save()
        painter.resetTransform()
        painter.setFont(QFont("Consolas", dp(8)))
        for g in self._guides:
            p_scr = self.image_to_canvas_f(
                g['pos'] if g['orientation'] == 'v' else 0,
                g['pos'] if g['orientation'] == 'h' else 0)
            label = f"{g['pos']}px"
            painter.setPen(QColor(80, 200, 255, 200))
            if g['orientation'] == 'h':
                painter.drawText(QPointF(4, p_scr.y() - 2), label)
            else:
                painter.drawText(QPointF(p_scr.x() + 3, 14), label)
        painter.restore()

    def add_guide(self, orientation, pos):
        """Add a guide line. orientation='h' or 'v', pos in image pixels."""
        self._guides.append({'orientation': orientation, 'pos': int(pos)})
        self.update()

    def remove_guide(self, index):
        if 0 <= index < len(self._guides):
            del self._guides[index]
            self.update()

    def clear_guides(self):
        self._guides.clear()
        self.update()

    def _snap_point(self, img_pt):
        """Snap a QPointF (image coords) to nearest guide within threshold."""
        if not self._snap_to_guides or not self._guides:
            return img_pt
        x, y = img_pt.x(), img_pt.y()
        thr = self.snap_threshold_px / max(0.01, self.zoom)
        for g in self._guides:
            if g['orientation'] == 'h':
                if abs(y - g['pos']) < thr:
                    y = float(g['pos'])
            else:
                if abs(x - g['pos']) < thr:
                    x = float(g['pos'])
        return QPointF(x, y)

    def rotate_view(self, delta_deg):
        """Rotate the canvas view (non-destructive, pixels unchanged)."""
        self.canvas_angle = (self.canvas_angle + delta_deg) % 360
        self.update()

    def reset_view_rotation(self):
        self.canvas_angle = 0.0
        self.update()

    # ── Quick Mask ────────────────────────────────────────────────────────────

    def _paint_quick_mask(self, painter):
        """Red overlay on the quick-mask canvas (masked = red)."""
        if self._quick_mask_layer is None: return
        painter.save()
        painter.resetTransform()
        inv = ImageChops.invert(self._quick_mask_layer)
        overlay = Image.new("RGBA", self._quick_mask_layer.size, (200, 40, 40, 0))
        overlay.putalpha(inv.point(lambda v: int(v * 0.5)))
        qpx = pil_to_qpixmap(overlay)
        iw, ih = self._quick_mask_layer.size
        target = QRectF(self.pan_offset.x(), self.pan_offset.y(),
                        iw * self.zoom, ih * self.zoom)
        painter.drawPixmap(target, qpx, QRectF(qpx.rect()))
        # Label
        painter.setPen(QColor(255, 80, 80, 220))
        painter.setFont(QFont("Consolas", dp(9)))
        painter.drawText(QPointF(target.x() + 6, target.y() + dp(14)), "QUICK MASK")
        painter.restore()

    def quick_mask_enter(self):
        """Enter Quick Mask mode — current selection → red overlay to paint."""
        layer = self.editor.active_layer()
        if not layer: return
        iw, ih = layer.image.size
        self._quick_mask_prev = self.selection_mask.copy() if self.selection_mask else None
        if self.selection_mask is not None:
            self._quick_mask_layer = self.selection_mask.copy()
        else:
            self._quick_mask_layer = Image.new("L", (iw, ih), 255)
        self.editor.quick_mask_active = True
        self.set_selection_mask(None)
        self.update()
        self.editor._status("Quick Mask — paint black to mask, white to unmask; press Q to exit")

    def quick_mask_exit(self):
        """Exit Quick Mask — paint result becomes selection."""
        if not self.editor.quick_mask_active: return
        if self._quick_mask_layer is not None:
            self.set_selection_mask(self._quick_mask_layer.copy())
        self._quick_mask_layer = None
        self._quick_mask_prev = None
        self.editor.quick_mask_active = False
        self.update()
        self.editor._status("Quick Mask exited — selection updated")

    def _paint_quick_mask_stroke(self, x, y):
        """Paint on quick mask layer (white=selected, black=masked)."""
        if self._quick_mask_layer is None: return
        sz  = self.editor.brush_size
        col = 255 if self.editor.fg_color.lightness() > 127 else 0
        draw = ImageDraw.Draw(self._quick_mask_layer)
        r = sz // 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=col)

    def _paint_quick_mask_line(self, p1, p2):
        if self._quick_mask_layer is None: return
        x1, y1 = int(p1.x()), int(p1.y())
        x2, y2 = int(p2.x()), int(p2.y())
        sz = self.editor.brush_size
        dist = max(1, int(math.hypot(x2 - x1, y2 - y1)))
        step = max(1, sz // 3)
        for i in range(0, dist + 1, step):
            t = i / dist
            self._paint_quick_mask_stroke(int(x1 + (x2-x1)*t), int(y1 + (y2-y1)*t))

    # ── Magnetic Scissors ─────────────────────────────────────────────────────

    def _paint_mag_scissors(self, painter):
        """Draw anchor points and live edge path for magnetic lasso."""
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Draw path between anchors
        wpts = [self.image_to_canvas(a) for a in self._mag_anchors]
        if self._mag_preview:
            wpts_full = wpts + [self.image_to_canvas(self._mag_preview)]
        else:
            wpts_full = wpts
        if len(wpts_full) > 1:
            pen = QPen(QColor(255, 255, 255, 200), 1.5)
            pen.setDashPattern([5, 3])
            painter.setPen(pen)
            for i in range(len(wpts_full) - 1):
                painter.drawLine(wpts_full[i], wpts_full[i + 1])
        # Draw anchors
        for pt in wpts:
            painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
            painter.setPen(QPen(QColor(80, 160, 255), 1.5))
            painter.drawRect(QRectF(pt.x() - dp(4), pt.y() - dp(4), dp(8), dp(8)))
        painter.restore()

    def _mag_compute_edge_map(self):
        """Compute Sobel edge-strength map for current composite."""
        layer = self.editor.active_layer()
        if not layer: return
        import scipy.ndimage as ndi
        arr = np.array(self.editor.get_composite().convert("L"), dtype=np.float32)
        sx = ndi.sobel(arr, axis=1)
        sy = ndi.sobel(arr, axis=0)
        strength = np.hypot(sx, sy)
        # Normalize 0-1
        mx = strength.max()
        if mx > 0: strength /= mx
        self._mag_edge_map = strength

    def _mag_snap_to_edge(self, img_pos, search_radius=12):
        """Snap cursor position to nearest strong edge within radius."""
        if self._mag_edge_map is None:
            self._mag_compute_edge_map()
        x, y = int(img_pos.x()), int(img_pos.y())
        h, w = self._mag_edge_map.shape
        x0 = max(0, x - search_radius); x1 = min(w, x + search_radius)
        y0 = max(0, y - search_radius); y1 = min(h, y + search_radius)
        region = self._mag_edge_map[y0:y1, x0:x1]
        if region.size == 0: return img_pos
        flat_idx = np.argmax(region)
        ry, rx = divmod(flat_idx, region.shape[1])
        # Only snap if edge is strong enough
        sens = self.editor.mag_edge_sensitivity / 100.0
        if region[ry, rx] >= 0.2 * sens:
            return QPointF(x0 + rx, y0 + ry)
        return img_pos

    def mag_scissors_finalize(self):
        """Close the magnetic lasso and create a selection from anchor path."""
        if len(self._mag_anchors) < 3: return
        layer = self.editor.active_layer()
        if not layer: return
        iw, ih = layer.image.size
        mask = Image.new("L", (iw, ih), 0)
        draw = ImageDraw.Draw(mask)
        pts = [(int(p.x()), int(p.y())) for p in self._mag_anchors]
        draw.polygon(pts, fill=255)
        new_mask = self._apply_feather(mask)
        self._apply_selection_mode(new_mask)
        self._mag_anchors = []
        self._mag_preview = None
        self._mag_edge_map = None
        self.update()

    # ── Selection mode / feather helpers ─────────────────────────────────────

    def _apply_feather(self, mask):
        """Apply feather radius to a selection mask."""
        feather = getattr(self.editor, 'sel_feather', 0)
        if feather > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(feather))
        return mask

    def _apply_selection_mode(self, new_mask):
        """Combine new_mask with existing selection per editor.sel_mode."""
        mode = getattr(self.editor, 'sel_mode', 'new')
        if mode == 'new' or self.selection_mask is None:
            self.set_selection_mask(new_mask)
        elif mode == 'add':
            self.set_selection_mask(ImageChops.lighter(self.selection_mask, new_mask))
        elif mode == 'subtract':
            inverted = ImageChops.invert(new_mask)
            self.set_selection_mask(ImageChops.darker(self.selection_mask, inverted))
        elif mode == 'intersect':
            self.set_selection_mask(ImageChops.multiply(self.selection_mask, new_mask))
        self.selection_rect = None

    # ── Layer mask painting ───────────────────────────────────────────────────

    def _paint_rubylith(self, painter, layer):
        """Draw a semi-transparent red overlay on masked-out areas."""
        painter.save()
        painter.resetTransform()
        # Invert mask: masked-out (0) → red overlay
        inv_mask = ImageChops.invert(layer.mask)
        # Convert mask to RGBA red overlay
        overlay = Image.new("RGBA", layer.mask.size, (200, 0, 0, 0))
        overlay.putalpha(inv_mask.point(lambda v: int(v * 0.55)))  # 55% max opacity
        qpx = pil_to_qpixmap(overlay)
        # Draw at canvas position/scale
        iw, ih = layer.mask.size
        target = QRectF(self.pan_offset.x(), self.pan_offset.y(),
                        iw * self.zoom, ih * self.zoom)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(target, qpx, QRectF(qpx.rect()))
        # Border indicator: bright magenta dashed frame
        pen = QPen(QColor(255, 0, 200, 200), 2.0)
        pen.setDashPattern([8, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(target.adjusted(1, 1, -1, -1))
        painter.restore()

    def _draw_brush_on_mask(self, x, y):
        """Paint white (reveal) or black (hide) on the layer mask."""
        layer = self.editor.active_layer()
        if not layer or layer.mask is None: return
        sz  = self.editor.brush_size
        col = 255 if self.editor.fg_color.lightness() > 127 else 0
        draw = ImageDraw.Draw(layer.mask)
        hardness = getattr(self.editor, "brush_hardness", 100)
        if hardness < 100:
            stamp_sz = max(2, sz)
            center_val = col
            edge_val   = 255 - col  # inverted at edge for soft falloff
            stamp = Image.new("L", (stamp_sz * 2, stamp_sz * 2), edge_val)
            for iy in range(stamp_sz * 2):
                for ix2 in range(stamp_sz * 2):
                    dx, dy = ix2 - stamp_sz, iy - stamp_sz
                    d = math.sqrt(dx * dx + dy * dy) / stamp_sz
                    if d <= 1.0:
                        fac = 1.0 - d ** (hardness / 50.0 + 0.1)
                        v = int(edge_val + (center_val - edge_val) * fac)
                        stamp.putpixel((ix2, iy), max(0, min(255, v)))
            # Blend stamp onto mask
            x0, y0 = x - stamp_sz, y - stamp_sz
            region = layer.mask.crop((x0, y0, x0 + stamp_sz * 2, y0 + stamp_sz * 2))
            if col == 255:
                merged = ImageChops.lighter(region, stamp)
            else:
                merged = ImageChops.darker(region, ImageChops.invert(stamp))
                merged = ImageChops.invert(merged)
            layer.mask.paste(merged, (x0, y0))
        else:
            r = sz // 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=col)

    def _draw_brush_line_on_mask(self, p1, p2):
        """Continuous stroke on mask."""
        layer = self.editor.active_layer()
        if not layer or layer.mask is None: return
        x1, y1 = int(p1.x()), int(p1.y())
        x2, y2 = int(p2.x()), int(p2.y())
        sz = self.editor.brush_size
        dist = max(1, int(math.hypot(x2 - x1, y2 - y1)))
        step = max(1, sz // 3)
        for i in range(0, dist + 1, step):
            t = i / dist
            self._draw_brush_on_mask(int(x1 + (x2 - x1) * t), int(y1 + (y2 - y1) * t))

    # ── Free Transform helpers ────────────────────────────────────────────────

    def _xform_handles_wp(self):
        """Return dict of handle_name → QPointF in WIDGET coords."""
        cx, cy = self._xform_cx, self._xform_cy
        w, h   = self._xform_w,  self._xform_h
        a      = self._xform_angle
        cos_a, sin_a = math.cos(a), math.sin(a)
        def rot(dx, dy):
            return (dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a)
        corners = {
            'tl': rot(-w, -h), 'tc': rot(0, -h), 'tr': rot(w, -h),
            'ml': rot(-w, 0),                     'mr': rot(w, 0),
            'bl': rot(-w, h),  'bc': rot(0, h),   'br': rot(w, h),
            'rot': rot(0, -h - 24 / self.zoom),
        }
        result = {}
        for name, (dx, dy) in corners.items():
            result[name] = self.image_to_canvas_f(cx + dx, cy + dy)
        return result

    def _xform_hit_test(self, wp):
        """Return handle name or 'body' or None."""
        handles = self._xform_handles_wp()
        RADIUS = dp(7)
        for name, pt in handles.items():
            if (wp - pt).manhattanLength() < RADIUS:
                return name
        # Check if inside the bounding box (rough test using widget coords)
        # Build polygon from corner handles
        pts = [handles['tl'], handles['tr'], handles['br'], handles['bl']]
        poly = QPolygonF(pts)
        if poly.containsPoint(wp, Qt.OddEvenFill):
            return 'body'
        return None

    def _paint_xform_overlay(self, painter):
        """Draw the free-transform bounding box and handles."""
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing, True)
        handles = self._xform_handles_wp()
        # Dashed bounding box
        box_pts = [handles['tl'], handles['tr'], handles['br'], handles['bl']]
        pen = QPen(QColor(255, 255, 255, 220), 1.5)
        pen.setDashPattern([6, 4])
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygonF(box_pts))
        # Rotate handle line
        painter.setPen(QPen(QColor(255, 255, 255, 180), 1.0))
        painter.drawLine(handles['tc'], handles['rot'])
        # Handle squares
        SZ = dp(7)
        for name, pt in handles.items():
            if name == 'rot':
                # Circle for rotate
                painter.setPen(QPen(QColor(80, 160, 255), 1.5))
                painter.setBrush(QBrush(QColor(255, 255, 255, 200)))
                painter.drawEllipse(pt, SZ / 2 + 1, SZ / 2 + 1)
            else:
                painter.setPen(QPen(QColor(80, 160, 255), 1.5))
                painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
                painter.drawRect(QRectF(pt.x() - SZ/2, pt.y() - SZ/2, SZ, SZ))
        # Center crosshair
        cp = self.image_to_canvas_f(self._xform_cx, self._xform_cy)
        ch = dp(5)
        painter.setPen(QPen(QColor(255, 255, 255, 160), 1.0))
        painter.drawLine(QPointF(cp.x() - ch, cp.y()), QPointF(cp.x() + ch, cp.y()))
        painter.drawLine(QPointF(cp.x(), cp.y() - ch), QPointF(cp.x(), cp.y() + ch))
        painter.restore()

    def _paint_persp_overlay(self, painter):
        """Draw perspective transform corner handles."""
        if len(self._persp_corners) < 4: return
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.Antialiasing, True)
        wpts = [self.image_to_canvas(p) for p in self._persp_corners]
        pen = QPen(QColor(255, 200, 50, 220), 1.5)
        pen.setDashPattern([6, 3])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(QPolygonF(wpts + [wpts[0]]))
        SZ = dp(8)
        for i, pt in enumerate(wpts):
            if i == self._persp_drag_i:
                painter.setBrush(QBrush(QColor(255, 200, 50, 255)))
            else:
                painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            painter.setPen(QPen(QColor(255, 200, 50), 1.5))
            painter.drawEllipse(pt, SZ / 2, SZ / 2)
        painter.restore()

    def xform_enter(self):
        """Enter Free Transform mode for the active layer."""
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        self._xform_orig   = layer.image.copy()
        iw, ih             = layer.image.size
        self._xform_cx     = iw / 2.0
        self._xform_cy     = ih / 2.0
        self._xform_w      = iw / 2.0
        self._xform_h      = ih / 2.0
        self._xform_angle  = 0.0
        self._xform_flip_h = False
        self._xform_flip_v = False
        self._xform_handle = None
        self._xform_active = True
        self.update()

    def xform_commit(self):
        """Apply the current transform to the layer and exit transform mode."""
        if not self._xform_active: return
        layer = self.editor.active_layer()
        if layer and self._xform_orig:
            self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Transform")
            layer.image = self._xform_render_final()
        self._xform_active = False
        self._xform_orig   = None
        self.update()

    def xform_cancel(self):
        """Cancel transform, restore original layer."""
        if not self._xform_active: return
        layer = self.editor.active_layer()
        if layer and self._xform_orig:
            layer.image = self._xform_orig.copy()
        self._xform_active = False
        self._xform_orig   = None
        self.update()

    def xform_flip_h(self):
        self._xform_flip_h = not self._xform_flip_h
        self._xform_apply_preview(); self.update()

    def xform_flip_v(self):
        self._xform_flip_v = not self._xform_flip_v
        self._xform_apply_preview(); self.update()

    def _xform_render_final(self):
        """Return a new PIL Image with the full transform applied."""
        src = self._xform_orig
        iw, ih = src.size
        if self._xform_flip_h: src = src.transpose(Image.FLIP_LEFT_RIGHT)
        if self._xform_flip_v: src = src.transpose(Image.FLIP_TOP_BOTTOM)
        # Scale
        new_w = max(1, int(self._xform_w * 2))
        new_h = max(1, int(self._xform_h * 2))
        if (new_w, new_h) != (iw, ih):
            src = src.resize((new_w, new_h), Image.LANCZOS)
        # Rotate
        if abs(self._xform_angle) > 0.001:
            deg = math.degrees(self._xform_angle)
            src = src.rotate(-deg, expand=True, resample=Image.BICUBIC)
        # Place on canvas at correct position
        canvas = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        paste_x = int(self._xform_cx - src.width / 2)
        paste_y = int(self._xform_cy - src.height / 2)
        canvas.paste(src, (paste_x, paste_y), src)
        return canvas

    def _xform_apply_preview(self):
        """Quick preview render into the layer (non-committed)."""
        layer = self.editor.active_layer()
        if not layer or not self._xform_orig: return
        layer.image = self._xform_render_final()
        self.update()

    def persp_enter(self):
        """Enter Perspective Transform mode."""
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        self._persp_orig = layer.image.copy()
        iw, ih = layer.image.size
        self._persp_corners = [
            QPointF(0, 0), QPointF(iw, 0),
            QPointF(iw, ih), QPointF(0, ih),
        ]
        self._persp_drag_i = -1
        self._persp_active = True
        self.update()

    def persp_commit(self):
        """Apply perspective transform."""
        if not self._persp_active: return
        layer = self.editor.active_layer()
        if layer and self._persp_orig:
            self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Perspective")
            layer.image = self._persp_render_final()
        self._persp_active = False
        self._persp_orig   = None
        self.update()

    def persp_cancel(self):
        if not self._persp_active: return
        layer = self.editor.active_layer()
        if layer and self._persp_orig:
            layer.image = self._persp_orig.copy()
        self._persp_active = False
        self._persp_orig   = None
        self.update()

    def _persp_render_final(self):
        """Apply PIL perspective transform from 4-corner mapping."""
        src = self._persp_orig
        iw, ih = src.size
        # Source corners (original)
        src_pts = [(0, 0), (iw, 0), (iw, ih), (0, ih)]
        # Destination corners (user-dragged)
        dst_pts = [(p.x(), p.y()) for p in self._persp_corners]
        # Compute perspective coefficients
        coeffs = self._find_perspective_coeffs(src_pts, dst_pts)
        # Apply PERSPECTIVE transform (dst→src mapping)
        coeffs_inv = self._find_perspective_coeffs(dst_pts, src_pts)
        result = src.transform((iw, ih), Image.PERSPECTIVE, coeffs_inv, Image.BICUBIC)
        return result

    @staticmethod
    def _find_perspective_coeffs(pa, pb):
        """Compute 8 perspective transform coefficients (src→dst)."""
        matrix = []
        for p1, p2 in zip(pa, pb):
            matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
            matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])
        A = np.matrix(matrix, dtype=float)
        B = np.array(pb, dtype=float).reshape(8)
        try:
            res = np.linalg.solve(A, B)
        except np.linalg.LinAlgError:
            res = np.zeros(8)
        return np.array(res).flatten().tolist()

    def _xform_drag(self, wp):
        """Handle free transform handle drag."""
        if self._xform_start is None or self._xform_drag_wp is None: return
        cx0, cy0, w0, h0, a0 = self._xform_start
        handle = self._xform_handle
        delta_w = QPointF(wp - self._xform_drag_wp)

        if handle == 'body':
            # Translate in image coords
            di = self.canvas_to_image(wp) - self.canvas_to_image(self._xform_drag_wp)
            self._xform_cx = cx0 + di.x()
            self._xform_cy = cy0 + di.y()
        elif handle == 'rot':
            # Rotate: angle between center→drag_start and center→current
            cw = self.image_to_canvas_f(cx0, cy0)
            a_start = math.atan2(self._xform_drag_wp.y() - cw.y(),
                                 self._xform_drag_wp.x() - cw.x())
            a_now   = math.atan2(wp.y() - cw.y(), wp.x() - cw.x())
            self._xform_angle = a0 + (a_now - a_start)
        else:
            # Scale: compute how far from center in image-space along rotated axis
            cos_a, sin_a = math.cos(-a0), math.sin(-a0)
            # Rotate delta into object space
            dx_rot =  delta_w.x() * cos_a - delta_w.y() * sin_a
            dy_rot =  delta_w.x() * sin_a + delta_w.y() * cos_a
            # Convert to image-space pixels
            dx_img = dx_rot / self.zoom
            dy_img = dy_rot / self.zoom

            if 'r' in handle:   self._xform_w = max(4, w0 + dx_img)
            if 'l' in handle:   self._xform_w = max(4, w0 - dx_img)
            if 'b' in handle:   self._xform_h = max(4, h0 + dy_img)
            if 't' in handle:   self._xform_h = max(4, h0 - dy_img)

        self._xform_apply_preview()

    def _apply_warp(self, layer, cx, cy, ddx, ddy):
        """Warp transform: displace pixels around brush area."""
        sz   = max(6, self.editor.brush_size)
        mode = getattr(self.editor, "warp_mode", "move")
        arr  = np.array(layer.image, dtype=np.float32)
        h, w = arr.shape[:2]
        # Build coordinate grid
        ys = np.arange(h, dtype=np.float32)
        xs = np.arange(w, dtype=np.float32)
        xg, yg = np.meshgrid(xs, ys)
        dist2 = (xg - cx) ** 2 + (yg - cy) ** 2
        rad2  = float(sz * sz)
        inside = dist2 < rad2
        falloff = np.where(inside, 1.0 - dist2 / rad2, 0.0)  # smooth falloff

        if mode == "move" and (ddx != 0 or ddy != 0):
            strength = getattr(self.editor, "warp_strength", 60) / 100.0
            sx = np.clip(xg - ddx * falloff * strength, 0, w - 1).astype(np.float32)
            sy = np.clip(yg - ddy * falloff * strength, 0, h - 1).astype(np.float32)
            from scipy.ndimage import map_coordinates
            result = np.zeros_like(arr)
            for c in range(arr.shape[2]):
                result[:, :, c] = map_coordinates(arr[:, :, c], [sy, sx], order=1, mode='nearest')
            layer.image = Image.fromarray(result.clip(0, 255).astype(np.uint8), "RGBA")
        elif mode == "grow":
            # Expand pixels outward from center
            strength = getattr(self.editor, "warp_strength", 60) / 200.0
            dx_field = (xg - cx) * falloff * strength
            dy_field = (yg - cy) * falloff * strength
            sx = np.clip(xg - dx_field, 0, w - 1).astype(np.float32)
            sy = np.clip(yg - dy_field, 0, h - 1).astype(np.float32)
            from scipy.ndimage import map_coordinates
            result = np.zeros_like(arr)
            for c in range(arr.shape[2]):
                result[:, :, c] = map_coordinates(arr[:, :, c], [sy, sx], order=1, mode='nearest')
            layer.image = Image.fromarray(result.clip(0, 255).astype(np.uint8), "RGBA")
        elif mode == "shrink":
            strength = getattr(self.editor, "warp_strength", 60) / 200.0
            dx_field = -(xg - cx) * falloff * strength
            dy_field = -(yg - cy) * falloff * strength
            sx = np.clip(xg - dx_field, 0, w - 1).astype(np.float32)
            sy = np.clip(yg - dy_field, 0, h - 1).astype(np.float32)
            from scipy.ndimage import map_coordinates
            result = np.zeros_like(arr)
            for c in range(arr.shape[2]):
                result[:, :, c] = map_coordinates(arr[:, :, c], [sy, sx], order=1, mode='nearest')
            layer.image = Image.fromarray(result.clip(0, 255).astype(np.uint8), "RGBA")
        elif mode == "swirl":
            strength = getattr(self.editor, "warp_strength", 60) / 100.0 * 0.05
            angle = falloff * strength
            cos_a = np.cos(angle); sin_a = np.sin(angle)
            rx = xg - cx; ry = yg - cy
            sx = np.clip(cx + rx * cos_a - ry * sin_a, 0, w - 1).astype(np.float32)
            sy = np.clip(cy + rx * sin_a + ry * cos_a, 0, h - 1).astype(np.float32)
            from scipy.ndimage import map_coordinates
            result = np.zeros_like(arr)
            for c in range(arr.shape[2]):
                result[:, :, c] = map_coordinates(arr[:, :, c], [sy, sx], order=1, mode='nearest')
            layer.image = Image.fromarray(result.clip(0, 255).astype(np.uint8), "RGBA")
        self.update()

    def _apply_blur_sharpen(self, layer, cx, cy):
        """Blur or sharpen pixels within brush radius."""
        sz     = max(4, self.editor.brush_size)
        mode   = getattr(self.editor, "blur_sharpen_mode", "blur")
        strength = getattr(self.editor, "blur_sharpen_strength", 50) / 100.0
        radius = max(1, int(sz * 0.4))
        x0, y0 = max(0, cx - sz), max(0, cy - sz)
        x1, y1 = min(layer.image.width, cx + sz), min(layer.image.height, cy + sz)
        if x1 <= x0 or y1 <= y0: return
        region = layer.image.crop((x0, y0, x1, y1))
        if mode == "blur":
            filtered = region.filter(ImageFilter.GaussianBlur(radius))
        else:
            # Sharpen: blend unsharp mask result
            blurred  = region.filter(ImageFilter.GaussianBlur(1))
            arr_orig = np.array(region, dtype=np.float32)
            arr_blur = np.array(blurred, dtype=np.float32)
            arr_sharp = np.clip(arr_orig + (arr_orig - arr_blur) * strength * 3, 0, 255).astype(np.uint8)
            filtered = Image.fromarray(arr_sharp, "RGBA")
        # Feather blend: apply circular mask so edges are smooth
        rw, rh = x1 - x0, y1 - y0
        fmask = Image.new("L", (rw, rh), 0)
        fdraw = ImageDraw.Draw(fmask)
        fdraw.ellipse((0, 0, rw - 1, rh - 1), fill=int(180 * strength))
        fmask = fmask.filter(ImageFilter.GaussianBlur(sz // 3))
        blended = Image.composite(filtered, region, fmask)
        layer.image.paste(blended, (x0, y0))
        self.update()

    # ── Red Eye Removal ──────────────────────────────────────────────────────

    def _apply_red_eye(self, cx, cy):
        """Desaturate red pixels in a brush-sized circle around (cx, cy)."""
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        sz = max(4, self.editor.brush_size)
        x0 = max(0, cx - sz); y0 = max(0, cy - sz)
        x1 = min(layer.image.width, cx + sz)
        y1 = min(layer.image.height, cy + sz)
        if x1 <= x0 or y1 <= y0: return
        crop = layer.image.crop((x0, y0, x1, y1))
        arr = np.array(crop, dtype=np.float32)
        r, g, b, a = arr[:,:,0], arr[:,:,1], arr[:,:,2], arr[:,:,3]
        # "Red eye" condition: red channel dominant and overall bright
        red_dominant = (r > 100) & (r > 1.4 * g) & (r > 1.4 * b)
        # Replace red channel with average of g,b
        new_r = (g + b) / 2.0
        arr[:,:,0] = np.where(red_dominant, new_r, r)
        # Also darken overall to natural pupil colour
        gray = 0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]
        factor = np.where(red_dominant, 0.25, 1.0)  # darken the red-eye region
        for ch in range(3):
            arr[:,:,ch] = np.where(red_dominant, arr[:,:,ch] * factor, arr[:,:,ch])
        fixed = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        layer.image.paste(fixed, (x0, y0))
        self.update()

    # ── Content-Aware Fill ────────────────────────────────────────────────────

    def _content_aware_fill(self):
        """Simplified patch-based infill: fill selection region using nearest-
        neighbour patches from the surrounding area."""
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        if self.selection_mask is None:
            self.editor._status("No selection — draw a selection first")
            return
        self.editor.history.save_state(
            self.editor.layers, self.editor.active_layer_index, "Content-Aware Fill")
        img = np.array(layer.image, dtype=np.uint8)
        mask = np.array(self.selection_mask, dtype=np.uint8)
        h, w = img.shape[:2]
        patch_sz = max(8, self.editor.brush_size // 2)
        ys, xs = np.where(mask > 127)
        if len(ys) == 0: return
        # Build list of valid source patches (outside mask with enough margin)
        margin = patch_sz // 2
        valid_src = []
        step = max(1, patch_sz // 3)
        for sy in range(margin, h - margin, step):
            for sx in range(margin, w - margin, step):
                # Check that the entire patch is outside the mask
                patch_mask = mask[sy-margin:sy+margin+1, sx-margin:sx+margin+1]
                if patch_mask.max() == 0:
                    valid_src.append((sy, sx))
        if not valid_src:
            # Fallback: sample average color from border of selection
            border_ys, border_xs = np.where((mask == 0))
            if len(border_ys) > 0:
                sample = img[border_ys, border_xs, :3].mean(axis=0).astype(np.uint8)
                for y, x in zip(ys, xs):
                    img[y, x, :3] = sample
            layer.image = Image.fromarray(img, "RGBA")
            self.update(); return
        # For each hole pixel, find best-matching source patch and copy center
        rng = np.random.default_rng(42)
        for y, x in zip(ys, xs):
            # Sample a few candidates and pick the closest by color
            candidates = [valid_src[i] for i in rng.integers(0, len(valid_src), size=min(20, len(valid_src)))]
            best_diff = float('inf')
            best_src = candidates[0]
            for sy, sx in candidates:
                src_patch = img[sy-1:sy+2, sx-1:sx+2, :3].astype(np.float32)
                tgt_patch = img[y-1:y+2, x-1:x+2, :3].astype(np.float32) if (
                    y > 0 and y < h-1 and x > 0 and x < w-1) else src_patch
                diff = float(np.mean(np.abs(src_patch - tgt_patch)))
                if diff < best_diff:
                    best_diff = diff; best_src = (sy, sx)
            img[y, x, :3] = img[best_src[0], best_src[1], :3]
        layer.image = Image.fromarray(img, "RGBA")
        self.set_selection_mask(None)
        self.update()
        self.editor._status("Content-Aware Fill applied")

    # ── Off-canvas painting expansion ─────────────────────────────────────────

    def _expand_canvas_for_stroke(self, ix, iy):
        """If brush strokes go beyond canvas edge, expand the canvas to fit."""
        layer = self.editor.active_layer()
        if not layer: return ix, iy
        iw, ih = layer.image.size
        sz = self.editor.brush_size
        margin = sz // 2 + 2
        # Compute new bounds
        new_x0 = min(0, ix - margin)
        new_y0 = min(0, iy - margin)
        new_x1 = max(iw, ix + margin)
        new_y1 = max(ih, iy + margin)
        if new_x0 < 0 or new_y0 < 0 or new_x1 > iw or new_y1 > ih:
            new_w = new_x1 - new_x0
            new_h = new_y1 - new_y0
            ox, oy = -new_x0, -new_y0  # offset for existing content
            for i, lyr in enumerate(self.editor.layers):
                expanded = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
                expanded.paste(lyr.image, (ox, oy))
                lyr.image = expanded
                if lyr.mask is not None:
                    exp_mask = Image.new("L", (new_w, new_h), 255)
                    exp_mask.paste(lyr.mask, (ox, oy))
                    lyr.mask = exp_mask
            # Adjust pan offset to keep visible content in same position
            self.pan_offset = QPointF(
                self.pan_offset.x() - ox * self.zoom,
                self.pan_offset.y() - oy * self.zoom)
            ix += ox; iy += oy
        return ix, iy

    def _select_by_color(self, x, y):
        """Global select-by-color (all matching pixels, not just contiguous)."""
        layer = self.editor.active_layer()
        if not layer: return
        w, h = layer.image.size
        if x < 0 or x >= w or y < 0 or y >= h: return
        source = self.editor.get_composite() if self.editor.magic_wand_sample_all else layer.image
        src_np = np.array(source).astype(np.int16)
        target = src_np[y, x, :3]
        tol = self.editor.magic_wand_tolerance
        diff = np.abs(src_np[:, :, :3] - target.reshape(1, 1, 3))
        match = np.all(diff <= tol, axis=2)
        mask_arr = np.where(match, 255, 0).astype(np.uint8)
        new_mask = Image.fromarray(mask_arr, "L")
        new_mask = self._apply_feather(new_mask)
        self._apply_selection_mode(new_mask)
        px_count = int(np.count_nonzero(mask_arr))
        self.status_update.emit(f"Select by Color: {px_count} px selected (tol={tol})")

    def clear_selection(self):
        self.selection_mask = None
        self.marching_ants_path = None
        self.selection_rect = None
        self.update()

# ── RulerWidget ───────────────────────────────────────────────────────────────
class RulerWidget(QWidget):
    """Photoshop-style ruler along top or left edge."""
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(parent)
        self.orientation = orientation
        self._zoom = 1.0
        self._offset = 0.0
        self._mouse_pos = -1
        sz = dp(18)
        if orientation == Qt.Horizontal:
            self.setFixedHeight(sz)
        else:
            self.setFixedWidth(sz)
        self.setStyleSheet(f"background:{C.BG0};")

    def update_view(self, zoom, pan_x, pan_y):
        self._zoom = zoom
        self._offset = pan_x if self.orientation == Qt.Horizontal else pan_y
        self.update()

    def set_mouse_pos(self, x):
        self._mouse_pos = x
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG0))
        p.setPen(QColor(C.BORDER))
        if self.orientation == Qt.Horizontal:
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        else:
            p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        p.setPen(QColor(C.TEXT_MUT))
        p.setFont(QFont("Consolas", 8))

        # Draw tick marks
        zoom = max(0.05, self._zoom)
        if zoom >= 4: step_px = 10
        elif zoom >= 1: step_px = 50
        elif zoom >= 0.5: step_px = 100
        else: step_px = 200

        span = self.width() if self.orientation == Qt.Horizontal else self.height()
        offset = self._offset
        start_img = int(-offset / zoom) - step_px
        end_img = int((span - offset) / zoom) + step_px

        for img_coord in range(start_img - (start_img % step_px), end_img + step_px, step_px):
            sc = int(img_coord * zoom + offset)
            if self.orientation == Qt.Horizontal:
                if 0 <= sc < self.width():
                    p.drawLine(sc, self.height() - 6, sc, self.height() - 1)
                    if img_coord % (step_px * 2) == 0 or zoom >= 2:
                        p.drawText(sc + 2, self.height() - 7, str(img_coord))
            else:
                if 0 <= sc < self.height():
                    p.drawLine(self.width() - 6, sc, self.width() - 1, sc)
                    if img_coord % (step_px * 2) == 0 or zoom >= 2:
                        p.save()
                        p.translate(self.width() - 8, sc + 2)
                        p.rotate(-90)
                        p.drawText(0, 0, str(img_coord))
                        p.restore()

        # Mouse crosshair
        if self._mouse_pos >= 0:
            p.setPen(QColor(C.ACCENT))
            if self.orientation == Qt.Horizontal:
                p.drawLine(self._mouse_pos, 0, self._mouse_pos, self.height())
            else:
                p.drawLine(0, self._mouse_pos, self.width(), self._mouse_pos)
        p.end()


# ── NavigatorPanel ────────────────────────────────────────────────────────────
class NavigatorPanel(QWidget):
    """Mini thumbnail with viewport rectangle indicator."""
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setMinimumHeight(dp(120))
        self.setMaximumHeight(dp(160))
        self._thumb = None
        self._zoom = 1.0
        self._pan_offset = QPointF()

    def update_view(self, zoom, pan_x, pan_y):
        self._zoom = zoom
        self._pan_offset = QPointF(pan_x, pan_y)
        self.update()

    def refresh_thumb(self):
        """Regenerate thumbnail from composite."""
        try:
            comp = self.editor.get_composite()
            if comp:
                thumb = comp.copy()
                thumb.thumbnail((self.width() - 8, self.height() - 8), Image.LANCZOS)
                self._thumb = pil_to_qpixmap(thumb)
                self.update()
        except Exception:
            pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG0))
        if self._thumb and not self._thumb.isNull():
            tw, th = self._thumb.width(), self._thumb.height()
            ox = (self.width() - tw) // 2
            oy = (self.height() - th) // 2
            p.drawPixmap(ox, oy, self._thumb)

            # Draw viewport rect
            if self.editor.layers:
                iw, ih = self.editor.layers[0].image.size
                if iw > 0 and ih > 0:
                    sx = tw / iw; sy = th / ih
                    canvas = self.editor.canvas
                    vw, vh = canvas.width(), canvas.height()
                    # Canvas corners in image space
                    tl = canvas.canvas_to_image(QPointF(0, 0))
                    br = canvas.canvas_to_image(QPointF(vw, vh))
                    rx = ox + tl.x() * sx
                    ry = oy + tl.y() * sy
                    rw = (br.x() - tl.x()) * sx
                    rh = (br.y() - tl.y()) * sy
                    p.setPen(QPen(QColor(C.ACCENT), 1.5))
                    p.setBrush(QColor(C.ACCENT_D[0:7] + "44" if len(C.ACCENT_D) == 7 else C.ACCENT_D))
                    p.drawRect(QRectF(rx, ry, rw, rh))
        else:
            p.setPen(QColor(C.TEXT_MUT))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(self.rect(), Qt.AlignCenter, "No image")
        p.end()


# ── HistogramWidget ───────────────────────────────────────────────────────────
class HistogramWidget(QWidget):
    """Live RGB/luminance histogram display."""
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setFixedHeight(dp(90))
        self._hists = None
        self._channel = "rgb"  # "rgb", "r", "g", "b", "lum"

    def set_channel(self, ch):
        self._channel = ch
        self.update()

    def refresh(self):
        try:
            comp = self.editor.get_composite()
            if not comp:
                self._hists = None; self.update(); return
            arr = np.array(comp.convert("RGB"))
            self._hists = {
                "r": np.histogram(arr[:, :, 0].ravel(), bins=256, range=(0, 256))[0].astype(np.float32),
                "g": np.histogram(arr[:, :, 1].ravel(), bins=256, range=(0, 256))[0].astype(np.float32),
                "b": np.histogram(arr[:, :, 2].ravel(), bins=256, range=(0, 256))[0].astype(np.float32),
            }
            lum = (arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114).astype(np.uint8)
            self._hists["lum"] = np.histogram(lum.ravel(), bins=256, range=(0, 256))[0].astype(np.float32)
            self.update()
        except Exception:
            pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C.BG0))
        if not self._hists:
            p.setPen(QColor(C.TEXT_MUT))
            p.drawText(self.rect(), Qt.AlignCenter, "Open an image")
            p.end(); return

        W, H = self.width(), self.height() - dp(2)
        p.setRenderHint(QPainter.Antialiasing, False)

        def _draw_channel(hist, color_hex, alpha=180):
            mx = max(hist.max(), 1)
            clr = QColor(color_hex)
            clr.setAlpha(alpha)
            p.setPen(QPen(clr, 1))
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.moveTo(0, H)
            for i, v in enumerate(hist):
                x = i * W / 256
                y = H - (v / mx) * H * 0.95
                path.lineTo(x, y)
            path.lineTo(W, H)
            fill = QColor(color_hex); fill.setAlpha(50)
            p.fillPath(path, fill)
            p.drawPath(path)

        ch = self._channel
        if ch in ("rgb", "r"):
            _draw_channel(self._hists["r"], "#ff5555", 200 if ch == "r" else 120)
        if ch in ("rgb", "g"):
            _draw_channel(self._hists["g"], "#55cc55", 200 if ch == "g" else 120)
        if ch in ("rgb", "b"):
            _draw_channel(self._hists["b"], "#4488ff", 200 if ch == "b" else 120)
        if ch == "lum":
            _draw_channel(self._hists["lum"], "#aaaaaa", 220)

        p.setPen(QColor(C.BORDER))
        p.drawRect(0, 0, W - 1, H - 1)
        p.end()


# ── AIWorker ──────────────────────────────────────────────────────────────────
class AIWorker(QObject):
    """Runs AI operations in a background thread."""
    finished = pyqtSignal(object, str)  # result, label
    error = pyqtSignal(str)
    progress = pyqtSignal(int, str)     # pct, message

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result, "")
        except Exception as e:
            self.error.emit(str(e))


# ── AIProgressDialog ──────────────────────────────────────────────────────────
class AIProgressDialog(QDialog):
    """Modal progress dialog for AI operations."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        self.setFixedWidth(dp(360))
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setSpacing(dp(12))
        layout.setContentsMargins(dp(20), dp(16), dp(20), dp(16))

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(f"font-size:13px;font-weight:600;color:{C.TEXT_PRI};")
        layout.addWidget(self._title_lbl)

        self._msg_lbl = QLabel("Initializing...")
        self._msg_lbl.setStyleSheet(f"color:{C.TEXT_SEC};font-size:11px;")
        self._msg_lbl.setWordWrap(True)
        layout.addWidget(self._msg_lbl)

        from PyQt5.QtWidgets import QProgressBar
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(dp(8))
        layout.addWidget(self._bar)

        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setStyleSheet(f"color:{C.TEXT_MUT};font-size:10px;")
        self._pct_lbl.setAlignment(Qt.AlignRight)
        layout.addWidget(self._pct_lbl)

    def set_message(self, msg):
        self._msg_lbl.setText(msg)

    def set_progress(self, pct, msg=""):
        self._bar.setValue(int(pct))
        self._pct_lbl.setText(f"{int(pct)}%")
        if msg:
            self._msg_lbl.setText(msg)
        QApplication.processEvents()


# ── CommandPaletteDialog ──────────────────────────────────────────────────────
class CommandPaletteDialog(QDialog):
    """Ctrl+K command palette for quick access to all actions."""
    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setFixedSize(dp(480), dp(400))
        self.setModal(True)
        self._all_commands = commands  # list of (label, category, callable)
        self._selected = 0
        self._filtered = commands      # always starts as full list

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(dp(50))
        header.setStyleSheet(f"background:{C.BG1};border-bottom:1px solid {C.BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(dp(12), 0, dp(12), 0)
        icon_lbl = QLabel("⌘")
        icon_lbl.setStyleSheet(f"color:{C.ACCENT};font-size:20px;font-weight:bold;")
        hl.addWidget(icon_lbl)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Type a command...")
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background:transparent; border:none; color:{C.TEXT_PRI};
                font-size:14px; padding:0 8px;
            }}
        """)
        self._search.textChanged.connect(self._filter)
        hl.addWidget(self._search, 1)
        layout.addWidget(header)

        # Results
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{ background:{C.BG1}; border:none; outline:none; }}
            QListWidget::item {{ padding:8px 12px; border-bottom:1px solid {C.BG0}; }}
            QListWidget::item:selected {{ background:{C.ACCENT_D}; color:{C.ACCENT}; }}
        """)
        self._list.itemDoubleClicked.connect(self._exec_selected)
        layout.addWidget(self._list, 1)

        # Footer
        footer = QWidget()
        footer.setFixedHeight(dp(30))
        footer.setStyleSheet(f"background:{C.BG0};border-top:1px solid {C.BORDER};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(dp(12), 0, dp(12), 0)
        fl.addWidget(QLabel("↑↓ navigate   Enter select   Esc close"))
        fl.itemAt(0).widget().setStyleSheet(f"color:{C.TEXT_MUT};font-size:10px;")
        layout.addWidget(footer)

        self._populate(commands)
        self._search.setFocus()

    def _populate(self, commands):
        self._list.clear()
        for label, cat, _ in commands:
            item = QListWidgetItem(f"{label}")
            item.setData(Qt.UserRole, label)
            cat_badge = QLabel(f" {cat}")
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _filter(self, text):
        text = text.lower()
        self._filtered = [(l, c, fn) for l, c, fn in self._all_commands
                          if text in l.lower() or text in c.lower()] if text else list(self._all_commands)
        self._populate(self._filtered)

    def _exec_selected(self, item=None):
        row = self._list.currentRow()
        cmds = getattr(self, "_filtered", self._all_commands)
        if 0 <= row < len(cmds):
            _, _, fn = cmds[row]
            self.accept()
            fn()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Return or e.key() == Qt.Key_Enter:
            self._exec_selected()
        elif e.key() == Qt.Key_Escape:
            self.reject()
        elif e.key() == Qt.Key_Down:
            r = self._list.currentRow()
            self._list.setCurrentRow(min(r + 1, self._list.count() - 1))
        elif e.key() == Qt.Key_Up:
            r = self._list.currentRow()
            self._list.setCurrentRow(max(r - 1, 0))
        else:
            super().keyPressEvent(e)


# ── ColorSwatch widget ────────────────────────────────────────────────────────
class ColorSwatchWidget(QWidget):
    """FG/BG color boxes with swap button."""
    fg_changed = pyqtSignal(QColor)
    bg_changed = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fg = QColor(255, 255, 255)
        self._bg = QColor(0, 0, 0)
        self.setFixedHeight(dp(60))

    def set_fg(self, c): self._fg = c; self.update()
    def set_bg(self, c): self._bg = c; self.update()
    def fg(self): return self._fg
    def bg(self): return self._bg

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        sz = dp(36); gap = dp(14); sx = dp(8); sy = dp(12)
        # BG box (behind)
        p.setPen(QPen(QColor(C.BORDER), 1))
        p.setBrush(QBrush(self._bg))
        p.drawRect(sx + gap, sy + gap, sz, sz)
        # FG box (front)
        p.setBrush(QBrush(self._fg))
        p.drawRect(sx, sy, sz, sz)
        # Swap arrows
        p.setPen(QColor(C.TEXT_SEC)); p.setFont(QFont("Segoe UI", 9))
        p.drawText(sx + sz + dp(4), sy + sz // 2, "⇄")
        p.end()

    def mousePressEvent(self, e):
        sz = dp(36); gap = dp(14); sx = dp(8); sy = dp(12)
        pos = e.pos()
        # Click swap area
        if pos.x() > sx + sz:
            self._fg, self._bg = self._bg, self._fg
            self.fg_changed.emit(self._fg); self.bg_changed.emit(self._bg); self.update(); return
        # Click FG
        if sx <= pos.x() <= sx + sz and sy <= pos.y() <= sy + sz:
            c = QColorDialog.getColor(self._fg, self, "Foreground Color")
            if c.isValid(): self._fg = c; self.fg_changed.emit(c); self.update()
        # Click BG
        elif sx + gap <= pos.x() <= sx + gap + sz and sy + gap <= pos.y() <= sy + gap + sz:
            c = QColorDialog.getColor(self._bg, self, "Background Color")
            if c.isValid(): self._bg = c; self.bg_changed.emit(c); self.update()

# ── LayerPanel ────────────────────────────────────────────────────────────────
class LayerPanel(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setMinimumWidth(dp(240))
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        # Blend / Opacity row
        opts = QWidget(); opts.setFixedHeight(dp(68))
        opts.setStyleSheet(f"background:{C.BG2}; border-bottom:1px solid {C.BORDER};")
        ol = QVBoxLayout(opts); ol.setContentsMargins(dp(8), dp(5), dp(8), dp(5)); ol.setSpacing(dp(4))
        # Blend mode row with "Mode:" label
        br = QHBoxLayout(); br.setSpacing(dp(6))
        mode_lbl = QLabel("Mode:")
        mode_lbl.setStyleSheet(f"color:{C.TEXT_MUT}; font-size:10px;")
        mode_lbl.setFixedWidth(dp(34))
        br.addWidget(mode_lbl)
        self.blend_combo = QComboBox()
        self.blend_combo.addItems(Layer.BLEND_MODES)
        self.blend_combo.currentTextChanged.connect(self.on_blend_change)
        self.blend_combo.setFixedHeight(dp(24))
        br.addWidget(self.blend_combo)
        ol.addLayout(br)
        # Opacity row
        orow = QHBoxLayout(); orow.setSpacing(dp(6))
        op_lbl = QLabel("Opacity:")
        op_lbl.setStyleSheet(f"color:{C.TEXT_MUT}; font-size:10px;")
        op_lbl.setFixedWidth(dp(48))
        orow.addWidget(op_lbl)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100); self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.on_opacity_change)
        orow.addWidget(self.opacity_slider)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setFixedWidth(dp(32))
        self.opacity_label.setStyleSheet(f"color:{C.TEXT_SEC}; font-size:10px; font-family:Consolas;")
        orow.addWidget(self.opacity_label)
        ol.addLayout(orow)
        layout.addWidget(opts)

        # Layer list
        self.layer_list = QListWidget()
        self.layer_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.layer_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.layer_list.setIconSize(QSize(dp(40), dp(32)))
        self.layer_list.setStyleSheet(
            f"QListWidget::item {{ padding: 4px 6px; min-height: {dp(38)}px; }}"
            f"QListWidget::item:selected {{ background: {C.ACCENT_D}; color: {C.ACCENT}; }}"
            f"QListWidget::item:hover:!selected {{ background: {C.BG3}; }}"
        )
        self.layer_list.currentRowChanged.connect(self.on_layer_selected)
        self.layer_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.layer_list.model().rowsMoved.connect(self.on_layers_reordered)
        self.layer_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.layer_list, 1)

        # Action buttons
        acts = QWidget(); acts.setFixedHeight(dp(38))
        acts.setStyleSheet(f"background:{C.BG0}; border-top:1px solid {C.BORDER};")
        al = QHBoxLayout(acts); al.setContentsMargins(dp(4), dp(3), dp(4), dp(3)); al.setSpacing(dp(2))

        def _ico_btn(svg_key, tip, cb):
            b = QToolButton(); b.setIcon(svg_icon(svg_key, C.TEXT_SEC, dp(15)))
            b.setToolTip(tip); b.setFixedSize(dp(30), dp(30))
            b.clicked.connect(cb); return b

        al.addWidget(_ico_btn("layer-new",   "New Layer",       self.add_layer))
        al.addWidget(_ico_btn("layer-dup",   "Duplicate Layer", self.duplicate_layer))
        al.addWidget(_ico_btn("layer-merge", "Merge Down",      self.merge_down))
        al.addWidget(_ico_btn("layer-del",   "Delete Layer",    self.remove_layer))
        # fx button
        self.fx_btn = QPushButton("fx")
        self.fx_btn.setFixedSize(dp(30), dp(30))
        self.fx_btn.setToolTip("Layer Effects")
        self.fx_btn.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_MUT};border:1px solid {C.BORDER};"
            f"border-radius:4px;font-size:{dp(10)}px;font-style:italic;font-weight:bold;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};color:{C.ACCENT};}}"
            f"QPushButton[active=true]{{background:{C.ACCENT_D};color:{C.ACCENT};border-color:{C.ACCENT};}}")
        self.fx_btn.clicked.connect(self.open_fx_dialog)
        al.addWidget(self.fx_btn)
        # Group button
        self.group_btn = QToolButton()
        self.group_btn.setToolTip("Group Selected Layers (Ctrl+G)")
        self.group_btn.setText("G")
        self.group_btn.setFixedSize(dp(30), dp(30))
        self.group_btn.setStyleSheet(
            f"QToolButton{{background:{C.BG2};color:{C.TEXT_MUT};border:1px solid {C.BORDER};"
            f"border-radius:4px;font-size:{dp(10)}px;font-weight:bold;}}"
            f"QToolButton:hover{{border-color:{C.ACCENT};color:{C.ACCENT};}}")
        self.group_btn.clicked.connect(self.group_selected)
        al.addWidget(self.group_btn)
        al.addStretch()
        self.vis_btn = QToolButton(); self.vis_btn.setCheckable(True); self.vis_btn.setChecked(True)
        self.vis_btn.setToolTip("Toggle Visibility")
        self.vis_btn.setIcon(svg_icon("eye-open", C.TEXT_SEC, dp(15)))
        self.vis_btn.setFixedSize(dp(30), dp(30))
        self.vis_btn.toggled.connect(self.on_visibility_toggle)
        al.addWidget(self.vis_btn)
        self.lock_btn = QToolButton(); self.lock_btn.setCheckable(True)
        self.lock_btn.setToolTip("Lock Layer")
        self.lock_btn.setIcon(svg_icon("lock-open", C.TEXT_SEC, dp(15)))
        self.lock_btn.setFixedSize(dp(30), dp(30))
        self.lock_btn.toggled.connect(self.on_lock_toggle)
        al.addWidget(self.lock_btn)
        layout.addWidget(acts)

        # ── Mask actions row ──────────────────────────────────────────────────
        mask_row = QWidget(); mask_row.setFixedHeight(dp(34))
        mask_row.setStyleSheet(f"background:{C.BG2}; border-top:1px solid {C.BORDER};")
        ml = QHBoxLayout(mask_row)
        ml.setContentsMargins(dp(4), dp(3), dp(4), dp(3)); ml.setSpacing(dp(2))

        lbl = QLabel("Mask:")
        lbl.setStyleSheet(f"color:{C.TEXT_MUT}; font-size:{dp(10)}px;")
        lbl.setFixedWidth(dp(36))
        ml.addWidget(lbl)

        def _mask_btn(text, tip, cb):
            b = QPushButton(text); b.setFixedHeight(dp(26)); b.setToolTip(tip)
            b.setStyleSheet(
                f"QPushButton{{background:{C.BG3};color:{C.TEXT_SEC};border:1px solid {C.BORDER};"
                f"border-radius:3px;padding:0 5px;font-size:{dp(10)}px;}}"
                f"QPushButton:hover{{border-color:{C.ACCENT};color:{C.ACCENT};}}")
            b.clicked.connect(cb); return b

        self.mask_add_btn    = _mask_btn("+White",    "Add white mask (reveal all)",  self.mask_add_white)
        self.mask_add_black  = _mask_btn("+Black",    "Add black mask (hide all)",    self.mask_add_black_fn)
        self.mask_edit_btn   = _mask_btn("Edit",      "Toggle mask editing mode",     self.mask_toggle_edit)
        self.mask_del_btn    = _mask_btn("Delete",    "Delete mask",                  self.mask_delete)
        self.mask_apply_btn  = _mask_btn("Apply",     "Apply mask (bake into layer)", self.mask_apply)
        self.mask_dis_btn    = _mask_btn("Disable",   "Toggle mask enabled/disabled", self.mask_toggle_enable)
        for b in (self.mask_add_btn, self.mask_add_black, self.mask_edit_btn,
                  self.mask_del_btn, self.mask_apply_btn, self.mask_dis_btn):
            ml.addWidget(b)
        ml.addStretch()

        layout.addWidget(mask_row)
        self._mask_row = mask_row

    def _make_thumb(self, layer):
        try:
            tw, th = dp(40), dp(32)
            # LayerGroup: show folder icon with child count
            if isinstance(layer, LayerGroup):
                bg = Image.new("RGBA", (tw, th), (50, 55, 70, 255))
                icon_txt_bg = Image.new("RGBA", (tw, th), (0,0,0,0))
                draw_g = ImageDraw.Draw(bg)
                draw_g.rectangle((2, 8, tw-3, th-3), outline=(120,140,180,200), width=1)
                draw_g.rectangle((2, 5, 14, 10), fill=(120,140,180,200))
                label = f"{len(layer.children)}L"
                try:
                    from PIL import ImageFont
                    font = ImageFont.load_default()
                    draw_g.text((tw//2-8, th//2-4), label, fill=(180,200,230,255), font=font)
                except Exception:
                    pass
                return QIcon(pil_to_qpixmap(bg))
            # Layer thumbnail
            thumb = layer.image.copy()
            thumb.thumbnail((tw, th), Image.LANCZOS)
            bg = Image.new("RGBA", (tw, th), (40, 40, 40, 255))
            ox = (tw - thumb.width) // 2; oy = (th - thumb.height) // 2
            bg.paste(thumb, (ox, oy), thumb)
            icon_img = bg
            if layer.mask is not None:
                # Append a small mask thumbnail to the right
                mtw = dp(28); mth = dp(24)
                combined = Image.new("RGBA", (tw + mtw + dp(4), th), (30, 30, 30, 255))
                combined.paste(bg, (0, 0))
                mthumb = layer.mask.copy().convert("RGB")
                mthumb.thumbnail((mtw, mth), Image.LANCZOS)
                mbg = Image.new("RGB", (mtw, mth), (80, 80, 80))
                mox = (mtw - mthumb.width) // 2; moy = (mth - mthumb.height) // 2
                mbg.paste(mthumb, (mox, moy))
                mbg_rgba = mbg.convert("RGBA")
                # Red tint if editing_mask
                if getattr(layer, 'editing_mask', False):
                    tint = Image.new("RGBA", mbg_rgba.size, (220, 60, 60, 80))
                    mbg_rgba = Image.alpha_composite(mbg_rgba, tint)
                # Bright border if editing
                combined.paste(mbg_rgba, (tw + dp(4), (th - mth) // 2))
                icon_img = combined
            return QIcon(pil_to_qpixmap(icon_img))
        except Exception:
            return QIcon()

    def refresh(self):
        self.layer_list.blockSignals(True)
        self.layer_list.clear()
        for i, layer in enumerate(reversed(self.editor.layers)):
            idx = len(self.editor.layers) - 1 - i
            vis   = "" if layer.visible else " [hidden]"
            lock  = " [L]" if layer.locked else ""
            is_group = isinstance(layer, LayerGroup)
            prefix = "[G] " if is_group else ""
            collapsed_sfx = " ..." if (is_group and layer.collapsed) else ""
            item = QListWidgetItem(self._make_thumb(layer),
                                   f"{prefix}{layer.name}{vis}{lock}{collapsed_sfx}")
            item.setData(Qt.UserRole, idx)
            if not layer.visible:
                item.setForeground(QColor(C.TEXT_MUT))
            elif idx in getattr(self.editor, 'selected_layer_indices', set()):
                item.setForeground(QColor(C.ACCENT))
            self.layer_list.addItem(item)
            # If group is expanded, show children indented (display only)
            if is_group and not layer.collapsed:
                for ci, child in enumerate(reversed(layer.children)):
                    citem = QListWidgetItem(self._make_thumb(child),
                                           f"    {child.name}")
                    citem.setData(Qt.UserRole, (idx, len(layer.children)-1-ci))
                    citem.setFlags(citem.flags() & ~Qt.ItemIsDragEnabled)
                    if not child.visible:
                        citem.setForeground(QColor(C.TEXT_MUT))
                    self.layer_list.addItem(citem)
        active = self.editor.active_layer_index
        di = len(self.editor.layers) - 1 - active
        if 0 <= di < self.layer_list.count():
            self.layer_list.setCurrentRow(di)
        layer = self.editor.active_layer()
        if layer:
            self.opacity_slider.blockSignals(True)
            self.opacity_slider.setValue(layer.opacity * 100 // 255)
            self.opacity_slider.blockSignals(False)
            self.opacity_label.setText(f"{layer.opacity * 100 // 255}%")
            self.vis_btn.blockSignals(True); self.vis_btn.setChecked(layer.visible); self.vis_btn.blockSignals(False)
            self.lock_btn.blockSignals(True); self.lock_btn.setChecked(layer.locked); self.lock_btn.blockSignals(False)
            self.blend_combo.blockSignals(True)
            idx2 = self.blend_combo.findText(layer.blend_mode)
            if idx2 >= 0: self.blend_combo.setCurrentIndex(idx2)
            self.blend_combo.blockSignals(False)
            # fx button active indicator
            has_fx = bool(getattr(layer, 'effects', []))
            self.fx_btn.setProperty("active", "true" if has_fx else "false")
            self.fx_btn.setStyleSheet(self.fx_btn.styleSheet())  # force re-evaluate
            # Update mask button states
            has_mask = layer.mask is not None
            self.mask_add_btn.setVisible(not has_mask)
            self.mask_add_black.setVisible(not has_mask)
            self.mask_edit_btn.setVisible(has_mask)
            self.mask_del_btn.setVisible(has_mask)
            self.mask_apply_btn.setVisible(has_mask)
            self.mask_dis_btn.setVisible(has_mask)
            if has_mask:
                editing = getattr(layer, 'editing_mask', False)
                enabled = getattr(layer, 'mask_enabled', True)
                self.mask_edit_btn.setStyleSheet(
                    self.mask_edit_btn.styleSheet().replace("color:" + C.TEXT_SEC, "color:" + (C.ACCENT if editing else C.TEXT_SEC)))
                self.mask_dis_btn.setText("Enable" if not enabled else "Disable")
        self.layer_list.blockSignals(False)

    def on_item_double_clicked(self, item):
        """Double-click: toggle group collapse or rename."""
        idx = item.data(Qt.UserRole)
        if isinstance(idx, int) and 0 <= idx < len(self.editor.layers):
            layer = self.editor.layers[idx]
            if isinstance(layer, LayerGroup):
                layer.collapsed = not layer.collapsed
                self.refresh(); return
            self.on_layer_rename_by_idx(layer, idx)
        elif isinstance(idx, tuple):
            # Child row — rename child
            parent_idx, child_idx = idx
            parent = self.editor.layers[parent_idx]
            if isinstance(parent, LayerGroup) and 0 <= child_idx < len(parent.children):
                self.on_layer_rename_by_idx(parent.children[child_idx], None)

    def on_layer_rename(self, item):
        """Double-click a layer to rename it (legacy, kept for compatibility)."""
        layer_idx = item.data(Qt.UserRole)
        if isinstance(layer_idx, int) and layer_idx < len(self.editor.layers):
            self.on_layer_rename_by_idx(self.editor.layers[layer_idx], layer_idx)

    def on_layer_rename_by_idx(self, layer, idx):
        new_name, ok = QInputDialog.getText(self, "Rename Layer", "Layer name:", text=layer.name)
        if ok and new_name.strip():
            self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Rename Layer")
            layer.name = new_name.strip()
            self.refresh()

    def on_layer_selected(self, row):
        if row < 0: return
        item = self.layer_list.item(row)
        if item:
            idx = item.data(Qt.UserRole)
            if isinstance(idx, tuple):
                # Child of a group — select the group
                self.editor.active_layer_index = idx[0]
            else:
                self.editor.active_layer_index = idx
            self.refresh(); self.editor.canvas.update()

    def on_selection_changed(self):
        """Track multi-selected layer indices in editor.selected_layer_indices."""
        sel = set()
        for item in self.layer_list.selectedItems():
            idx = item.data(Qt.UserRole)
            if isinstance(idx, int):
                sel.add(idx)
        self.editor.selected_layer_indices = sel
        # Update group button enabled state
        self.group_btn.setEnabled(len(sel) >= 2)

    def on_layers_reordered(self):
        new = []
        for i in range(self.layer_list.count()):
            new.append(self.editor.layers[self.layer_list.item(i).data(Qt.UserRole)])
        new.reverse(); self.editor.layers = new
        self.editor.active_layer_index = max(0, min(self.editor.active_layer_index, len(self.editor.layers) - 1))
        self.refresh(); self.editor.canvas.update()

    def on_opacity_change(self, v):
        layer = self.editor.active_layer()
        if layer:
            layer.opacity = int(v * 255 / 100)
            self.opacity_label.setText(f"{v}%")
            self.editor.canvas.update()

    def on_blend_change(self, mode):
        layer = self.editor.active_layer()
        if layer: layer.blend_mode = mode; self.editor.canvas.update()

    def on_visibility_toggle(self, checked):
        layer = self.editor.active_layer()
        if layer:
            layer.visible = checked
            key = "eye-open" if checked else "eye-closed"
            self.vis_btn.setIcon(svg_icon(key, C.ACCENT if not checked else C.TEXT_SEC, dp(14)))
            self.refresh(); self.editor.canvas.update()

    def on_lock_toggle(self, checked):
        layer = self.editor.active_layer()
        if layer:
            layer.locked = checked
            key = "lock-closed" if checked else "lock-open"
            self.lock_btn.setIcon(svg_icon(key, C.ACCENT if checked else C.TEXT_SEC, dp(14)))
            self.refresh()

    def add_layer(self):
        if not self.editor.layers: return
        w, h = self.editor.layers[0].image.size
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "New Layer")
        name = f"Layer {len(self.editor.layers) + 1}"
        self.editor.layers.append(Layer(name, w, h))
        self.editor.active_layer_index = len(self.editor.layers) - 1
        self.refresh(); self.editor.canvas.update()
        self.editor.update_history_panel()

    def remove_layer(self):
        if len(self.editor.layers) <= 1: return
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Delete Layer")
        del self.editor.layers[self.editor.active_layer_index]
        self.editor.active_layer_index = max(0, self.editor.active_layer_index - 1)
        self.refresh(); self.editor.canvas.update()

    def duplicate_layer(self):
        layer = self.editor.active_layer()
        if layer:
            self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Duplicate Layer")
            self.editor.layers.insert(self.editor.active_layer_index + 1, layer.copy())
            self.editor.active_layer_index += 1
            self.refresh(); self.editor.canvas.update()

    def merge_down(self):
        self.editor.merge_down()

    def open_fx_dialog(self):
        layer = self.editor.active_layer()
        if not layer: return
        dlg = FxDialog(layer, self.editor, self)
        if dlg.exec_() == QDialog.Accepted:
            self.editor.canvas.update()
            self.refresh()

    def group_selected(self):
        """Group the currently multi-selected layers into a LayerGroup."""
        sel = sorted(self.editor.selected_layer_indices)
        if len(sel) < 1: return
        if not self.editor.layers: return
        w, h = self.editor.layers[0].image.size
        self.editor.history.save_state(
            self.editor.layers, self.editor.active_layer_index, "Group Layers")
        # Collect layers in order (lowest index first = bottom)
        children = [self.editor.layers[i] for i in sel if i < len(self.editor.layers)]
        group = LayerGroup(f"Group {len(self.editor.layers)}", w, h)
        group.children = children
        # Replace first selected layer with group, remove the rest
        insert_pos = min(sel)
        new_layers = [l for i, l in enumerate(self.editor.layers) if i not in sel]
        new_layers.insert(insert_pos, group)
        self.editor.layers = new_layers
        self.editor.active_layer_index = insert_pos
        self.editor.selected_layer_indices = set()
        self.refresh(); self.editor.canvas.update()

    def ungroup(self):
        """Ungroup the active LayerGroup back to flat layers."""
        layer = self.editor.active_layer()
        if not isinstance(layer, LayerGroup): return
        self.editor.history.save_state(
            self.editor.layers, self.editor.active_layer_index, "Ungroup")
        idx = self.editor.active_layer_index
        children = list(layer.children)
        new_layers = self.editor.layers[:idx] + children + self.editor.layers[idx+1:]
        self.editor.layers = new_layers
        self.editor.active_layer_index = max(0, idx)
        self.refresh(); self.editor.canvas.update()

    # ── Mask actions ───────────────────────────────────────────────────────────

    def mask_add_white(self):
        layer = self.editor.active_layer()
        if not layer: return
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Add Mask")
        layer.add_mask("white")
        layer.editing_mask = True
        self.refresh(); self.editor.canvas.update()
        self.editor._status("Layer mask added — painting white=reveal, black=hide")

    def mask_add_black_fn(self):
        layer = self.editor.active_layer()
        if not layer: return
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Add Black Mask")
        layer.add_mask("black")
        layer.editing_mask = True
        self.refresh(); self.editor.canvas.update()
        self.editor._status("Black mask added — layer hidden; paint white to reveal")

    def mask_toggle_edit(self):
        layer = self.editor.active_layer()
        if not layer or layer.mask is None: return
        layer.editing_mask = not layer.editing_mask
        self.refresh(); self.editor.canvas.update()
        mode = "mask" if layer.editing_mask else "layer"
        self.editor._status(f"Now editing: {mode}")

    def mask_delete(self):
        layer = self.editor.active_layer()
        if not layer or layer.mask is None: return
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Delete Mask")
        layer.delete_mask()
        self.refresh(); self.editor.canvas.update()

    def mask_apply(self):
        layer = self.editor.active_layer()
        if not layer or layer.mask is None: return
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, "Apply Mask")
        layer.apply_mask()
        self.refresh(); self.editor.canvas.update()

    def mask_toggle_enable(self):
        layer = self.editor.active_layer()
        if not layer or layer.mask is None: return
        layer.mask_enabled = not layer.mask_enabled
        self.refresh(); self.editor.canvas.update()
        state = "enabled" if layer.mask_enabled else "disabled"
        self.editor._status(f"Mask {state}")

# ── FxDialog ─────────────────────────────────────────────────────────────────
class FxDialog(QDialog):
    """Non-destructive layer effects stack editor."""

    EFFECT_TYPES = [
        ("drop_shadow",    "Drop Shadow"),
        ("outer_glow",     "Outer Glow"),
        ("inner_glow",     "Inner Glow"),
        ("bevel_emboss",   "Bevel & Emboss"),
        ("color_overlay",  "Color Overlay"),
        ("gradient_overlay","Gradient Overlay"),
        ("stroke",         "Stroke"),
    ]

    # Default params for each effect type
    DEFAULTS = {
        "drop_shadow":      {"blur": 8,  "opacity": 180, "angle": 135, "distance": 8,
                             "color": [0,0,0]},
        "outer_glow":       {"blur": 12, "opacity": 160, "spread": 0,
                             "color": [255,255,200]},
        "inner_glow":       {"blur": 10, "opacity": 140,
                             "color": [255,255,200]},
        "bevel_emboss":     {"depth": 3, "size": 5, "opacity": 150, "angle": 135,
                             "highlight_color": [255,255,255], "shadow_color": [0,0,0]},
        "color_overlay":    {"opacity": 255, "color": [255,0,0]},
        "gradient_overlay": {"opacity": 200, "angle": 90,
                             "color1": [0,0,255], "color2": [255,0,0]},
        "stroke":           {"size": 3, "opacity": 255, "position": "outside",
                             "color": [0,0,0]},
    }

    def __init__(self, layer, editor, parent=None):
        super().__init__(parent)
        self.layer  = layer
        self.editor = editor
        self._orig_effects = [dict(fx) for fx in layer.effects]
        self.setWindowTitle(f"Layer Effects — {layer.name}")
        self.setMinimumSize(dp(640), dp(480))
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog{{background:{C.BG1};color:{C.TEXT_PRI};}}
            QGroupBox{{background:{C.BG2};border:1px solid {C.BORDER};border-radius:4px;
                       margin-top:{dp(14)}px;padding:{dp(8)}px;color:{C.TEXT_SEC};font-size:{dp(11)}px;}}
            QGroupBox::title{{subcontrol-origin:margin;left:{dp(8)}px;top:-{dp(6)}px;}}
            QLabel{{color:{C.TEXT_SEC};font-size:{dp(11)}px;background:transparent;}}
            QSpinBox,QDoubleSpinBox,QComboBox{{background:{C.BG3};color:{C.TEXT_PRI};
                border:1px solid {C.BORDER};border-radius:3px;padding:2px 4px;
                selection-background-color:{C.ACCENT_D};}}
            QCheckBox{{color:{C.TEXT_SEC};font-size:{dp(11)}px;spacing:{dp(5)}px;}}
            QPushButton{{background:{C.BG3};color:{C.TEXT_SEC};border:1px solid {C.BORDER};
                border-radius:4px;padding:{dp(4)}px {dp(10)}px;font-size:{dp(11)}px;}}
            QPushButton:hover{{border-color:{C.ACCENT};color:{C.ACCENT};}}
            QListWidget{{background:{C.BG0};border:1px solid {C.BORDER};border-radius:3px;}}
            QListWidget::item{{padding:{dp(5)}px {dp(8)}px;color:{C.TEXT_SEC};}}
            QListWidget::item:selected{{background:{C.ACCENT_D};color:{C.ACCENT};}}
        """)
        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(dp(10), dp(10), dp(10), dp(10))
        main.setSpacing(dp(10))

        # ── Left: effect list ─────────────────────────────────────────────────
        left = QVBoxLayout(); left.setSpacing(dp(5))
        lbl = QLabel("Effects")
        lbl.setStyleSheet(f"color:{C.TEXT_PRI};font-size:{dp(12)}px;font-weight:bold;")
        left.addWidget(lbl)
        self.fx_list = QListWidget()
        self.fx_list.setFixedWidth(dp(175))
        self.fx_list.currentRowChanged.connect(self._on_row_change)
        left.addWidget(self.fx_list, 1)

        # Add / Remove buttons
        btn_row = QHBoxLayout(); btn_row.setSpacing(dp(4))
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_effect)
        btn_row.addWidget(add_btn)
        self.del_btn = QPushButton("Remove")
        self.del_btn.clicked.connect(self._remove_effect)
        btn_row.addWidget(self.del_btn)
        left.addLayout(btn_row)
        main.addLayout(left)

        # ── Right: parameters panel ───────────────────────────────────────────
        right = QVBoxLayout(); right.setSpacing(dp(6))
        self.params_label = QLabel("Select an effect to edit its parameters")
        self.params_label.setStyleSheet(
            f"color:{C.TEXT_MUT};font-size:{dp(11)}px;font-style:italic;")
        right.addWidget(self.params_label)
        self.params_area = QWidget()
        self.params_layout = QVBoxLayout(self.params_area)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        self.params_layout.setSpacing(dp(6))
        right.addWidget(self.params_area, 1)
        right.addStretch()
        main.addLayout(right, 1)

        # ── Bottom: OK / Cancel ───────────────────────────────────────────────
        outer = QVBoxLayout()
        outer.addLayout(main, 1)
        btn_bottom = QHBoxLayout(); btn_bottom.addStretch()
        ok = QPushButton("OK")
        ok.setStyleSheet(
            f"QPushButton{{background:{C.ACCENT};color:{C.BG0};border:none;border-radius:4px;"
            f"padding:{dp(5)}px {dp(18)}px;font-weight:bold;}}"
            f"QPushButton:hover{{background:#a6d3f5;}}")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._cancel)
        btn_bottom.addWidget(cancel); btn_bottom.addWidget(ok)
        outer.addLayout(btn_bottom)
        # replace existing layout
        while self.layout().count():
            self.layout().takeAt(0)
        for i in range(outer.count()):
            item = outer.itemAt(i)
            if item.widget():
                self.layout().addWidget(item.widget())
            elif item.layout():
                self.layout().addLayout(item.layout())

        # Use a proper single layout
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(dp(10), dp(10), dp(10), dp(10))
        self.layout().setSpacing(dp(8))
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(dp(10))
        # Left panel
        lp = QWidget(); lp.setFixedWidth(dp(175))
        ll = QVBoxLayout(lp); ll.setContentsMargins(0,0,0,0); ll.setSpacing(dp(5))
        lbl2 = QLabel("Active Effects")
        lbl2.setStyleSheet(f"color:{C.TEXT_PRI};font-size:{dp(12)}px;font-weight:bold;")
        ll.addWidget(lbl2)
        self.fx_list = QListWidget()
        self.fx_list.currentRowChanged.connect(self._on_row_change)
        ll.addWidget(self.fx_list, 1)
        br = QHBoxLayout(); br.setSpacing(dp(4))
        ab = QPushButton("+ Add"); ab.clicked.connect(self._add_effect)
        rb = QPushButton("Remove"); rb.clicked.connect(self._remove_effect)
        br.addWidget(ab); br.addWidget(rb)
        ll.addLayout(br)
        content_layout.addWidget(lp)
        # Right panel
        rp = QWidget()
        rl = QVBoxLayout(rp); rl.setContentsMargins(0,0,0,0); rl.setSpacing(dp(6))
        self.params_label = QLabel("Select an effect")
        self.params_label.setStyleSheet(f"color:{C.TEXT_MUT};font-style:italic;font-size:{dp(11)}px;")
        rl.addWidget(self.params_label)
        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setStyleSheet(f"QScrollArea{{border:none;background:{C.BG1};}}")
        self.params_container = QWidget()
        self.params_layout = QVBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        self.params_layout.setAlignment(Qt.AlignTop)
        self.params_scroll.setWidget(self.params_container)
        rl.addWidget(self.params_scroll, 1)
        content_layout.addWidget(rp, 1)
        self.layout().addWidget(content, 1)
        # Bottom buttons
        bb = QHBoxLayout(); bb.addStretch()
        ok2 = QPushButton("OK")
        ok2.setStyleSheet(
            f"QPushButton{{background:{C.ACCENT};color:{C.BG0};border:none;border-radius:4px;"
            f"padding:{dp(5)}px {dp(18)}px;font-weight:bold;}}"
            f"QPushButton:hover{{background:#a6d3f5;}}")
        ok2.clicked.connect(self.accept)
        ca2 = QPushButton("Cancel"); ca2.clicked.connect(self._cancel)
        bb.addWidget(ca2); bb.addWidget(ok2)
        self.layout().addLayout(bb)

    def _populate_list(self):
        self.fx_list.clear()
        for fx in self.layer.effects:
            label = dict(self.EFFECT_TYPES).get(fx["type"], fx["type"])
            enabled = fx.get("enabled", True)
            item = QListWidgetItem(("" if enabled else "[off] ") + label)
            item.setForeground(QColor(C.ACCENT if enabled else C.TEXT_MUT))
            self.fx_list.addItem(item)
        self.editor.canvas.update()

    def _on_row_change(self, row):
        # Clear params panel
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if row < 0 or row >= len(self.layer.effects): return
        fx = self.layer.effects[row]
        label = dict(self.EFFECT_TYPES).get(fx["type"], fx["type"])
        self.params_label.setText(label)
        self._build_params(fx)

    def _build_params(self, fx):
        """Build parameter widgets for a given fx dict."""
        def spn(key, lo, hi, suffix="", val=None, step=1):
            w = QSpinBox(); w.setRange(lo, hi)
            w.setValue(fx.get(key, val if val is not None else lo))
            if suffix: w.setSuffix(suffix)
            w.setSingleStep(step)
            w.valueChanged.connect(lambda v, k=key: self._update_fx(fx, k, v))
            return w

        def col_btn(key, default):
            c = fx.get(key, default)
            if not isinstance(c, (list, tuple)): c = default
            btn = QPushButton()
            btn.setFixedSize(dp(40), dp(22))
            btn.setStyleSheet(
                f"background: rgb({c[0]},{c[1]},{c[2]}); border:1px solid {C.BORDER}; border-radius:3px;")
            def pick(checked=False, k=key, b=btn):
                cur = fx.get(k, default)
                if not isinstance(cur, (list, tuple)): cur = default
                qc = QColorDialog.getColor(QColor(*cur[:3]), self, "Choose Color")
                if qc.isValid():
                    fx[k] = [qc.red(), qc.green(), qc.blue()]
                    b.setStyleSheet(
                        f"background: rgb({qc.red()},{qc.green()},{qc.blue()});"
                        f" border:1px solid {C.BORDER}; border-radius:3px;")
                    self.editor.canvas.update()
            btn.clicked.connect(pick)
            return btn

        def row(label, widget):
            r = QHBoxLayout(); r.setSpacing(dp(6))
            lbl = QLabel(label); lbl.setFixedWidth(dp(110))
            r.addWidget(lbl); r.addWidget(widget); r.addStretch()
            self.params_layout.addLayout(r)

        def chk(key, label_text):
            w = QCheckBox(label_text); w.setChecked(fx.get(key, True))
            w.toggled.connect(lambda v, k=key: (self._update_fx(fx, k, v), self._populate_list()))
            return w

        kind = fx.get("type", "")
        # Enabled toggle
        self.params_layout.addWidget(chk("enabled", "Effect Enabled"))

        if kind in ("drop_shadow", "outer_glow", "inner_glow"):
            row("Opacity:", spn("opacity", 0, 255))
            row("Blur:", spn("blur", 0, 60, "px"))
            if kind == "drop_shadow":
                row("Distance:", spn("distance", 0, 100, "px"))
                row("Angle:", spn("angle", 0, 360, "°"))
            if kind == "outer_glow":
                row("Spread:", spn("spread", 0, 30, "px"))
            row("Color:", col_btn("color", [0, 0, 0] if kind == "drop_shadow" else [255, 255, 200]))

        elif kind == "bevel_emboss":
            row("Opacity:", spn("opacity", 0, 255))
            row("Depth:", spn("depth", 1, 20))
            row("Size:", spn("size", 1, 30, "px"))
            row("Angle:", spn("angle", 0, 360, "°"))
            r2 = QHBoxLayout(); r2.setSpacing(dp(6))
            r2.addWidget(QLabel("Highlight:")); r2.addWidget(col_btn("highlight_color", [255,255,255]))
            r2.addWidget(QLabel("Shadow:"));    r2.addWidget(col_btn("shadow_color",    [0,0,0]))
            r2.addStretch(); self.params_layout.addLayout(r2)

        elif kind == "color_overlay":
            row("Opacity:", spn("opacity", 0, 255))
            row("Color:", col_btn("color", [255, 0, 0]))

        elif kind == "gradient_overlay":
            row("Opacity:", spn("opacity", 0, 255))
            row("Angle:", spn("angle", 0, 360, "°"))
            r2 = QHBoxLayout(); r2.setSpacing(dp(6))
            r2.addWidget(QLabel("Color 1:")); r2.addWidget(col_btn("color1", [0,0,255]))
            r2.addWidget(QLabel("Color 2:")); r2.addWidget(col_btn("color2", [255,0,0]))
            r2.addStretch(); self.params_layout.addLayout(r2)

        elif kind == "stroke":
            row("Size:", spn("size", 1, 50, "px"))
            row("Opacity:", spn("opacity", 0, 255))
            pos_w = QComboBox()
            pos_w.addItems(["outside", "inside", "center"])
            pos_w.setCurrentText(fx.get("position", "outside"))
            pos_w.currentTextChanged.connect(lambda v: self._update_fx(fx, "position", v))
            row("Position:", pos_w)
            row("Color:", col_btn("color", [0, 0, 0]))

        self.params_layout.addStretch()

    def _update_fx(self, fx, key, val):
        fx[key] = val
        self.editor.canvas.update()

    def _add_effect(self):
        """Show a menu to pick which effect to add."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};
                   padding:4px;}}
            QMenu::item{{padding:5px 16px 5px 10px;}}
            QMenu::item:selected{{background:{C.ACCENT_D};color:{C.ACCENT};}}
        """)
        for type_id, type_label in self.EFFECT_TYPES:
            act = menu.addAction(type_label)
            act.setData(type_id)
        chosen = menu.exec_(self.fx_list.mapToGlobal(
            self.fx_list.rect().bottomLeft() + QPoint(0, 2)))
        if chosen and chosen.data():
            type_id = chosen.data()
            new_fx = {"type": type_id, "enabled": True}
            new_fx.update(self.DEFAULTS.get(type_id, {}))
            self.layer.effects.append(new_fx)
            self._populate_list()
            self.fx_list.setCurrentRow(len(self.layer.effects) - 1)

    def _remove_effect(self):
        row = self.fx_list.currentRow()
        if 0 <= row < len(self.layer.effects):
            del self.layer.effects[row]
            self._populate_list()
            self.fx_list.setCurrentRow(min(row, len(self.layer.effects) - 1))

    def _cancel(self):
        self.layer.effects = self._orig_effects
        self.editor.canvas.update()
        self.reject()


# ── ChannelsPanel ────────────────────────────────────────────────────────────
class ChannelsPanel(QWidget):
    """Shows R/G/B/A channel thumbnails with visibility toggles."""

    CHANNELS = [("R", "Red", (255,0,0)), ("G", "Green", (0,220,0)),
                ("B", "Blue", (0,120,255)), ("A", "Alpha", (180,180,180))]

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self._hidden = set()    # set of channel letters that are hidden
        layout = QVBoxLayout(self)
        layout.setContentsMargins(dp(6), dp(8), dp(6), dp(8))
        layout.setSpacing(dp(4))

        hdr = QLabel("Channels")
        hdr.setStyleSheet(f"color:{C.TEXT_PRI};font-size:{dp(12)}px;font-weight:bold;")
        layout.addWidget(hdr)

        self.rows = {}
        for ch, name, col in self.CHANNELS:
            row = QWidget(); row.setFixedHeight(dp(44))
            row.setStyleSheet(f"background:{C.BG2};border:1px solid {C.BORDER};border-radius:3px;")
            rl = QHBoxLayout(row); rl.setContentsMargins(dp(5),dp(3),dp(5),dp(3)); rl.setSpacing(dp(6))
            # Eye toggle
            eye = QToolButton(); eye.setCheckable(True); eye.setChecked(True)
            eye.setFixedSize(dp(18), dp(18))
            eye.setText("V")
            eye.setStyleSheet(
                f"QToolButton{{background:{C.BG3};color:{C.TEXT_MUT};border:none;border-radius:2px;"
                f"font-size:{dp(9)}px;}}"
                f"QToolButton:checked{{color:rgb{col};}} "
                f"QToolButton:!checked{{color:{C.BG0};}}")
            eye.toggled.connect(lambda checked, c=ch: self._toggle_channel(c, checked))
            rl.addWidget(eye)
            # Thumbnail
            thumb_lbl = QLabel()
            thumb_lbl.setFixedSize(dp(48), dp(36))
            thumb_lbl.setStyleSheet(f"background:{C.BG0};border:1px solid {C.BORDER};border-radius:2px;")
            rl.addWidget(thumb_lbl)
            # Name + color swatch
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(f"color:rgb{col};font-size:{dp(11)}px;font-weight:bold;")
            rl.addWidget(name_lbl)
            rl.addStretch()
            layout.addWidget(row)
            self.rows[ch] = (thumb_lbl, eye, row)

        layout.addStretch()
        self.refresh()

    def _toggle_channel(self, ch, visible):
        if not visible: self._hidden.add(ch)
        else:           self._hidden.discard(ch)
        self.editor.canvas.update()

    def channel_hidden(self, ch):
        return ch in self._hidden

    def refresh(self):
        """Update channel thumbnails from the active composite."""
        comp = self.editor.get_composite()
        if comp is None: return
        tw, th = dp(48), dp(36)
        try:
            r, g, b, a = comp.split()
            parts = {"R": r, "G": g, "B": b, "A": a}
            for ch, (thumb_lbl, eye, row) in self.rows.items():
                ch_img = parts[ch].convert("RGB")  # grayscale displayed as gray
                ch_img.thumbnail((tw, th), Image.LANCZOS)
                bg = Image.new("RGB", (tw, th), (30, 30, 30))
                ox = (tw - ch_img.width) // 2; oy = (th - ch_img.height) // 2
                bg.paste(ch_img, (ox, oy))
                px = pil_to_qpixmap(bg.convert("RGBA"))
                thumb_lbl.setPixmap(px)
        except Exception:
            pass


# ── PathsPanel ────────────────────────────────────────────────────────────────
class PathsPanel(QWidget):
    """Lists saved pen paths with actions: delete, stroke, fill, selection."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(dp(6), dp(8), dp(6), dp(8))
        layout.setSpacing(dp(5))

        hdr = QLabel("Paths")
        hdr.setStyleSheet(f"color:{C.TEXT_PRI};font-size:{dp(12)}px;font-weight:bold;")
        layout.addWidget(hdr)

        self.path_list = QListWidget()
        self.path_list.setStyleSheet(
            f"QListWidget{{background:{C.BG0};border:1px solid {C.BORDER};border-radius:3px;}}"
            f"QListWidget::item{{padding:{dp(5)}px {dp(8)}px;color:{C.TEXT_SEC};}}"
            f"QListWidget::item:selected{{background:{C.ACCENT_D};color:{C.ACCENT};}}")
        layout.addWidget(self.path_list, 1)

        def _btn(text, tip, cb):
            b = QPushButton(text); b.setToolTip(tip)
            b.setFixedHeight(dp(26))
            b.setStyleSheet(
                f"QPushButton{{background:{C.BG2};color:{C.TEXT_SEC};border:1px solid {C.BORDER};"
                f"border-radius:3px;padding:0 8px;font-size:{dp(10)}px;}}"
                f"QPushButton:hover{{border-color:{C.ACCENT};color:{C.ACCENT};}}")
            b.clicked.connect(cb); return b

        btn_row = QHBoxLayout(); btn_row.setSpacing(dp(4))
        btn_row.addWidget(_btn("Save Path",   "Save current pen path", self.save_path))
        btn_row.addWidget(_btn("To Selection","Convert path to selection", self.path_to_selection))
        layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout(); btn_row2.setSpacing(dp(4))
        btn_row2.addWidget(_btn("Stroke Path","Stroke path on active layer", self.stroke_path))
        btn_row2.addWidget(_btn("Fill Path",  "Fill path on active layer",   self.fill_path))
        btn_row2.addWidget(_btn("Delete",     "Delete selected path",        self.delete_path))
        layout.addLayout(btn_row2)

    def refresh(self):
        self.path_list.clear()
        for i, p in enumerate(self.editor.saved_paths):
            self.path_list.addItem(f"Path {i+1}  ({len(p.get('points',[]))} pts)")

    def save_path(self):
        """Save the current pen lasso points as a named path."""
        pts = getattr(self.editor.canvas, '_lasso_points', [])
        if not pts:
            self.editor._status("No path to save (draw with Lasso or Pen first)")
            return
        points = [(int(p.x()), int(p.y())) for p in pts]
        self.editor.saved_paths.append({"points": points})
        self.refresh()
        self.editor._status(f"Path saved ({len(points)} points)")

    def _selected_path(self):
        row = self.path_list.currentRow()
        if 0 <= row < len(self.editor.saved_paths):
            return self.editor.saved_paths[row]
        return None

    def path_to_selection(self):
        path = self._selected_path()
        if not path: return
        layer = self.editor.active_layer()
        if not layer: return
        w, h = layer.image.size
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).polygon(path["points"], fill=255)
        self.editor.canvas.set_selection_mask(mask)
        self.editor._status("Path loaded as selection")

    def stroke_path(self):
        path = self._selected_path()
        if not path: return
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        self.editor.history.save_state(
            self.editor.layers, self.editor.active_layer_index, "Stroke Path")
        c = self.editor.fg_color
        color = (c.red(), c.green(), c.blue(), self.editor.brush_opacity)
        sw = max(1, self.editor.brush_size)
        draw = ImageDraw.Draw(layer.image)
        pts = path["points"]
        for i in range(len(pts)):
            x1,y1 = pts[i]; x2,y2 = pts[(i+1) % len(pts)]
            draw.line([(x1,y1),(x2,y2)], fill=color, width=sw)
        self.editor.canvas.update()
        self.editor._status("Path stroked")

    def fill_path(self):
        path = self._selected_path()
        if not path: return
        layer = self.editor.active_layer()
        if not layer or layer.locked: return
        self.editor.history.save_state(
            self.editor.layers, self.editor.active_layer_index, "Fill Path")
        c = self.editor.fg_color
        color = (c.red(), c.green(), c.blue(), self.editor.brush_opacity)
        draw = ImageDraw.Draw(layer.image)
        draw.polygon(path["points"], fill=color)
        self.editor.canvas.update()
        self.editor._status("Path filled")

    def delete_path(self):
        row = self.path_list.currentRow()
        if 0 <= row < len(self.editor.saved_paths):
            del self.editor.saved_paths[row]
            self.refresh()


# ── PropertiesPanel ───────────────────────────────────────────────────────────
class PropertiesPanel(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self); layout.setContentsMargins(dp(8), dp(8), dp(8), dp(8)); layout.setSpacing(dp(6))

        # Brush group
        bg = QGroupBox("Brush"); bl = QFormLayout(bg)
        self.size_spin = QSpinBox(); self.size_spin.setRange(1, 500); self.size_spin.setValue(10)
        self.size_spin.valueChanged.connect(lambda v: setattr(editor, "brush_size", v))
        bl.addRow("Size:", self.size_spin)
        self.opacity_spin = QSpinBox(); self.opacity_spin.setRange(0, 100); self.opacity_spin.setValue(100)
        self.opacity_spin.setSuffix("%")
        self.opacity_spin.valueChanged.connect(lambda v: setattr(editor, "brush_opacity", int(v * 255 / 100)))
        bl.addRow("Opacity:", self.opacity_spin)
        self.hardness_spin = QSpinBox(); self.hardness_spin.setRange(0, 100); self.hardness_spin.setValue(100)
        self.hardness_spin.setSuffix("%")
        self.hardness_spin.valueChanged.connect(lambda v: setattr(editor, "brush_hardness", v))
        bl.addRow("Hardness:", self.hardness_spin)
        layout.addWidget(bg)

        # Shape group
        sg = QGroupBox("Shape"); sl = QFormLayout(sg)
        self.stroke_spin = QSpinBox(); self.stroke_spin.setRange(1, 50); self.stroke_spin.setValue(2)
        self.stroke_spin.valueChanged.connect(lambda v: setattr(editor, "shape_stroke_width", v))
        sl.addRow("Stroke:", self.stroke_spin)
        self.filled_chk = QCheckBox("Filled")
        self.filled_chk.toggled.connect(lambda v: setattr(editor, "shape_filled", v))
        sl.addRow("", self.filled_chk)
        self.sides_spin = QSpinBox(); self.sides_spin.setRange(3, 20); self.sides_spin.setValue(5)
        self.sides_spin.valueChanged.connect(lambda v: setattr(editor, "polygon_sides", v))
        sl.addRow("Sides:", self.sides_spin)
        layout.addWidget(sg)

        # Selection group
        selg = QGroupBox("Selection"); sell = QFormLayout(selg)
        self.tol_spin = QSpinBox(); self.tol_spin.setRange(0, 255); self.tol_spin.setValue(32)
        self.tol_spin.valueChanged.connect(lambda v: setattr(editor, "magic_wand_tolerance", v))
        sell.addRow("Tolerance:", self.tol_spin)
        self.contig_chk = QCheckBox("Contiguous"); self.contig_chk.setChecked(True)
        self.contig_chk.toggled.connect(lambda v: setattr(editor, "magic_wand_contiguous", v))
        sell.addRow("", self.contig_chk)
        self.sample_chk = QCheckBox("Sample All Layers")
        self.sample_chk.toggled.connect(lambda v: setattr(editor, "magic_wand_sample_all", v))
        sell.addRow("", self.sample_chk)
        layout.addWidget(selg)

        # Gradient/Pattern group
        gg = QGroupBox("Fill / Gradient"); gl = QFormLayout(gg)
        self.grad_combo = QComboBox(); self.grad_combo.addItems(["linear", "radial"])
        self.grad_combo.currentTextChanged.connect(lambda v: setattr(editor, "gradient_type", v))
        gl.addRow("Gradient:", self.grad_combo)
        self.pat_combo = QComboBox(); self.pat_combo.addItems(["checkerboard", "stripes", "dots", "grid"])
        self.pat_combo.currentTextChanged.connect(lambda v: setattr(editor, "pattern_type", v))
        gl.addRow("Pattern:", self.pat_combo)
        self.pat_scale = QSpinBox(); self.pat_scale.setRange(4, 128); self.pat_scale.setValue(16)
        self.pat_scale.valueChanged.connect(lambda v: setattr(editor, "pattern_scale", v))
        gl.addRow("Scale:", self.pat_scale)
        layout.addWidget(gg)

        # Retouch group
        rg = QGroupBox("Retouch"); rl = QFormLayout(rg)
        self.exp_spin = QSpinBox(); self.exp_spin.setRange(1, 100); self.exp_spin.setValue(50)
        self.exp_spin.setSuffix("%")
        self.exp_spin.valueChanged.connect(lambda v: setattr(editor, "retouch_exposure", v))
        rl.addRow("Exposure:", self.exp_spin)
        layout.addWidget(rg)
        layout.addStretch()

# ── AlignPanel ────────────────────────────────────────────────────────────────
class AlignPanel(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self); layout.setContentsMargins(dp(8), dp(10), dp(8), dp(8)); layout.setSpacing(dp(10))

        hdr = QLabel("Align Layer")
        hdr.setStyleSheet(f"color:{C.TEXT_SEC}; font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.8px;")
        layout.addWidget(hdr)

        grid = QGridLayout(); grid.setSpacing(dp(4))
        btns = [
            ("al-left",     "Align Left",       "left",    0, 0),
            ("al-center-h", "Align Center H",   "centerH", 0, 1),
            ("al-right",    "Align Right",       "right",   0, 2),
            ("al-top",      "Align Top",         "top",     1, 0),
            ("al-center-v", "Align Center V",   "centerV", 1, 1),
            ("al-bottom",   "Align Bottom",      "bottom",  1, 2),
        ]
        for key, tip, action, row, col in btns:
            b = QToolButton()
            b.setIcon(svg_icon(key, C.TEXT_SEC, dp(17)))
            b.setToolTip(tip)
            b.setFixedSize(dp(38), dp(38))
            b.clicked.connect(lambda checked=False, a=action: self._align(a))
            grid.addWidget(b, row, col)
        layout.addLayout(grid)
        layout.addStretch()

    def _align(self, action):
        layer = self.editor.active_layer()
        if not layer or not self.editor.layers: return
        w, h = self.editor.layers[0].image.size
        lw, lh = layer.image.size
        self.editor.history.save_state(self.editor.layers, self.editor.active_layer_index, f"Align {action}")
        ni = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if action == "left":     ox = 0;            oy = 0
        elif action == "centerH": ox = (w - lw) // 2; oy = 0
        elif action == "right":   ox = w - lw;      oy = 0
        elif action == "top":     ox = 0;            oy = 0
        elif action == "centerV": ox = 0;            oy = (h - lh) // 2
        elif action == "bottom":  ox = 0;            oy = h - lh
        else: return
        ni.paste(layer.image, (ox, oy))
        layer.image = ni; self.editor.canvas.update()

# ── ColorPanel ────────────────────────────────────────────────────────────────
class ColorPanel(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self); layout.setContentsMargins(dp(8), dp(8), dp(8), dp(8)); layout.setSpacing(dp(8))

        # FG/BG swatches
        self.swatch = ColorSwatchWidget()
        self.swatch.fg_changed.connect(editor.set_fg_color)
        self.swatch.bg_changed.connect(editor.set_bg_color)
        layout.addWidget(self.swatch)

        # HSL sliders
        hsl = QGroupBox("Color Picker")
        hsl_l = QFormLayout(hsl); hsl_l.setSpacing(dp(6))
        self.h_sl = QSlider(Qt.Horizontal); self.h_sl.setRange(0, 359)
        self.s_sl = QSlider(Qt.Horizontal); self.s_sl.setRange(0, 100)
        self.v_sl = QSlider(Qt.Horizontal); self.v_sl.setRange(0, 100)
        hsl_l.addRow("H:", self.h_sl); hsl_l.addRow("S:", self.s_sl); hsl_l.addRow("V:", self.v_sl)
        for sl in (self.h_sl, self.s_sl, self.v_sl):
            sl.valueChanged.connect(self._on_hsv_change)
        layout.addWidget(hsl)

        # Hex input
        hr = QHBoxLayout()
        hr.addWidget(QLabel("#"))
        self.hex_edit = QLineEdit(); self.hex_edit.setMaximumWidth(dp(80))
        self.hex_edit.returnPressed.connect(self._on_hex_change)
        hr.addWidget(self.hex_edit); hr.addStretch()
        layout.addLayout(hr)

        # Swatches row
        sw_row = QHBoxLayout(); sw_row.setSpacing(dp(3))
        presets = ["#ff6b8a", "#fbbf24", "#4ade80", "#6c8cff", "#a78bfa",
                   "#f9a8d4", "#ffffff", "#aaaaaa", "#555555", "#000000"]
        for pc in presets:
            b = QPushButton(); b.setFixedSize(dp(20), dp(20))
            b.setStyleSheet(f"background:{pc};border:1px solid {C.BORDER};border-radius:3px;")
            b.clicked.connect(lambda checked=False, c=pc: self._pick_preset(c))
            sw_row.addWidget(b)
        layout.addLayout(sw_row)
        layout.addStretch()

    def _pick_preset(self, hex_c):
        c = QColor(hex_c)
        self.editor.set_fg_color(c)
        self.swatch.set_fg(c)
        self._update_from_color(c)

    def _on_hsv_change(self):
        c = QColor.fromHsv(self.h_sl.value(), int(self.s_sl.value() * 2.55),
                           int(self.v_sl.value() * 2.55))
        self.hex_edit.setText(c.name()[1:])
        self.editor.set_fg_color(c)
        self.swatch.set_fg(c)

    def _on_hex_change(self):
        txt = self.hex_edit.text().strip().lstrip("#")
        if len(txt) == 6:
            c = QColor(f"#{txt}")
            if c.isValid():
                self._update_from_color(c)
                self.editor.set_fg_color(c)
                self.swatch.set_fg(c)

    def _update_from_color(self, c):
        self.h_sl.blockSignals(True); self.s_sl.blockSignals(True); self.v_sl.blockSignals(True)
        self.h_sl.setValue(c.hsvHue() if c.hsvHue() >= 0 else 0)
        self.s_sl.setValue(c.hsvSaturation() * 100 // 255)
        self.v_sl.setValue(c.value() * 100 // 255)
        self.hex_edit.setText(c.name()[1:])
        self.h_sl.blockSignals(False); self.s_sl.blockSignals(False); self.v_sl.blockSignals(False)

    def sync_fg(self, c):
        self.swatch.set_fg(c); self._update_from_color(c)

# ── HistoryPanel ──────────────────────────────────────────────────────────────
class HistoryPanel(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.list)

    def refresh(self):
        self.list.clear()
        # Current state always first
        cur = QListWidgetItem("  ▶  Current")
        cur.setForeground(QColor(C.ACCENT))
        f = cur.font(); f.setBold(True); cur.setFont(f)
        self.list.addItem(cur)
        labels = self.editor.history.all_labels()
        for lbl in reversed(labels):
            item = QListWidgetItem(f"    {lbl}")
            item.setForeground(QColor(C.TEXT_SEC))
            self.list.addItem(item)
        self.list.scrollToTop()

# ── OptionsBar ────────────────────────────────────────────────────────────────
class OptionsBar(QWidget):
    """Context-sensitive tool options bar below the menu."""
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setFixedHeight(dp(38))
        self.setStyleSheet(
            f"background:{C.BG1}; border-bottom:1px solid {C.BORDER};"
            f"border-top:1px solid {C.BORDER};"
        )
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(dp(8), dp(4), dp(8), dp(4))
        self._layout.setSpacing(dp(6))
        self._widgets = {}
        # Tool name label (left side)
        self._tool_lbl = QLabel("Brush")
        self._tool_lbl.setFixedWidth(dp(84))
        self._tool_lbl.setStyleSheet(
            f"color:{C.ACCENT}; font-size:{dp(11)}px; font-weight:600;"
            f"border-right:1px solid {C.BORDER}; padding-right:{dp(8)}px;"
            f"background:{C.BG1};"
        )
        self._layout.addWidget(self._tool_lbl)
        self._build()
        self.update_for_tool("brush")

    def _lbl(self, text):
        l = QLabel(text)
        l.setStyleSheet(f"color:{C.TEXT_SEC}; font-size:{dp(11)}px; background:transparent;")
        return l

    def _build(self):
        ly = self._layout
        def sp(w=None, h=None):
            s = QSpinBox(); s.setFixedHeight(dp(26))
            s.setStyleSheet(f"QSpinBox{{background:{C.BG0}; border:1px solid {C.BORDER}; border-radius:3px; padding:2px 4px; min-height:{dp(22)}px;}}"
                            f"QSpinBox:focus{{border-color:{C.ACCENT};}}")
            if w: s.setFixedWidth(w)
            return s

        # Size
        self._widgets["size_lbl"] = self._lbl("Size:")
        ly.addWidget(self._widgets["size_lbl"])
        self._widgets["size"] = sp(dp(60)); self._widgets["size"].setRange(1, 500)
        self._widgets["size"].setValue(10)
        self._widgets["size"].valueChanged.connect(lambda v: setattr(self.editor, "brush_size", v))
        ly.addWidget(self._widgets["size"])

        # Opacity
        self._widgets["op_lbl"] = self._lbl("Opacity:")
        ly.addWidget(self._widgets["op_lbl"])
        self._widgets["opacity"] = sp(dp(60)); self._widgets["opacity"].setRange(0, 100)
        self._widgets["opacity"].setValue(100); self._widgets["opacity"].setSuffix("%")
        self._widgets["opacity"].valueChanged.connect(lambda v: setattr(self.editor, "brush_opacity", int(v * 255 / 100)))
        ly.addWidget(self._widgets["opacity"])

        # Off-canvas painting toggle
        self._widgets["offcanvas"] = QCheckBox("Off-Canvas")
        self._widgets["offcanvas"].setChecked(False)
        self._widgets["offcanvas"].setToolTip("Expand canvas when brush strokes go beyond image edges")
        self._widgets["offcanvas"].toggled.connect(lambda v: setattr(self.editor, "off_canvas_paint", v))
        ly.addWidget(self._widgets["offcanvas"])

        self._widgets["sep_tol"] = QFrame(); self._widgets["sep_tol"].setFrameShape(QFrame.VLine)
        self._widgets["sep_tol"].setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(self._widgets["sep_tol"])

        # Tolerance
        self._widgets["tol_lbl"] = self._lbl("Tolerance:")
        ly.addWidget(self._widgets["tol_lbl"])
        self._widgets["tolerance"] = sp(dp(60)); self._widgets["tolerance"].setRange(0, 255)
        self._widgets["tolerance"].setValue(32)
        self._widgets["tolerance"].valueChanged.connect(lambda v: setattr(self.editor, "magic_wand_tolerance", v))
        ly.addWidget(self._widgets["tolerance"])
        self._widgets["contig"] = QCheckBox("Contiguous"); self._widgets["contig"].setChecked(True)
        self._widgets["contig"].toggled.connect(lambda v: setattr(self.editor, "magic_wand_contiguous", v))
        ly.addWidget(self._widgets["contig"])

        # ── Selection mode (New / Add / Subtract / Intersect) ─────────────
        sep_sm = QFrame(); sep_sm.setFrameShape(QFrame.VLine)
        sep_sm.setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(sep_sm); self._widgets["sep_selmode"] = sep_sm
        self._widgets["selmode_lbl"] = self._lbl("Mode:")
        ly.addWidget(self._widgets["selmode_lbl"])
        self._selmode_btns = {}
        for _mid, _mlbl in [("new","N"),("add","+"),("subtract","−"),("intersect","×")]:
            _b = QToolButton(); _b.setText(_mlbl); _b.setCheckable(True)
            _b.setFixedSize(dp(22), dp(22))
            _b.setToolTip({"new":"New","add":"Add (Shift)","subtract":"Subtract (Alt)","intersect":"Intersect"}[_mid])
            _b.setStyleSheet(
                f"QToolButton{{background:{C.BG2};color:{C.TEXT_SEC};border:1px solid {C.BORDER};"
                f"border-radius:3px;font-size:{dp(10)}px;font-weight:bold;}}"
                f"QToolButton:checked{{background:{C.ACCENT_D};color:{C.ACCENT};border-color:{C.ACCENT};}}"
                f"QToolButton:hover{{border-color:{C.ACCENT};}}")
            _b.clicked.connect(lambda checked, m=_mid: self._set_sel_mode(m))
            ly.addWidget(_b)
            self._selmode_btns[_mid] = _b
            self._widgets[f"selmode_{_mid}"] = _b
        self._selmode_btns["new"].setChecked(True)

        # ── Feather ────────────────────────────────────────────────────────
        self._widgets["feather_lbl"] = self._lbl("Feather:")
        ly.addWidget(self._widgets["feather_lbl"])
        self._widgets["sel_feather"] = sp(dp(52))
        self._widgets["sel_feather"].setRange(0, 200)
        self._widgets["sel_feather"].setValue(0)
        self._widgets["sel_feather"].setSuffix("px")
        self._widgets["sel_feather"].valueChanged.connect(lambda v: setattr(self.editor, "sel_feather", v))
        ly.addWidget(self._widgets["sel_feather"])
        self._widgets["anti_alias"] = QCheckBox("AA")
        self._widgets["anti_alias"].setChecked(True)
        self._widgets["anti_alias"].setToolTip("Anti-alias")
        self._widgets["anti_alias"].toggled.connect(lambda v: setattr(self.editor, "sel_anti_alias", v))
        ly.addWidget(self._widgets["anti_alias"])

        # ── Magnetic scissors sensitivity ──────────────────────────────────
        self._widgets["mag_lbl"] = self._lbl("Edge:")
        ly.addWidget(self._widgets["mag_lbl"])
        self._widgets["mag_sens"] = sp(dp(52))
        self._widgets["mag_sens"].setRange(1, 100)
        self._widgets["mag_sens"].setValue(60)
        self._widgets["mag_sens"].setSuffix("%")
        self._widgets["mag_sens"].valueChanged.connect(
            lambda v: setattr(self.editor, "mag_edge_sensitivity", v))
        ly.addWidget(self._widgets["mag_sens"])

        # Shape options
        self._widgets["sep_shape"] = QFrame(); self._widgets["sep_shape"].setFrameShape(QFrame.VLine)
        self._widgets["sep_shape"].setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(self._widgets["sep_shape"])
        self._widgets["stroke_lbl"] = self._lbl("Stroke:")
        ly.addWidget(self._widgets["stroke_lbl"])
        self._widgets["stroke"] = sp(dp(50)); self._widgets["stroke"].setRange(1, 50)
        self._widgets["stroke"].setValue(2)
        self._widgets["stroke"].valueChanged.connect(lambda v: setattr(self.editor, "shape_stroke_width", v))
        ly.addWidget(self._widgets["stroke"])
        self._widgets["filled"] = QCheckBox("Filled")
        self._widgets["filled"].toggled.connect(lambda v: setattr(self.editor, "shape_filled", v))
        ly.addWidget(self._widgets["filled"])
        self._widgets["sides_lbl"] = self._lbl("Sides:")
        ly.addWidget(self._widgets["sides_lbl"])
        self._widgets["sides"] = sp(dp(50)); self._widgets["sides"].setRange(3, 20)
        self._widgets["sides"].setValue(5)
        self._widgets["sides"].valueChanged.connect(lambda v: setattr(self.editor, "polygon_sides", v))
        ly.addWidget(self._widgets["sides"])

        # Gradient type
        self._widgets["sep_grad"] = QFrame(); self._widgets["sep_grad"].setFrameShape(QFrame.VLine)
        self._widgets["sep_grad"].setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(self._widgets["sep_grad"])
        self._widgets["grad_lbl"] = self._lbl("Type:")
        ly.addWidget(self._widgets["grad_lbl"])
        self._widgets["grad_type"] = QComboBox()
        self._widgets["grad_type"].addItems(["linear", "radial", "angle", "reflected", "diamond"])
        self._widgets["grad_type"].setFixedSize(dp(90), dp(24))
        self._widgets["grad_type"].currentTextChanged.connect(lambda v: setattr(self.editor, "gradient_type", v))
        ly.addWidget(self._widgets["grad_type"])

        # Exposure (retouch)
        self._widgets["sep_exp"] = QFrame(); self._widgets["sep_exp"].setFrameShape(QFrame.VLine)
        self._widgets["sep_exp"].setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(self._widgets["sep_exp"])
        self._widgets["exp_lbl"] = self._lbl("Exposure:")
        ly.addWidget(self._widgets["exp_lbl"])
        self._widgets["exposure"] = sp(dp(60)); self._widgets["exposure"].setRange(1, 100)
        self._widgets["exposure"].setValue(50); self._widgets["exposure"].setSuffix("%")
        self._widgets["exposure"].valueChanged.connect(lambda v: setattr(self.editor, "retouch_exposure", v))
        ly.addWidget(self._widgets["exposure"])

        # ── Star tool: inner ratio + points ──
        sep5 = QFrame(); sep5.setFrameShape(QFrame.VLine)
        sep5.setStyleSheet(f"color:{C.BORDER};"); ly.addWidget(sep5)
        self._widgets["star_sep"] = sep5
        self._widgets["points_lbl"] = self._lbl("Points:")
        ly.addWidget(self._widgets["points_lbl"])
        self._widgets["star_points"] = sp(dp(55)); self._widgets["star_points"].setRange(3, 20)
        self._widgets["star_points"].setValue(5)
        self._widgets["star_points"].valueChanged.connect(lambda v: setattr(self.editor, "star_points", v))
        ly.addWidget(self._widgets["star_points"])
        self._widgets["inner_lbl"] = self._lbl("Inner%:")
        ly.addWidget(self._widgets["inner_lbl"])
        self._widgets["inner_ratio"] = sp(dp(55)); self._widgets["inner_ratio"].setRange(10, 90)
        self._widgets["inner_ratio"].setValue(40)
        self._widgets["inner_ratio"].valueChanged.connect(lambda v: setattr(self.editor, "star_inner_ratio", v))
        ly.addWidget(self._widgets["inner_ratio"])

        # ── Crop: aspect ratio lock ──
        sep6 = QFrame(); sep6.setFrameShape(QFrame.VLine)
        sep6.setStyleSheet(f"color:{C.BORDER};"); ly.addWidget(sep6)
        self._widgets["crop_sep"] = sep6
        self._widgets["ratio_lbl"] = self._lbl("Ratio:")
        ly.addWidget(self._widgets["ratio_lbl"])
        self._widgets["crop_ratio"] = QComboBox()
        self._widgets["crop_ratio"].addItems(["Free", "Square (1:1)", "4:3", "3:2", "16:9", "16:10", "2:1", "Custom"])
        self._widgets["crop_ratio"].setFixedSize(dp(120), dp(24))
        self._widgets["crop_ratio"].currentTextChanged.connect(lambda v: setattr(self.editor, "crop_ratio", v))
        ly.addWidget(self._widgets["crop_ratio"])

        # ── Text tool options ──
        sep7 = QFrame(); sep7.setFrameShape(QFrame.VLine)
        sep7.setStyleSheet(f"color:{C.BORDER};"); ly.addWidget(sep7)
        self._widgets["text_sep"] = sep7
        self._widgets["font_lbl"] = self._lbl("Font:")
        ly.addWidget(self._widgets["font_lbl"])
        self._widgets["font_family"] = QComboBox()
        from PyQt5.QtGui import QFontDatabase
        fdb = QFontDatabase()
        for fam in sorted(fdb.families())[:50]:   # top 50 to keep menu short
            self._widgets["font_family"].addItem(fam)
        for common in ["Arial", "Segoe UI", "Verdana", "Times New Roman", "Courier New", "Impact"]:
            if self._widgets["font_family"].findText(common) < 0:
                self._widgets["font_family"].insertItem(0, common)
        self._widgets["font_family"].setFixedSize(dp(140), dp(24))
        self._widgets["font_family"].currentTextChanged.connect(lambda v: setattr(self.editor, "text_font_family", v))
        ly.addWidget(self._widgets["font_family"])
        self._widgets["tsize_lbl"] = self._lbl("Size:")
        ly.addWidget(self._widgets["tsize_lbl"])
        self._widgets["text_size"] = sp(dp(55)); self._widgets["text_size"].setRange(4, 500)
        self._widgets["text_size"].setValue(36)
        self._widgets["text_size"].valueChanged.connect(lambda v: setattr(self.editor, "text_size", v))
        ly.addWidget(self._widgets["text_size"])
        self._widgets["text_bold"] = QCheckBox("Bold")
        self._widgets["text_bold"].toggled.connect(lambda v: setattr(self.editor, "text_bold", v))
        ly.addWidget(self._widgets["text_bold"])
        self._widgets["text_italic"] = QCheckBox("Italic")
        self._widgets["text_italic"].toggled.connect(lambda v: setattr(self.editor, "text_italic", v))
        ly.addWidget(self._widgets["text_italic"])

        # ── Pen tool: flow ──
        sep8 = QFrame(); sep8.setFrameShape(QFrame.VLine)
        sep8.setStyleSheet(f"color:{C.BORDER};"); ly.addWidget(sep8)
        self._widgets["pen_sep"] = sep8
        self._widgets["flow_lbl"] = self._lbl("Flow:")
        ly.addWidget(self._widgets["flow_lbl"])
        self._widgets["pen_flow"] = sp(dp(55)); self._widgets["pen_flow"].setRange(1, 100)
        self._widgets["pen_flow"].setValue(100); self._widgets["pen_flow"].setSuffix("%")
        self._widgets["pen_flow"].valueChanged.connect(lambda v: setattr(self.editor, "pen_flow", v))
        ly.addWidget(self._widgets["pen_flow"])
        self._widgets["smooth_lbl"] = self._lbl("Smooth:")
        ly.addWidget(self._widgets["smooth_lbl"])
        self._widgets["pen_smooth"] = sp(dp(55)); self._widgets["pen_smooth"].setRange(0, 10)
        self._widgets["pen_smooth"].setValue(3)
        self._widgets["pen_smooth"].valueChanged.connect(lambda v: setattr(self.editor, "pen_smooth", v))
        ly.addWidget(self._widgets["pen_smooth"])

        # ── Transform tool controls ────────────────────────────────────
        sep_xform = QFrame(); sep_xform.setFrameShape(QFrame.VLine)
        sep_xform.setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(sep_xform); self._widgets["sep_xform"] = sep_xform

        xform_commit = QPushButton("Apply")
        xform_commit.setFixedHeight(dp(26))
        xform_commit.setStyleSheet(
            f"QPushButton{{background:{C.ACCENT};color:{C.BG0};border:none;"
            f"border-radius:4px;padding:0 10px;font-weight:bold;font-size:{dp(11)}px;}}"
            f"QPushButton:hover{{background:#a6d3f5;}}")
        xform_commit.clicked.connect(self._commit_xform)
        ly.addWidget(xform_commit); self._widgets["xform_commit"] = xform_commit

        xform_cancel = QPushButton("Cancel")
        xform_cancel.setFixedHeight(dp(26))
        xform_cancel.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};"
            f"border-radius:4px;padding:0 10px;font-size:{dp(11)}px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}")
        xform_cancel.clicked.connect(self._cancel_xform)
        ly.addWidget(xform_cancel); self._widgets["xform_cancel"] = xform_cancel

        xform_flip_h = QPushButton("Flip H")
        xform_flip_h.setFixedHeight(dp(26))
        xform_flip_h.setToolTip("Flip horizontally")
        xform_flip_h.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};"
            f"border-radius:4px;padding:0 8px;font-size:{dp(11)}px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}")
        xform_flip_h.clicked.connect(self._xform_flip_h)
        ly.addWidget(xform_flip_h); self._widgets["xform_flip_h"] = xform_flip_h

        xform_flip_v = QPushButton("Flip V")
        xform_flip_v.setFixedHeight(dp(26))
        xform_flip_v.setToolTip("Flip vertically")
        xform_flip_v.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};"
            f"border-radius:4px;padding:0 8px;font-size:{dp(11)}px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}")
        xform_flip_v.clicked.connect(self._xform_flip_v)
        ly.addWidget(xform_flip_v); self._widgets["xform_flip_v"] = xform_flip_v

        # ── Perspective transform confirm/cancel ───────────────────────────
        persp_commit = QPushButton("Apply")
        persp_commit.setFixedHeight(dp(26))
        persp_commit.setStyleSheet(
            f"QPushButton{{background:{C.ACCENT};color:{C.BG0};border:none;"
            f"border-radius:4px;padding:0 10px;font-weight:bold;font-size:{dp(11)}px;}}"
            f"QPushButton:hover{{background:#a6d3f5;}}")
        persp_commit.clicked.connect(self._commit_persp)
        ly.addWidget(persp_commit); self._widgets["persp_commit"] = persp_commit

        persp_cancel = QPushButton("Cancel")
        persp_cancel.setFixedHeight(dp(26))
        persp_cancel.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};"
            f"border-radius:4px;padding:0 10px;font-size:{dp(11)}px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}")
        persp_cancel.clicked.connect(self._cancel_persp)
        ly.addWidget(persp_cancel); self._widgets["persp_cancel"] = persp_cancel

        # ── Warp transform controls ────────────────────────────────────────
        sep_warp = QFrame(); sep_warp.setFrameShape(QFrame.VLine)
        sep_warp.setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(sep_warp); self._widgets["sep_warp"] = sep_warp

        self._widgets["warp_mode_lbl"] = self._lbl("Mode:")
        ly.addWidget(self._widgets["warp_mode_lbl"])
        self._widgets["warp_mode"] = QComboBox()
        self._widgets["warp_mode"].addItems(["move", "grow", "shrink", "swirl"])
        self._widgets["warp_mode"].setFixedSize(dp(80), dp(26))
        self._widgets["warp_mode"].currentTextChanged.connect(
            lambda v: setattr(self.editor, "warp_mode", v))
        ly.addWidget(self._widgets["warp_mode"])

        self._widgets["warp_str_lbl"] = self._lbl("Strength:")
        ly.addWidget(self._widgets["warp_str_lbl"])
        self._widgets["warp_strength"] = sp(dp(55))
        self._widgets["warp_strength"].setRange(1, 100)
        self._widgets["warp_strength"].setValue(60)
        self._widgets["warp_strength"].setSuffix("%")
        self._widgets["warp_strength"].valueChanged.connect(
            lambda v: setattr(self.editor, "warp_strength", v))
        ly.addWidget(self._widgets["warp_strength"])

        warp_reset = QPushButton("Reset")
        warp_reset.setFixedHeight(dp(26))
        warp_reset.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};"
            f"border-radius:4px;padding:0 8px;font-size:{dp(11)}px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}")
        warp_reset.clicked.connect(self._warp_reset)
        ly.addWidget(warp_reset); self._widgets["warp_reset"] = warp_reset

        # ── Blur / Sharpen controls ────────────────────────────────────────
        sep_bs = QFrame(); sep_bs.setFrameShape(QFrame.VLine)
        sep_bs.setStyleSheet(f"color:{C.BORDER}; margin:4px 2px;")
        ly.addWidget(sep_bs); self._widgets["sep_bs"] = sep_bs

        self._widgets["bs_mode_lbl"] = self._lbl("Mode:")
        ly.addWidget(self._widgets["bs_mode_lbl"])
        self._widgets["bs_mode"] = QComboBox()
        self._widgets["bs_mode"].addItems(["blur", "sharpen"])
        self._widgets["bs_mode"].setFixedSize(dp(80), dp(26))
        self._widgets["bs_mode"].currentTextChanged.connect(
            lambda v: setattr(self.editor, "blur_sharpen_mode", v))
        ly.addWidget(self._widgets["bs_mode"])

        self._widgets["bs_str_lbl"] = self._lbl("Strength:")
        ly.addWidget(self._widgets["bs_str_lbl"])
        self._widgets["bs_strength"] = sp(dp(55))
        self._widgets["bs_strength"].setRange(1, 100)
        self._widgets["bs_strength"].setValue(50)
        self._widgets["bs_strength"].setSuffix("%")
        self._widgets["bs_strength"].valueChanged.connect(
            lambda v: setattr(self.editor, "blur_sharpen_strength", v))
        ly.addWidget(self._widgets["bs_strength"])

        ly.addStretch()

        # Crop confirm/cancel (shown only for crop tool)
        sep_crop = QFrame(); sep_crop.setFrameShape(QFrame.VLine)
        sep_crop.setStyleSheet(f"color:{C.BORDER};"); ly.addWidget(sep_crop)
        self._widgets["sep_crop"] = sep_crop

        confirm_btn = QPushButton("Confirm Crop")
        confirm_btn.setFixedHeight(dp(24))
        confirm_btn.setStyleSheet(
            f"QPushButton{{background:{C.ACCENT};color:{C.BG0};border:none;"
            f"border-radius:4px;padding:0 10px;font-weight:bold;font-size:11px;}}"
            f"QPushButton:hover{{background:#a6d3f5;}}"
        )
        confirm_btn.clicked.connect(self._confirm_crop)
        ly.addWidget(confirm_btn)
        self._widgets["crop_confirm"] = confirm_btn

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(dp(24))
        cancel_btn.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};"
            f"border-radius:4px;padding:0 10px;font-size:11px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}"
        )
        cancel_btn.clicked.connect(self._cancel_crop)
        ly.addWidget(cancel_btn)
        self._widgets["crop_cancel"] = cancel_btn

        # Copy to clipboard quick button
        sep_clip = QFrame(); sep_clip.setFrameShape(QFrame.VLine)
        sep_clip.setStyleSheet(f"color:{C.BORDER};"); ly.addWidget(sep_clip)
        self._widgets["sep_clip"] = sep_clip

        clip_btn = QPushButton("Copy Image")
        clip_btn.setFixedHeight(dp(24))
        clip_btn.setToolTip("Copy flattened image to clipboard  (Ctrl+Shift+C)")
        clip_btn.setStyleSheet(
            f"QPushButton{{background:{C.BG2};color:{C.TEXT_PRI};border:1px solid {C.BORDER};"
            f"border-radius:4px;padding:0 10px;font-size:11px;}}"
            f"QPushButton:hover{{border-color:{C.ACCENT};}}"
        )
        clip_btn.clicked.connect(lambda: self.editor.copy_to_clipboard())
        ly.addWidget(clip_btn)
        self._widgets["clip_btn"] = clip_btn

    def _confirm_crop(self):
        self.editor.apply_crop()
        self.update_for_tool(self.editor.current_tool)

    def _cancel_crop(self):
        self.editor.canvas.crop_rect = None
        self.editor.canvas.drawing = False
        self.editor.canvas.update()
        self.editor._status("Crop cancelled")
        self.update_for_tool(self.editor.current_tool)

    def _commit_xform(self):
        self.editor.canvas.xform_commit()
        self.update_for_tool("transform")

    def _cancel_xform(self):
        self.editor.canvas.xform_cancel()
        self.update_for_tool("transform")

    def _xform_flip_h(self):
        self.editor.canvas.xform_flip_h()

    def _xform_flip_v(self):
        self.editor.canvas.xform_flip_v()

    def _commit_persp(self):
        self.editor.canvas.persp_commit()
        self.update_for_tool("perspective")

    def _cancel_persp(self):
        self.editor.canvas.persp_cancel()
        self.update_for_tool("perspective")

    def _set_sel_mode(self, mode):
        """Update selection mode and refresh button states."""
        self.editor.sel_mode = mode
        for mid, btn in self._selmode_btns.items():
            btn.setChecked(mid == mode)

    def _warp_reset(self):
        canvas = self.editor.canvas
        if canvas._warp_orig is not None:
            layer = self.editor.active_layer()
            if layer:
                layer.image = canvas._warp_orig.copy()
            canvas._warp_orig = None
            canvas.update()
            self.editor._status("Warp reset to original")

    def _show(self, *keys):
        for k, w in self._widgets.items():
            visible = any(k.startswith(pat) or k == pat for pat in keys)
            w.setVisible(visible)

    def update_for_tool(self, tool):
        # Update tool name label
        if hasattr(self, "_tool_lbl"):
            self._tool_lbl.setText(tool.replace("-", " ").replace("_", " ").title())

        # Each group includes the separator that PRECEDES it so seps only show
        # when their group is visible. sep_tol / sep_shape / sep_grad / sep_exp
        # are now stored in _widgets and therefore managed by _show().
        paint  = ("size_lbl", "size", "op_lbl", "opacity", "offcanvas")
        # tol group leads with sep_tol so separator only appears when group visible
        tol    = ("sep_tol", "tol_lbl", "tolerance", "contig",
                   "sep_selmode", "selmode_lbl",
                   "selmode_new", "selmode_add", "selmode_subtract", "selmode_intersect",
                   "feather_lbl", "sel_feather", "anti_alias")
        mag_tol = (*tol, "mag_lbl", "mag_sens")
        shape  = ("sep_shape", "stroke_lbl", "stroke", "filled", "sides_lbl", "sides")
        grad   = ("sep_grad", "grad_lbl", "grad_type")
        exp    = ("sep_exp", "exp_lbl", "exposure")
        star   = ("star_sep", "points_lbl", "star_points", "inner_lbl", "inner_ratio")
        crop_r = ("crop_sep", "ratio_lbl", "crop_ratio")
        text_w = ("text_sep", "font_lbl", "font_family", "tsize_lbl", "text_size",
                  "text_bold", "text_italic")
        pen_w  = ("pen_sep", "flow_lbl", "pen_flow", "smooth_lbl", "pen_smooth")

        if tool in ("brush", "pencil", "spray", "eraser"):
            self._show(*paint)
        elif tool in ("marquee-rect", "marquee-ellipse", "lasso"):
            self._show(*tol)
        elif tool in ("magic-wand", "select-color"):
            self._show(*tol)
        elif tool == "magnetic-lasso":
            self._show(*mag_tol)
        elif tool == "star":
            self._show(*paint, *shape, *star)
        elif tool in ("rect", "ellipse", "line", "arrow", "triangle", "polygon"):
            self._show(*paint, *shape)
        elif tool == "gradient":
            self._show(*paint, *grad)
        elif tool in ("dodge", "burn", "sponge", "smudge"):
            self._show(*paint, *exp)
        elif tool in ("clone", "healing"):
            self._show(*paint)
        elif tool == "crop":
            for w in self._widgets.values():
                w.setVisible(False)
            for k in ("sep_crop", "crop_confirm", "crop_cancel", *crop_r, "sep_clip", "clip_btn"):
                if k in self._widgets:
                    self._widgets[k].setVisible(True)
            return
        elif tool == "text":
            self._show(*text_w)
        elif tool == "pen":
            self._show(*paint, *pen_w)
        elif tool in ("move", "pan", "zoom", "eyedropper", "note", "measure", "fill", "pattern"):
            for w in self._widgets.values():
                w.setVisible(False)
            for k in ("sep_clip", "clip_btn"):
                if k in self._widgets:
                    self._widgets[k].setVisible(True)
            return
        elif tool == "transform":
            canvas = self.editor.canvas
            if getattr(canvas, "_xform_active", False):
                self._show("sep_xform", "xform_commit", "xform_cancel", "xform_flip_h", "xform_flip_v")
            else:
                for w in self._widgets.values():
                    w.setVisible(False)
                self.editor._status("Free Transform — click a layer to begin")
            return
        elif tool == "perspective":
            canvas = self.editor.canvas
            if getattr(canvas, "_persp_active", False):
                self._show("sep_xform", "persp_commit", "persp_cancel")
            else:
                for w in self._widgets.values():
                    w.setVisible(False)
                self.editor._status("Perspective — click canvas to place 4-corner grid")
            return
        elif tool == "warp":
            self._show(*paint, "sep_warp", "warp_mode_lbl", "warp_mode",
                       "warp_str_lbl", "warp_strength", "warp_reset")
        elif tool == "blur-sharpen":
            self._show(*paint, "sep_bs", "bs_mode_lbl", "bs_mode",
                       "bs_str_lbl", "bs_strength")
        else:
            for w in self._widgets.values():
                w.setVisible(False)

        # Always keep clip_btn visible, hide crop buttons
        for k in ("sep_crop", "crop_confirm", "crop_cancel"):
            if k in self._widgets:
                self._widgets[k].setVisible(False)
        for k in ("sep_clip", "clip_btn"):
            if k in self._widgets:
                self._widgets[k].setVisible(True)

# ── ImageEditor (main window) ─────────────────────────────────────────────────
class ImageEditor(QMainWindow):
    def __init__(self, pixmap=None, swiftshot_app=None):
        super().__init__()
        scale = get_ui_scale()
        scale_str = f" [{scale*100:.0f}% UI]" if abs(scale - 1.0) > 0.01 else ""
        self.setWindowTitle(f"SwiftShot Editor v2.6.5{scale_str}")
        self.setMinimumSize(dp(900), dp(600))
        self.swiftshot_app = swiftshot_app

        # State
        self.layers = []; self.active_layer_index = 0
        self.current_tool = "brush"
        self.fg_color = QColor(255, 255, 255)
        self.bg_color = QColor(0, 0, 0)
        self.brush_size = 10
        self.brush_opacity = 255
        self.magic_wand_tolerance = 32
        self.magic_wand_contiguous = True
        self.magic_wand_sample_all = False
        self.clone_source = None
        self.history = HistoryManager()
        self.file_path = None
        self.saved_path = None
        self.selected_layer_indices = set()  # multi-select
        self.saved_paths = []               # list of path dicts for Paths panel
        self._uploader = None
        self.retouch_exposure = 50
        self.shape_stroke_width = 2
        self.shape_filled = False
        self.polygon_sides = 5
        self.star_points = 5
        self.star_inner_ratio = 40
        self.gradient_type = "linear"
        self.pattern_type = "checkerboard"
        self.pattern_scale = 16
        self.crop_ratio = "Free"
        self.text_font_family = "Arial"
        self.text_size = 36
        self.text_bold = False
        self.text_italic = False
        self.pen_flow = 100
        self.pen_smooth = 3
        # Transform / Warp / Blur-Sharpen state
        self.warp_mode           = "move"   # move / grow / shrink / swirl
        self.warp_strength       = 60
        self.blur_sharpen_mode   = "blur"   # blur / sharpen
        self.blur_sharpen_strength = 50
        self.brush_hardness = 100
        # Selection state
        self.sel_mode            = "new"    # new / add / subtract / intersect
        self.sel_feather         = 0        # feather radius in px
        self.sel_anti_alias      = True
        self.quick_mask_active   = False
        # Magnetic Scissors state
        self.mag_edge_sensitivity = 60      # 0-100
        # Select by Color
        self.color_sel_contiguous = False   # False = global (Photoshop "select by color")
        # Off-canvas painting
        self.off_canvas_paint = False       # expand canvas when brush goes off edge

        self._load_recent_files()
        self.init_ui()

        if pixmap is not None and not pixmap.isNull():
            pil_img = qpixmap_to_pil(pixmap)
            self.layers = [Layer("Background", image=pil_img)]
            self.active_layer_index = 0
            self.update_layer_panel()
            self.canvas.fit_in_view()
            self.setWindowTitle(f"SwiftShot Editor — {pil_img.width}×{pil_img.height}")

        self.showMaximized()

    def active_layer(self):
        if 0 <= self.active_layer_index < len(self.layers):
            return self.layers[self.active_layer_index]
        return None

    # ── Config / Recent Files ─────────────────────────────────────────────────
    @staticmethod
    def _config_dir():
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        d = os.path.join(base, "SwiftShot")
        os.makedirs(d, exist_ok=True)
        return d

    def _load_recent_files(self):
        self._recent_files = []
        try:
            cfg = os.path.join(self._config_dir(), "recent.json")
            if os.path.exists(cfg):
                with open(cfg) as f:
                    data = json.load(f)
                self._recent_files = [p for p in data.get("recent", []) if os.path.exists(p)][:10]
        except Exception:
            pass

    def _save_recent_files(self):
        try:
            cfg = os.path.join(self._config_dir(), "recent.json")
            with open(cfg, "w") as f:
                json.dump({"recent": self._recent_files[:10]}, f, indent=2)
        except Exception:
            pass

    def _add_recent(self, path):
        path = os.path.abspath(path)
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:10]
        self._save_recent_files()
        self._rebuild_recent_menu()

    # ── UI Construction ───────────────────────────────────────────────────────
    def init_ui(self):
        self.setStyleSheet(build_ss())
        self.canvas = CanvasWidget(self)
        self.canvas.color_picked.connect(self.set_fg_color)
        self.canvas.status_update.connect(self._status)
        self.canvas.zoom_changed.connect(self._on_canvas_zoom_changed)
        self.setCentralWidget(self.canvas)
        self._create_menus()
        self._create_toolbar()
        self._create_options_bar()
        self._create_right_panel()
        self._setup_rulers()
        # Connect canvas to histogram refresh on update
        self.canvas.installEventFilter(self)
        # Fallback polling timer: refresh navigator/histogram every 2s if dirty
        self._panels_dirty = False
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poll_refresh_panels)
        self._poll_timer.start()
        self._status("Ready")

    def eventFilter(self, obj, event):
        """Intercept canvas resize/update to refresh panels."""
        from PyQt5.QtCore import QEvent
        if obj is self.canvas and event.type() == QEvent.Paint:
            self._panels_dirty = True
            QTimer.singleShot(600, self._refresh_panels_lazy)
        return super().eventFilter(obj, event)

    def _poll_refresh_panels(self):
        """Fallback: catch any missed paint events via dirty flag."""
        if getattr(self, "_panels_dirty", False):
            self._refresh_panels_lazy()
            self._panels_dirty = False

    def _refresh_panels_lazy(self):
        if hasattr(self, "histogram"):
            self.histogram.refresh()
            # Update stats label
            if self.histogram._hists and hasattr(self, "_hist_stats"):
                try:
                    lum = self.histogram._hists["lum"]
                    total = lum.sum()
                    if total > 0:
                        lo = int(np.argmax(lum > 0))
                        hi = int(255 - np.argmax(lum[::-1] > 0))
                        mean = float(np.dot(np.arange(256), lum) / total)
                        self._hist_stats.setText(f"Min: {lo}   Mean: {mean:.1f}   Max: {hi}")
                except Exception:
                    pass
        if hasattr(self, "navigator"):
            self.navigator.refresh_thumb()

    def _setup_rulers(self):
        """Insert rulers into the central widget layout."""
        self._ruler_h = RulerWidget(Qt.Horizontal)
        self._ruler_v = RulerWidget(Qt.Vertical)
        self._show_rulers = True
        # Rebuild central widget with rulers
        central = self.centralWidget()
        wrapper2 = QWidget()
        main_l = QVBoxLayout(wrapper2)
        main_l.setContentsMargins(0, 0, 0, 0); main_l.setSpacing(0)
        # Options bar is already in central
        if hasattr(self, "options_bar"):
            main_l.addWidget(self.options_bar)
        # Ruler row
        ruler_row = QHBoxLayout(); ruler_row.setSpacing(0)
        self._ruler_corner = QWidget()
        self._ruler_corner.setFixedSize(dp(18), dp(18))
        self._ruler_corner.setStyleSheet(f"background:{C.BG0};border-right:1px solid {C.BORDER};border-bottom:1px solid {C.BORDER};")
        ruler_row.addWidget(self._ruler_corner)
        ruler_row.addWidget(self._ruler_h)
        main_l.addLayout(ruler_row)
        # Canvas row
        canvas_row = QHBoxLayout(); canvas_row.setSpacing(0)
        canvas_row.addWidget(self._ruler_v)
        canvas_row.addWidget(self.canvas, 1)
        main_l.addLayout(canvas_row, 1)
        self.setCentralWidget(wrapper2)
        # Mouse tracking for ruler crosshairs
        self.canvas.setMouseTracking(True)

    def _on_canvas_zoom_changed(self, zoom, pan_x, pan_y):
        if hasattr(self, "_ruler_h"):
            self._ruler_h.update_view(zoom, pan_x, pan_y)
        if hasattr(self, "_ruler_v"):
            self._ruler_v.update_view(zoom, pan_x, pan_y)
        if hasattr(self, "navigator"):
            self.navigator.update_view(zoom, pan_x, pan_y)
        if hasattr(self, "_nav_zoom_sl"):
            self._nav_zoom_sl.blockSignals(True)
            self._nav_zoom_sl.setValue(max(5, min(3200, int(zoom * 100))))
            self._nav_zoom_sl.blockSignals(False)
            self._nav_zoom_lbl.setText(f"{zoom * 100:.0f}%")

    def _status(self, msg):
        self.statusBar().showMessage("  " + msg)

    # ── Options Bar ───────────────────────────────────────────────────────────
    def _create_options_bar(self):
        self.options_bar = OptionsBar(self)
        # Insert above central widget via a wrapper
        wrapper = QWidget()
        vl = QVBoxLayout(wrapper); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)
        vl.addWidget(self.options_bar)
        vl.addWidget(self.canvas)
        self.setCentralWidget(wrapper)
        # Re-grab canvas ref
        self.canvas.setParent(wrapper)

    # ── Left Toolbar ──────────────────────────────────────────────────────────
    def _create_toolbar(self):
        tb = QToolBar("Tools"); tb.setMovable(False)
        tb.setOrientation(Qt.Vertical)
        tb.setIconSize(QSize(dp(18), dp(18)))
        tb.setStyleSheet(f"""
            QToolBar {{
                background:{C.BG0};
                border:none;
                border-right:1px solid {C.BORDER};
                padding:{dp(5)}px {dp(4)}px;
                spacing:{dp(2)}px;
            }}
            QToolButton {{
                background:transparent;
                border:1px solid transparent;
                border-radius:{dp(5)}px;
                padding:{dp(3)}px;
                min-width:{dp(30)}px;
                min-height:{dp(30)}px;
            }}
            QToolButton:hover {{
                background:{C.BG3};
                border-color:{C.BORDER};
            }}
            QToolButton:checked {{
                background:{C.ACCENT_D};
                border-color:{C.ACCENT};
            }}
        """)
        self.addToolBar(Qt.LeftToolBarArea, tb)
        self.tool_group = QActionGroup(self)

        def sep():
            s = QWidget(); s.setFixedHeight(dp(1))
            s.setStyleSheet(f"background:{C.BORDER}; margin:3px 4px;")
            tb.addWidget(s)

        def simple_tool(tool_id, tip, shortcut=None):
            sz = dp(34)
            btn = QToolButton(); btn.setCheckable(True)
            btn.setFixedSize(sz, sz)
            btn.setToolTip(f"{tip}" + (f" ({shortcut})" if shortcut else ""))
            btn.setIcon(svg_icon(tool_id, C.TEXT_SEC, dp(18)))
            btn.clicked.connect(lambda: self._set_tool(tool_id, btn))
            self.tool_group.addAction(btn.defaultAction() if btn.defaultAction() else QAction(self))
            tb.addWidget(btn)
            self._tool_buttons[tool_id] = btn
            return btn

        def flyout_tool(primary, tools, shortcut=None):
            """tools = [(tool_id, label), ...]"""
            sz = dp(32)
            btn = FlyoutToolButton(primary, tools, self)
            btn.tool_selected.connect(lambda t: self._set_tool(t, btn))
            if shortcut:
                btn.setToolTip(f"{primary.replace('-',' ').title()} ({shortcut})")
            tb.addWidget(btn)
            self._flyout_buttons[primary] = btn
            for tid, _ in tools:
                self._tool_buttons[tid] = btn
            return btn

        self._tool_buttons = {}
        self._flyout_buttons = {}

        simple_tool("move", "Move / Select", "V")
        sep()

        flyout_tool("marquee-rect", [
            ("marquee-rect",    "Rect Marquee"),
            ("marquee-ellipse", "Ellipse Marquee"),
            ("lasso",           "Lasso"),
            ("magnetic-lasso",  "Magnetic Scissors"),
            ("magic-wand",      "Magic Wand"),
            ("select-color",    "Select by Color"),
        ], "M")

        flyout_tool("crop", [
            ("crop", "Crop"),
            ("measure", "Measure"),
        ], "C")
        sep()

        flyout_tool("brush", [
            ("brush", "Brush"),
            ("pencil", "Pencil"),
            ("spray", "Spray / Airbrush"),
        ], "B")

        simple_tool("eraser", "Eraser", "E")

        flyout_tool("clone", [
            ("clone",   "Clone Stamp"),
            ("healing", "Healing Brush"),
            ("red-eye", "Red Eye Removal"),
        ], "S")

        flyout_tool("dodge", [
            ("dodge", "Dodge"),
            ("burn", "Burn"),
            ("sponge", "Sponge"),
            ("smudge", "Smudge"),
        ])
        sep()

        flyout_tool("rect", [
            ("rect", "Rectangle"),
            ("ellipse", "Ellipse"),
            ("triangle", "Triangle"),
            ("line", "Line"),
            ("arrow", "Arrow"),
            ("polygon", "Polygon"),
            ("star", "Star"),
        ], "R")

        simple_tool("text", "Text", "T")
        simple_tool("pen", "Pen Tool", "P")
        simple_tool("note", "Sticky Note", "N")
        sep()

        flyout_tool("gradient", [
            ("gradient", "Gradient"),
            ("fill", "Fill Bucket"),
            ("pattern", "Pattern Fill"),
        ], "G")

        simple_tool("eyedropper", "Eyedropper", "I")
        sep()

        flyout_tool("pan", [
            ("pan", "Pan"),
            ("zoom", "Zoom"),
        ], "H")

        sep()
        # ── Transform tools ──────────────────────────────────────────────────
        flyout_tool("transform", [
            ("transform",   "Free Transform"),
            ("perspective", "Perspective Transform"),
        ], "X")

        flyout_tool("warp", [
            ("warp",         "Warp Transform"),
            ("blur-sharpen", "Blur / Sharpen"),
        ])

        sep()
        # FG/BG color boxes
        tb.addWidget(self._build_color_buttons())

        # Select brush as default
        if "brush" in self._flyout_buttons:
            self._flyout_buttons["brush"].setChecked(True)

    def _build_color_buttons(self):
        """Live FG/BG color swatches at bottom of left toolbar."""
        editor_ref = self

        class _Swatch(QWidget):
            def __init__(self2):
                super().__init__()
                self2.setFixedSize(dp(40), dp(54))
                self2.setToolTip("Left-click: pick foreground\nRight-click: pick background\nX: swap")

            def paintEvent(self2, event):
                p = QPainter(self2)
                p.setRenderHint(QPainter.Antialiasing)
                # BG box (back, offset bottom-right)
                bx, by = dp(12), dp(12)
                bsz = dp(22)
                p.setPen(QPen(QColor(C.BORDER), 1.2))
                p.setBrush(QBrush(editor_ref.bg_color))
                p.drawRoundedRect(bx, by, bsz, bsz, 3, 3)
                # FG box (front)
                fx, fy = dp(4), dp(4)
                fsz = dp(22)
                p.setPen(QPen(QColor("#888888"), 1.5))
                p.setBrush(QBrush(editor_ref.fg_color))
                p.drawRoundedRect(fx, fy, fsz, fsz, 3, 3)
                # Swap hint arrow
                p.setPen(QColor(C.TEXT_MUT))
                p.setFont(QFont("Segoe UI", 6))
                p.drawText(QRect(dp(26), dp(36), dp(14), dp(14)), Qt.AlignCenter, "⇄")
                p.end()

            def mousePressEvent(self2, e):
                if e.button() == Qt.LeftButton:
                    fx, fy, fsz = dp(4), dp(4), dp(22)
                    if QRect(fx, fy, fsz, fsz).contains(e.pos()):
                        c = QColorDialog.getColor(editor_ref.fg_color, editor_ref, "Foreground Color")
                        if c.isValid():
                            editor_ref.set_fg_color(c)
                            if hasattr(editor_ref, "color_panel"):
                                editor_ref.color_panel.sync_fg(c)
                            self2.update()
                    else:
                        c = QColorDialog.getColor(editor_ref.bg_color, editor_ref, "Background Color")
                        if c.isValid():
                            editor_ref.set_bg_color(c); self2.update()
                elif e.button() == Qt.RightButton:
                    editor_ref.fg_color, editor_ref.bg_color = editor_ref.bg_color, editor_ref.fg_color
                    self2.update(); editor_ref.canvas.update()

        self._color_swatch = _Swatch()
        return self._color_swatch

    def _set_tool(self, tool, btn=None):
        prev_tool = self.current_tool
        self.current_tool = tool
        # Leaving crop tool: discard any pending crop rect
        if prev_tool == "crop" and tool != "crop":
            self.canvas.crop_rect = None
        # Leaving transform tools without committing — auto-commit
        if prev_tool == "transform" and tool != "transform":
            if getattr(self.canvas, "_xform_active", False):
                self.canvas.xform_commit()
        if prev_tool == "perspective" and tool != "perspective":
            if getattr(self.canvas, "_persp_active", False):
                self.canvas.persp_commit()
        if prev_tool == "warp" and tool != "warp":
            # Keep the warped pixels, just clear the backup
            self.canvas._warp_orig = None
        # Uncheck all — then refresh icons on FlyoutToolButtons
        for fb in self._flyout_buttons.values():
            fb.setChecked(False)
            if hasattr(fb, "_update_icon"):
                fb._update_icon()
        for tb in self._tool_buttons.values():
            if hasattr(tb, "setChecked"):
                tb.setChecked(False)
        if btn:
            btn.setChecked(True)
            if hasattr(btn, "_update_icon"):
                btn._update_icon()
        self.options_bar.update_for_tool(tool)
        layer = self.active_layer()
        if layer and getattr(layer, 'editing_mask', False) and layer.mask is not None:
            self._status("Mask edit mode — white=reveal, black=hide")
        else:
            self._status(f"Tool: {tool.replace('-', ' ').title()}")
        # Set cursor
        cursors = {"eyedropper": Qt.CrossCursor, "pan": Qt.OpenHandCursor,
                   "zoom": Qt.SizeAllCursor, "text": Qt.IBeamCursor,
                   "crop": Qt.CrossCursor}
        self.canvas.setCursor(cursors.get(tool, Qt.ArrowCursor))
        self.canvas.update()

    # ── Right Panel ───────────────────────────────────────────────────────────
    def _create_right_panel(self):
        panel = QWidget(); panel.setFixedWidth(dp(300))
        panel.setStyleSheet(f"background:{C.BG1}; border-left:1px solid {C.BORDER};")
        vl = QVBoxLayout(panel); vl.setContentsMargins(0, 0, 0, 0); vl.setSpacing(0)

        tabs = QTabWidget(); tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        tabs.tabBar().setElideMode(Qt.ElideNone)
        # Override only scroll-button appearance for this specific tab bar
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; background: {C.BG1}; }}
            QTabBar {{
                background: {C.BG0};
                border-bottom: 1px solid {C.BORDER};
            }}
            QTabBar::tab {{
                padding: {dp(6)}px {dp(8)}px;
                font-size: {dp(10)}px;
                max-width: {dp(72)}px;
            }}
            QTabBar QToolButton {{
                background: {C.BG1};
                border: none;
                border-left: 1px solid {C.BORDER};
                color: {C.TEXT_SEC};
                min-width: {dp(18)}px;
                min-height: 100%;
                padding: 0 {dp(3)}px;
                border-radius: 0;
            }}
            QTabBar QToolButton:hover {{
                background: {C.BG2};
                color: {C.ACCENT};
            }}
            QTabBar QToolButton:disabled {{ color: {C.BG3}; }}
        """)

        # Layers tab
        self.layer_panel = LayerPanel(self)
        lt = tabs.addTab(self.layer_panel, "Layers")
        tabs.setTabToolTip(lt, "Layers — manage, reorder, blend")

        # Properties tab
        prop_scroll = QScrollArea(); prop_scroll.setWidgetResizable(True)
        prop_scroll.setFrameShape(QFrame.NoFrame)
        self.prop_panel = PropertiesPanel(self)
        prop_scroll.setWidget(self.prop_panel)
        pt = tabs.addTab(prop_scroll, "Props")
        tabs.setTabToolTip(pt, "Properties — brush, tool settings")

        # Color tab
        color_scroll = QScrollArea(); color_scroll.setWidgetResizable(True)
        color_scroll.setFrameShape(QFrame.NoFrame)
        self.color_panel = ColorPanel(self)
        color_scroll.setWidget(self.color_panel)
        ct = tabs.addTab(color_scroll, "Color")
        tabs.setTabToolTip(ct, "Color — HSV picker, hex")

        # ── Channels tab ─────────────────────────────────────────────────────
        self.channels_panel = ChannelsPanel(self)
        cht = tabs.addTab(self.channels_panel, "Channels")
        tabs.setTabToolTip(cht, "Channels — RGBA channel visibility & thumbnails")

        # Histogram tab
        hist_w = QWidget(); hist_l = QVBoxLayout(hist_w)
        hist_l.setContentsMargins(dp(6), dp(6), dp(6), dp(6)); hist_l.setSpacing(dp(4))
        # Channel buttons
        ch_row = QHBoxLayout(); ch_row.setSpacing(dp(3))
        self.histogram = HistogramWidget(self)
        for ch, label in [("rgb", "RGB"), ("r", "R"), ("g", "G"), ("b", "B"), ("lum", "Lum")]:
            btn = QPushButton(label); btn.setFixedHeight(dp(22))
            btn.setCheckable(True); btn.setChecked(ch == "rgb")
            btn.clicked.connect(lambda checked, c=ch: (self.histogram.set_channel(c), self.histogram.refresh()))
            ch_row.addWidget(btn)
        hist_l.addLayout(ch_row)
        hist_l.addWidget(self.histogram)
        # Stats
        self._hist_stats = QLabel("Min: —  Mean: —  Max: —")
        self._hist_stats.setStyleSheet(f"color:{C.TEXT_MUT}; font-size:10px; font-family:Consolas;")
        hist_l.addWidget(self._hist_stats)
        hist_l.addStretch()
        ht = tabs.addTab(hist_w, "Hist")
        tabs.setTabToolTip(ht, "Histogram — channel analysis")

        # Navigator tab
        nav_w = QWidget(); nav_l = QVBoxLayout(nav_w)
        nav_l.setContentsMargins(dp(6), dp(6), dp(6), dp(6)); nav_l.setSpacing(dp(6))
        self.navigator = NavigatorPanel(self)
        nav_l.addWidget(self.navigator)
        # Zoom slider
        zrow = QHBoxLayout()
        zrow.addWidget(QLabel("Zoom:"))
        self._nav_zoom_sl = QSlider(Qt.Horizontal)
        self._nav_zoom_sl.setRange(5, 3200)  # 0.05x to 32x (×100)
        self._nav_zoom_sl.setValue(100)
        self._nav_zoom_sl.valueChanged.connect(lambda v: self._set_zoom(v / 100.0))
        zrow.addWidget(self._nav_zoom_sl, 1)
        self._nav_zoom_lbl = QLabel("100%")
        self._nav_zoom_lbl.setFixedWidth(dp(44))
        self._nav_zoom_lbl.setStyleSheet(f"color:{C.TEXT_SEC}; font-size:11px; font-family:Consolas;")
        zrow.addWidget(self._nav_zoom_lbl)
        nav_l.addLayout(zrow)
        nav_l.addStretch()
        nt = tabs.addTab(nav_w, "Nav")
        tabs.setTabToolTip(nt, "Navigator — pan & zoom thumbnail")

        # ── Paths tab ─────────────────────────────────────────────────────────
        self.paths_panel = PathsPanel(self)
        pat = tabs.addTab(self.paths_panel, "Paths")
        tabs.setTabToolTip(pat, "Paths — saved pen paths, convert to selection")

        # Align tab
        self.align_panel = AlignPanel(self)
        at = tabs.addTab(self.align_panel, "Align")
        tabs.setTabToolTip(at, "Align — distribute layer contents")

        # History tab
        self.history_panel = HistoryPanel(self)
        het = tabs.addTab(self.history_panel, "History")
        tabs.setTabToolTip(het, "History — undo states")

        vl.addWidget(tabs)
        dock = QDockWidget("", self)
        dock.setTitleBarWidget(QWidget())  # hide title bar
        dock.setWidget(panel)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    # ── Menus ─────────────────────────────────────────────────────────────────
    def _create_menus(self):
        mb = self.menuBar()
        # File
        fm = mb.addMenu("&File")
        self._act(fm, "&New...", "Ctrl+N", self.new_image)
        self._act(fm, "&Open...", "Ctrl+O", self.open_image)
        self._act(fm, "Open from &Clipboard", "Ctrl+Shift+V", self.open_from_clipboard)
        self._recent_menu = fm.addMenu("Open &Recent")
        self._rebuild_recent_menu()
        fm.addSeparator()
        self._act(fm, "&Save", "Ctrl+S", self.save_image)
        self._act(fm, "Save &As...", "Ctrl+Shift+S", self.save_image_as)
        self._act(fm, "Export &PNG...", "", self.export_png)
        fm.addSeparator()
        self._act(fm, "&Copy to Clipboard", "Ctrl+Shift+C", self.copy_to_clipboard)
        self._act(fm, "Upload to &Imgur", "Ctrl+U", self.upload_imgur)
        fm.addSeparator()
        self._act(fm, "Save &Project (.swiftshot)...", "", self.save_project)
        self._act(fm, "Open P&roject (.swiftshot)...", "", self.open_project)
        fm.addSeparator()
        self._act(fm, "&Pin to Desktop", "", self.pin_to_desktop)
        fm.addSeparator()
        self._act(fm, "E&xit", "Ctrl+Q", self.close)

        # Edit
        em = mb.addMenu("&Edit")
        self._act(em, "&Undo", "Ctrl+Z", self.undo)
        self._act(em, "&Redo", "Ctrl+Y", self.redo)
        em.addSeparator()
        self._act(em, "Cu&t", "Ctrl+X", self.cut_selection)
        self._act(em, "&Copy", "Ctrl+C", self._smart_copy)
        self._act(em, "&Paste", "Ctrl+V", self.paste_clipboard)
        self._act(em, "&Delete", "Delete", self.delete_selection)
        em.addSeparator()
        self._act(em, "Select &All", "Ctrl+A", self.select_all)
        self._act(em, "&Deselect", "Ctrl+D", self.deselect)
        self._act(em, "&Invert Selection", "Ctrl+Shift+I", self.invert_selection)
        em.addSeparator()
        sel_m = em.addMenu("Modify Selection")
        self._act(sel_m, "&Expand...", "", self.selection_expand)
        self._act(sel_m, "&Contract...", "", self.selection_contract)
        self._act(sel_m, "&Feather...", "", self.selection_feather)
        self._act(sel_m, "&Smooth...", "", self.selection_smooth)
        self._act(em, "Color &Range...", "", self.color_range_select)
        em.addSeparator()
        self._act(em, "Content-Aware Fill", "Shift+F5",
                  lambda: self.canvas._content_aware_fill())
        em.addSeparator()
        ocp_act = em.addAction("Off-Canvas Painting")
        ocp_act.setCheckable(True)
        ocp_act.setChecked(False)
        ocp_act.triggered.connect(lambda v: setattr(self, "off_canvas_paint", v))
        self._off_canvas_action = ocp_act

        # Image
        im = mb.addMenu("&Image")
        self._act(im, "&Resize Canvas...", "", self.resize_canvas)
        self._act(im, "Resize &Image...", "", self.resize_image)
        im.addSeparator()
        self._act(im, "Rotate 90° CW", "", lambda: self.rotate_image(90))
        self._act(im, "Rotate 90° CCW", "", lambda: self.rotate_image(-90))
        self._act(im, "Rotate 180°", "", lambda: self.rotate_image(180))
        im.addSeparator()
        self._act(im, "Flip &Horizontal", "", lambda: self.flip_image("h"))
        self._act(im, "Flip &Vertical", "", lambda: self.flip_image("v"))
        im.addSeparator()
        self._act(im, "Flatten Image", "", self.flatten_image)
        self._act(im, "Merge Down", "", self.merge_down)
        self._act(im, "Group Layers", "Ctrl+G",
                  lambda: self.layer_panel.group_selected() if hasattr(self,'layer_panel') else None)
        self._act(im, "Ungroup Layers", "Ctrl+Shift+G",
                  lambda: self.layer_panel.ungroup() if hasattr(self,'layer_panel') else None)
        im.addSeparator()
        self._act(im, "Crop to Selection", "", self.crop_to_selection)
        self._act(im, "Apply Crop", "", self.apply_crop)
        im.addSeparator()
        mm = im.addMenu("Layer &Mask")
        self._act(mm, "Add White Mask",       "", lambda: self.layer_panel.mask_add_white())
        self._act(mm, "Add Black Mask",       "", lambda: self.layer_panel.mask_add_black_fn())
        self._act(mm, "Add From Selection",   "", self.mask_from_selection)
        mm.addSeparator()
        self._act(mm, "Apply Mask",           "", lambda: self.layer_panel.mask_apply())
        self._act(mm, "Delete Mask",          "", lambda: self.layer_panel.mask_delete())
        self._act(mm, "Disable / Enable Mask","", lambda: self.layer_panel.mask_toggle_enable())
        mm.addSeparator()
        self._act(mm, "Mask to Selection",    "", self.mask_to_selection)
        self._act(mm, "Selection to Mask",    "", self.mask_from_selection)
        self._act(mm, "Invert Mask",          "", self.mask_invert)
        im.addSeparator()
        lm = im.addMenu("&Layer Transform")
        self._act(lm, "Free &Transform",    "Ctrl+T",       self.enter_free_transform)
        self._act(lm, "&Perspective...",    "Ctrl+Shift+P", self.enter_perspective)
        self._act(lm, "&Warp Transform",    "",             lambda: self._set_tool("warp"))
        lm.addSeparator()
        self._act(lm, "Flip Layer &Horizontal", "", lambda: self.flip_layer("h"))
        self._act(lm, "Flip Layer &Vertical",   "", lambda: self.flip_layer("v"))
        self._act(lm, "Rotate Layer 90° CW",    "", lambda: self.rotate_layer(90))
        self._act(lm, "Rotate Layer 90° CCW",   "", lambda: self.rotate_layer(-90))
        self._act(lm, "Rotate Layer 180°",      "", lambda: self.rotate_layer(180))

        # Adjustments
        am = mb.addMenu("&Adjustments")
        self._act(am, "&Brightness / Contrast...", "", self.adjust_brightness_contrast)
        self._act(am, "&Hue / Saturation...", "", self.adjust_hue_saturation)
        self._act(am, "&Levels...", "", self.adjust_levels)
        self._act(am, "&Curves...", "", self.adjust_curves)
        self._act(am, "&Gamma...", "", self.adjust_gamma)
        self._act(am, "&Vibrance...", "", self.adjust_vibrance)
        self._act(am, "&Threshold...", "", self.adjust_threshold)
        am.addSeparator()
        self._act(am, "&Invert Colors", "Ctrl+I", self.invert_colors)
        self._act(am, "&Grayscale", "", self.grayscale)
        self._act(am, "&Auto Contrast", "", self.auto_contrast)
        self._act(am, "Auto &Levels", "", self.auto_levels)
        self._act(am, "Color &Balance...", "", self.color_balance)
        self._act(am, "&Sepia", "", self.sepia)

        # Filters
        flm = mb.addMenu("F&ilters")
        bm = flm.addMenu("Blur")
        self._act(bm, "Gaussian Blur...", "", self.gaussian_blur)
        self._act(bm, "Box Blur...", "", self.box_blur)
        self._act(bm, "Motion Blur...", "", self.motion_blur)
        self._act(bm, "Tilt Shift...", "", self.filter_tilt_shift)
        sm = flm.addMenu("Sharpen")
        self._act(sm, "Sharpen", "", self.sharpen)
        self._act(sm, "Unsharp Mask...", "", self.unsharp_mask)
        flm.addSeparator()
        self._act(flm, "Edge Detect", "", self.edge_detect)
        self._act(flm, "Emboss", "", self.emboss)
        self._act(flm, "Contour", "", self.contour)
        flm.addSeparator()
        self._act(flm, "Posterize...", "", self.posterize)
        self._act(flm, "Solarize...", "", self.solarize)
        self._act(flm, "Pixelate...", "", self.pixelate)
        flm.addSeparator()
        self._act(flm, "Add &Noise...", "", self.add_noise)
        self._act(flm, "&Vignette...", "", self.vignette)
        flm.addSeparator()
        self._act(flm, "Oil Paint...", "", self.filter_oil_paint)
        self._act(flm, "Halftone...", "", self.filter_halftone)
        self._act(flm, "Duotone...", "", self.filter_duotone)
        self._act(flm, "Chromatic Aberration...", "", self.filter_chromatic_aberration)
        self._act(flm, "Noise Generator...", "", self.filter_noise_gen)

        # AI
        aim = mb.addMenu("A&I")
        self._act(aim, "Remove Background", "", self.ai_remove_background)
        aim.addSeparator()
        self._act(aim, "Smart Upscale 2x", "", lambda: self.ai_upscale(2))
        self._act(aim, "Smart Upscale 4x", "", lambda: self.ai_upscale(4))
        aim.addSeparator()
        self._act(aim, "Generate Depth Map", "", self.ai_depth_map)
        self._act(aim, "Detect Objects", "", self.ai_object_detect)

        # Select
        selm = mb.addMenu("&Select")
        self._act(selm, "Select All", "Ctrl+A", self.select_all)
        self._act(selm, "Deselect", "Ctrl+D", self.deselect)
        self._act(selm, "Invert Selection", "Ctrl+Shift+I", self.invert_selection)
        selm.addSeparator()
        self._act(selm, "Expand...", "", self.selection_expand)
        self._act(selm, "Contract...", "", self.selection_contract)
        self._act(selm, "Feather...", "", self.selection_feather)
        self._act(selm, "Smooth...", "", self.selection_smooth)
        selm.addSeparator()
        self._act(selm, "Color Range...", "", self.color_range_select)
        self._act(selm, "Select by Color", "", self.selection_by_color_dialog)
        selm.addSeparator()
        self._act(selm, "Quick Mask Mode (Q)", "Q", self.toggle_quick_mask)
        selm.addSeparator()
        # Selection mode submenu
        sm_m = selm.addMenu("Mode")
        self._act(sm_m, "New",        "", lambda: self._sel_mode_act("new"))
        self._act(sm_m, "Add",        "", lambda: self._sel_mode_act("add"))
        self._act(sm_m, "Subtract",   "", lambda: self._sel_mode_act("subtract"))
        self._act(sm_m, "Intersect",  "", lambda: self._sel_mode_act("intersect"))

        # View
        vm = mb.addMenu("&View")
        self._act(vm, "Fit in Window", "Ctrl+0", self.canvas.fit_in_view)
        self._act(vm, "Zoom In", "Ctrl+=", lambda: self._zoom(1.25))
        self._act(vm, "Zoom Out", "Ctrl+-", lambda: self._zoom(0.8))
        self._act(vm, "Actual Size (100%)", "Ctrl+1", lambda: self._set_zoom(1.0))
        vm.addSeparator()
        self._act(vm, "Toggle Rulers", "Ctrl+R", self.toggle_rulers)
        self._act(vm, "Toggle Grid", "Ctrl+'", self.toggle_grid)
        vm.addSeparator()
        # ── Rotate View ────────────────────────────────────────────────────────
        rv_m = vm.addMenu("Rotate View")
        for deg, label in [(15, "Rotate +15°"), (-15, "Rotate -15°"),
                           (45, "Rotate +45°"), (-45, "Rotate -45°"),
                           (90, "Rotate +90°"), (-90, "Rotate -90°")]:
            self._act(rv_m, label, "", lambda checked=False, d=deg: self.canvas.rotate_view(d))
        rv_m.addSeparator()
        self._act(rv_m, "Reset Rotation", "Ctrl+Shift+R", self.canvas.reset_view_rotation)
        vm.addSeparator()
        # ── Guides ─────────────────────────────────────────────────────────────
        gm = vm.addMenu("Guides")
        self._act(gm, "Add Horizontal Guide...", "", self._add_h_guide)
        self._act(gm, "Add Vertical Guide...",   "", self._add_v_guide)
        gm.addSeparator()
        self._snap_act = gm.addAction("Snap to Guides")
        self._snap_act.setCheckable(True); self._snap_act.setChecked(True)
        self._snap_act.triggered.connect(
            lambda v: setattr(self.canvas, "_snap_to_guides", v))
        gm.addSeparator()
        self._act(gm, "Clear All Guides", "", self.canvas.clear_guides)
        vm.addSeparator()
        self._act(vm, "Refresh Histogram", "", lambda: (self.histogram.refresh() if hasattr(self, "histogram") else None))
        vm.addSeparator()
        scale_menu = vm.addMenu("UI &Scale")
        for label, val in [("75%", 0.75), ("100% — Standard", 1.0),
                            ("125%", 1.25), ("150%", 1.5),
                            ("175%", 1.75), ("200%", 2.0),
                            ("Auto-detect", None)]:
            act = scale_menu.addAction(label)
            act.triggered.connect(lambda checked=False, v=val: self._set_ui_scale(v))

        # Tools
        tm = mb.addMenu("&Tools")
        self._act(tm, "Command Palette", "Ctrl+K", self.open_command_palette)
        tm.addSeparator()
        self._act(tm, "OCR – Extract Text", "Ctrl+Shift+O", self.run_ocr)

    def _set_ui_scale(self, scale_val):
        """Change UI scale and restart editor to apply."""
        import json
        cfg_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "SwiftShot")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, "config.json")
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        if scale_val is None:
            cfg.pop("ui_scale", None)
            label = "Auto-detect"
        else:
            cfg["ui_scale"] = scale_val
            label = f"{scale_val*100:.0f}%"
        try:
            with open(cfg_path, "w") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
        from PyQt5.QtWidgets import QMessageBox
        mb = QMessageBox(self)
        mb.setWindowTitle("UI Scale Changed")
        mb.setText("UI Scale set to %s.  Restart to apply." % label)

        mb.setIcon(QMessageBox.Information)
        mb.setStandardButtons(QMessageBox.Ok)
        mb.exec_()

    def _act(self, menu, name, shortcut, cb):
        a = QAction(name, self)
        if shortcut: a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(cb); menu.addAction(a); return a

    # ── Helpers ───────────────────────────────────────────────────────────────
    def set_fg_color(self, c):
        self.fg_color = c
        if hasattr(self, "color_panel"):
            self.color_panel.sync_fg(c)

    def set_bg_color(self, c):
        self.bg_color = c

    def update_layer_panel(self):
        if hasattr(self, "layer_panel"):
            self.layer_panel.refresh()
        if hasattr(self, "channels_panel"):
            self.channels_panel.refresh()
        if hasattr(self, "paths_panel"):
            self.paths_panel.refresh()

    def update_history_panel(self):
        if hasattr(self, "history_panel"):
            self.history_panel.refresh()

    # ── Compositing ───────────────────────────────────────────────────────────
    def get_composite(self):
        if not self.layers: return None
        result = Image.new("RGBA", self.layers[0].image.size, (0, 0, 0, 0))
        for layer in self.layers:
            if not layer.visible: continue
            img = layer.image.copy()
            # Apply layer mask
            if layer.mask is not None and layer.mask_enabled:
                r, g, b, a = img.split()
                masked_a = ImageChops.multiply(a, layer.mask)
                img = Image.merge("RGBA", (r, g, b, masked_a))
            if layer.opacity < 255:
                r, g, b, a = img.split()
                a = a.point(lambda x: int(x * layer.opacity / 255))
                img = Image.merge("RGBA", (r, g, b, a))
            # Apply layer effects (rendered onto a scratch canvas then merged)
            if getattr(layer, 'effects', []):
                result = self._blend_with_effects(result, img, layer)
            else:
                result = self._blend(result, img, layer.blend_mode)
        # Apply channel visibility from ChannelsPanel
        if hasattr(self, 'channels_panel'):
            cp = self.channels_panel
            r2, g2, b2, a2 = result.split()
            blank_l = Image.new("L", result.size, 0)
            blank_rgb = Image.new("L", result.size, 128)  # mid-gray for hidden color ch
            if cp.channel_hidden("R"): r2 = blank_rgb
            if cp.channel_hidden("G"): g2 = blank_rgb
            if cp.channel_hidden("B"): b2 = blank_rgb
            if cp.channel_hidden("A"): a2 = Image.new("L", result.size, 255)
            result = Image.merge("RGBA", (r2, g2, b2, a2))
        return result

    def _blend_with_effects(self, base, top, layer):
        """Render all enabled layer effects around `top`, then blend onto `base`."""
        iw, ih = top.size
        # We render effects in painter's-model order:
        #   1. Below-layer effects  (Drop Shadow, Outer Glow)
        #   2. The layer itself
        #   3. Above-layer effects  (Stroke, Color Overlay, Gradient Overlay,
        #                            Inner Glow, Bevel)

        # scratch = transparent canvas matching image size
        scratch = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))

        for fx in layer.effects:
            if not fx.get("enabled", True): continue
            kind = fx.get("type", "")

            # ── Drop Shadow ───────────────────────────────────────────────────
            if kind == "drop_shadow":
                shadow = self._fx_drop_shadow(top, fx)
                scratch.paste(shadow, (0, 0), shadow)

            # ── Outer Glow ────────────────────────────────────────────────────
            elif kind == "outer_glow":
                glow = self._fx_outer_glow(top, fx)
                scratch.paste(glow, (0, 0), glow)

        # Paste the layer image itself
        scratch.paste(top, (0, 0), top)

        # Above-layer effects (rendered on top of the layer pixels)
        for fx in layer.effects:
            if not fx.get("enabled", True): continue
            kind = fx.get("type", "")

            if kind == "inner_glow":
                ig = self._fx_inner_glow(top, fx)
                scratch = Image.alpha_composite(scratch, ig)

            elif kind == "bevel_emboss":
                bv = self._fx_bevel_emboss(top, fx)
                scratch = Image.alpha_composite(scratch, bv)

            elif kind == "color_overlay":
                co = self._fx_color_overlay(top, fx)
                scratch = Image.alpha_composite(scratch, co)

            elif kind == "gradient_overlay":
                go = self._fx_gradient_overlay(top, fx)
                scratch = Image.alpha_composite(scratch, go)

            elif kind == "stroke":
                st = self._fx_stroke(top, fx)
                scratch = Image.alpha_composite(scratch, st)

        return self._blend(base, scratch, layer.blend_mode)

    # ── Individual effect renderers ───────────────────────────────────────────

    def _fx_color_at(self, spec, default=(0, 0, 0)):
        """Parse color from effect dict: [r,g,b] list or fallback."""
        c = spec.get("color", default)
        if isinstance(c, (list, tuple)) and len(c) >= 3:
            return tuple(int(v) for v in c[:3])
        return default

    def _fx_drop_shadow(self, top, fx):
        """Render drop shadow: blurred, offset, tinted copy of alpha."""
        iw, ih = top.size
        alpha = top.split()[3]
        blur_r  = max(1, fx.get("blur", 8))
        opacity = fx.get("opacity", 180)
        angle   = math.radians(fx.get("angle", 135))
        dist    = fx.get("distance", 8)
        color   = self._fx_color_at(fx, (0, 0, 0))
        ox = int(math.cos(angle) * dist)
        oy = int(math.sin(angle) * dist)
        # Build shadow: color + blurred alpha
        shadow_layer = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        colored = Image.new("RGB", (iw, ih), color)
        blurred = alpha.filter(ImageFilter.GaussianBlur(blur_r))
        blurred = blurred.point(lambda v: int(v * opacity / 255))
        shadow_layer.paste(colored, (ox, oy))
        shifted_alpha = Image.new("L", (iw, ih), 0)
        shifted_alpha.paste(blurred, (ox, oy))
        shadow_layer.putalpha(shifted_alpha)
        return shadow_layer

    def _fx_outer_glow(self, top, fx):
        """Render outer glow: expanded, blurred halo around the layer alpha."""
        iw, ih = top.size
        alpha   = top.split()[3]
        blur_r  = max(1, fx.get("blur", 12))
        opacity = fx.get("opacity", 160)
        spread  = fx.get("spread", 0)
        color   = self._fx_color_at(fx, (255, 255, 200))
        glow    = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        # Spread: dilate alpha by a small amount before blur
        blurred = alpha.filter(ImageFilter.GaussianBlur(blur_r + spread))
        blurred = blurred.point(lambda v: int(v * opacity / 255))
        colored = Image.new("RGB", (iw, ih), color)
        glow.paste(colored, (0, 0))
        glow.putalpha(blurred)
        return glow

    def _fx_inner_glow(self, top, fx):
        """Render inner glow: glow confined to interior of layer alpha."""
        iw, ih = top.size
        alpha   = top.split()[3]
        blur_r  = max(1, fx.get("blur", 10))
        opacity = fx.get("opacity", 140)
        color   = self._fx_color_at(fx, (255, 255, 200))
        # Inner glow = outer glow of the inverted alpha, clipped to original alpha
        inv_alpha = ImageChops.invert(alpha)
        blurred   = inv_alpha.filter(ImageFilter.GaussianBlur(blur_r))
        clipped   = ImageChops.multiply(blurred, alpha)
        clipped   = clipped.point(lambda v: int(v * opacity / 255))
        glow = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        glow.paste(Image.new("RGB", (iw, ih), color), (0, 0))
        glow.putalpha(clipped)
        return glow

    def _fx_bevel_emboss(self, top, fx):
        """Render bevel/emboss using a simplified highlight+shadow approach."""
        iw, ih  = top.size
        alpha   = top.split()[3]
        depth   = fx.get("depth", 3)
        blur_r  = max(1, fx.get("size", 5))
        opacity = fx.get("opacity", 150)
        angle   = math.radians(fx.get("angle", 135))
        h_col   = self._fx_color_at({"color": fx.get("highlight_color", [255,255,255])})
        s_col   = self._fx_color_at({"color": fx.get("shadow_color",    [0,0,0])})
        arr  = np.array(alpha, dtype=np.float32) / 255.0
        # Simple emboss: convolve with directional kernel
        import scipy.ndimage as ndi
        dx = ndi.sobel(arr, axis=1)
        dy = ndi.sobel(arr, axis=0)
        # Light direction
        lx, ly = math.cos(angle), math.sin(angle)
        light = np.clip(dx * lx + dy * ly, -1, 1) * depth / 3.0
        # Build RGBA overlay
        result = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        h_arr = np.clip(light, 0, 1)   # highlight where lit
        s_arr = np.clip(-light, 0, 1)  # shadow where not lit
        for ch_arr, ch_col in [(h_arr, h_col), (s_arr, s_col)]:
            a_ch = (ch_arr * opacity).clip(0, 255).astype(np.uint8)
            layer_img = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
            layer_img.paste(Image.new("RGB", (iw, ih), ch_col), (0, 0))
            layer_img.putalpha(Image.fromarray(a_ch, "L"))
            # Clip to layer alpha
            combined_a = ImageChops.multiply(layer_img.split()[3], alpha)
            layer_img.putalpha(combined_a)
            result = Image.alpha_composite(result, layer_img)
        return result

    def _fx_color_overlay(self, top, fx):
        """Solid color overlaid on layer alpha shape."""
        iw, ih  = top.size
        opacity = fx.get("opacity", 255)
        color   = self._fx_color_at(fx, (255, 0, 0))
        alpha   = top.split()[3]
        overlay = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        overlay.paste(Image.new("RGB", (iw, ih), color), (0, 0))
        scaled_a = alpha.point(lambda v: int(v * opacity / 255))
        overlay.putalpha(scaled_a)
        return overlay

    def _fx_gradient_overlay(self, top, fx):
        """Vertical or horizontal gradient overlaid on layer alpha shape."""
        iw, ih   = top.size
        opacity  = fx.get("opacity", 200)
        c1       = self._fx_color_at({"color": fx.get("color1", [0,0,255])})
        c2       = self._fx_color_at({"color": fx.get("color2", [255,0,0])})
        angle_deg= fx.get("angle", 90)
        angle    = math.radians(angle_deg)
        alpha    = top.split()[3]
        arr = np.zeros((ih, iw, 4), dtype=np.float32)
        X = np.arange(iw, dtype=np.float32)
        Y = np.arange(ih, dtype=np.float32)
        Xg, Yg = np.meshgrid(X / max(1, iw - 1), Y / max(1, ih - 1))
        t = np.clip(Xg * math.cos(angle) + Yg * math.sin(angle), 0, 1)
        for ch in range(3):
            arr[:, :, ch] = c1[ch] * (1 - t) + c2[ch] * t
        arr[:, :, 3] = 255
        grad_img = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        # Clip to layer alpha, apply opacity
        a_np = np.array(alpha, dtype=np.float32) * opacity / 255
        grad_img.putalpha(Image.fromarray(a_np.clip(0, 255).astype(np.uint8), "L"))
        return grad_img

    def _fx_stroke(self, top, fx):
        """Outline stroke around the layer alpha shape."""
        iw, ih   = top.size
        size     = max(1, fx.get("size", 3))
        opacity  = fx.get("opacity", 255)
        position = fx.get("position", "outside")   # outside / inside / center
        color    = self._fx_color_at(fx, (0, 0, 0))
        alpha    = top.split()[3]
        # Expand alpha by blur to get stroke area
        if position == "outside":
            expanded = alpha.filter(ImageFilter.MaxFilter(size * 2 + 1))
            stroke_a = ImageChops.subtract(expanded, alpha)
        elif position == "inside":
            shrunk   = alpha.filter(ImageFilter.MinFilter(size * 2 + 1))
            stroke_a = ImageChops.subtract(alpha, shrunk)
        else:  # center
            expanded = alpha.filter(ImageFilter.MaxFilter(size + 1))
            shrunk   = alpha.filter(ImageFilter.MinFilter(size + 1))
            stroke_a = ImageChops.subtract(expanded, shrunk)
        stroke_a = stroke_a.point(lambda v: int(v * opacity / 255))
        stroke   = Image.new("RGBA", (iw, ih), (0, 0, 0, 0))
        stroke.paste(Image.new("RGB", (iw, ih), color), (0, 0))
        stroke.putalpha(stroke_a)
        return stroke

    def _blend(self, base, top, mode):
        if mode == "Normal":
            base.paste(top, (0, 0), top); return base
        elif mode == "Multiply":
            bl = ImageChops.multiply(base.convert("RGB"), top.convert("RGB"))
        elif mode == "Screen":
            bl = ImageChops.screen(base.convert("RGB"), top.convert("RGB"))
        elif mode == "Overlay":
            b = np.array(base.convert("RGB"), dtype=np.float32) / 255
            t = np.array(top.convert("RGB"), dtype=np.float32) / 255
            m = b < 0.5; r = np.where(m, 2 * b * t, 1 - 2 * (1 - b) * (1 - t))
            bl = Image.fromarray((r * 255).clip(0, 255).astype(np.uint8), "RGB")
        elif mode == "Darken":
            bl = ImageChops.darker(base.convert("RGB"), top.convert("RGB"))
        elif mode == "Lighten":
            bl = ImageChops.lighter(base.convert("RGB"), top.convert("RGB"))
        elif mode == "Difference":
            bl = ImageChops.difference(base.convert("RGB"), top.convert("RGB"))
        elif mode == "Color Dodge":
            b = np.array(base.convert("RGB"), dtype=np.float32)
            t = np.array(top.convert("RGB"), dtype=np.float32)
            bl = Image.fromarray(np.where(t >= 255, 255, np.clip(b * 255 / (256 - t), 0, 255)).astype(np.uint8), "RGB")
        elif mode == "Color Burn":
            b = np.array(base.convert("RGB"), dtype=np.float32)
            t = np.array(top.convert("RGB"), dtype=np.float32)
            bl = Image.fromarray(np.where(t <= 0, 0, np.clip(255 - (255 - b) * 255 / (t + 1), 0, 255)).astype(np.uint8), "RGB")
        else:
            base.paste(top, (0, 0), top); return base
        _, _, _, ta = top.split()
        result = base.copy(); bl_rgba = bl.convert("RGBA"); bl_rgba.putalpha(ta)
        result.paste(bl_rgba, (0, 0), bl_rgba); return result

    # ── Adjustment helper ─────────────────────────────────────────────────────
    def _apply_to_active(self, func, label="Adjustment"):
        l = self.active_layer()
        if not l: return
        self.history.save_state(self.layers, self.active_layer_index, label)
        # If editing mask, route adjustments to mask
        if getattr(l, 'editing_mask', False) and l.mask is not None:
            try:
                result = func(l.mask.convert("RGB"))
                if result is not None:
                    l.mask = result.convert("L")
            except Exception as e:
                if self.history.undo_stack:
                    self.history.undo_stack.pop()
                QMessageBox.critical(self, f"{label} Error", str(e))
                return
            self.canvas.update(); self.update_history_panel()
            return
        try:
            if self.canvas.selection_mask:
                orig = l.image.copy(); l.image = func(l.image)
                l.image = Image.composite(l.image, orig, self.canvas.selection_mask)
            else:
                l.image = func(l.image)
        except Exception as e:
            if self.history.undo_stack:
                self.history.undo_stack.pop()
            QMessageBox.critical(self, f"{label} Error", str(e))
            return
        self.canvas.update(); self.update_history_panel()

    # ── File Operations ───────────────────────────────────────────────────────
    def new_image(self):
        dlg = QDialog(self); dlg.setWindowTitle("New Image")
        form = QFormLayout(dlg)
        ws = QSpinBox(); ws.setRange(1, 10000); ws.setValue(1920)
        hs = QSpinBox(); hs.setRange(1, 10000); hs.setValue(1080)
        bg = QComboBox(); bg.addItems(["Transparent", "White", "Black"])
        form.addRow("Width:", ws); form.addRow("Height:", hs); form.addRow("Background:", bg)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            w, h = ws.value(), hs.value()
            bgc = {"Transparent": (0, 0, 0, 0), "White": (255, 255, 255, 255), "Black": (0, 0, 0, 255)}[bg.currentText()]
            self.layers = [Layer("Background", w, h)]
            self.layers[0].image = Image.new("RGBA", (w, h), bgc)
            self.active_layer_index = 0; self.history = HistoryManager(); self.file_path = None
            self.canvas.clear_selection(); self.update_layer_panel(); self.canvas.fit_in_view()
            self.setWindowTitle("SwiftShot Editor — Untitled")

    def _rebuild_recent_menu(self):
        """Rebuild Open Recent submenu from current _recent_files list."""
        if not hasattr(self, "_recent_menu"): return
        self._recent_menu.clear()
        if not self._recent_files:
            a = self._recent_menu.addAction("(empty)")
            a.setEnabled(False)
            return
        for path in self._recent_files:
            label = os.path.basename(path)
            act = self._recent_menu.addAction(label)
            act.setToolTip(path)
            act.triggered.connect(lambda checked, p=path: self.open_recent_file(p))
        self._recent_menu.addSeparator()
        self._recent_menu.addAction("Clear Recent", self._clear_recent)

    def _clear_recent(self):
        self._recent_files = []
        self._save_recent_files()
        self._rebuild_recent_menu()

    def open_recent_file(self, path):
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found", f"File no longer exists:\n{path}")
            self._recent_files = [p for p in self._recent_files if p != path]
            self._save_recent_files()
            self._rebuild_recent_menu()
            return
        if path.endswith(".swiftshot"):
            # Load project
            self.saved_path = None
            import zipfile, io
            try:
                with zipfile.ZipFile(path) as zf:
                    meta = json.loads(zf.read("project.json"))
                    if meta.get("magic") != "SWIFTSHOT_PROJECT":
                        QMessageBox.critical(self, "Error", "Not a valid SwiftShot project"); return
                    layers = []
                    for i, lmeta in enumerate(meta["layers"]):
                        img = Image.open(io.BytesIO(zf.read(f"layer_{i}.png"))).convert("RGBA")
                        layer = Layer(lmeta["name"], image=img)
                        layer.visible = lmeta.get("visible", True)
                        layer.opacity = lmeta.get("opacity", 255)
                        layer.blend_mode = lmeta.get("blend_mode", "Normal")
                        layer.locked = lmeta.get("locked", False)
                        layers.append(layer)
                self.layers = layers
                self.active_layer_index = meta.get("active_index", 0)
                self.history = HistoryManager()
                self.file_path = None; self.saved_path = path
                self.canvas.clear_selection(); self.update_layer_panel(); self.canvas.fit_in_view()
                self.setWindowTitle(f"SwiftShot Editor — {os.path.basename(path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")
        else:
            try:
                img = Image.open(path).convert("RGBA")
                self.layers = [Layer("Background", image=img)]
                self.active_layer_index = 0; self.history = HistoryManager(); self.file_path = path
                self.canvas.clear_selection(); self.update_layer_panel(); self.canvas.fit_in_view()
                self.setWindowTitle(f"SwiftShot Editor — {os.path.basename(path)}")
                self._add_recent(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open:\n{e}")

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp);;All Files (*)")
        if path:
            try:
                img = Image.open(path).convert("RGBA")
                self.layers = [Layer("Background", image=img)]
                self.active_layer_index = 0; self.history = HistoryManager(); self.file_path = path
                self.canvas.clear_selection(); self.update_layer_panel(); self.canvas.fit_in_view()
                self.setWindowTitle(f"SwiftShot Editor — {os.path.basename(path)}")
                self._add_recent(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open:\n{e}")

    def save_image(self):
        # If currently working on a .swiftshot project, Ctrl+S saves the project
        if self.saved_path and self.saved_path.endswith(".swiftshot"):
            self._save_project_to(self.saved_path)
        elif self.file_path:
            self._save_to(self.file_path)
        else:
            self.save_image_as()

    def save_image_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Image", "",
            "PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp);;All Files (*)")
        if path:
            self.file_path = path; self._save_to(path)
            self.setWindowTitle(f"SwiftShot Editor — {os.path.basename(path)}")

    def _save_to(self, path):
        try:
            c = self.get_composite()
            if c:
                if path.lower().endswith((".jpg", ".jpeg")):
                    quality, ok = QInputDialog.getInt(self, "JPEG Quality",
                        "Quality (1–100):", 90, 1, 100)
                    if not ok: return
                    c = c.convert("RGB")
                    c.save(path, quality=quality)
                else:
                    c.save(path)
                self._add_recent(path)
                self._status(f"Saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "", "PNG (*.png)")
        if path:
            c = self.get_composite()
            if c: c.save(path, "PNG"); self._status(f"Exported: {path}")

    # ── Edit Ops ──────────────────────────────────────────────────────────────
    def undo(self):
        s, i, lbl = self.history.undo(self.layers, self.active_layer_index)
        if s:
            self.layers = s; self.active_layer_index = i
            self.update_layer_panel(); self.canvas.update()
            self.update_history_panel(); self._status(f"Undo: {lbl}")

    def redo(self):
        s, i, lbl = self.history.redo(self.layers, self.active_layer_index)
        if s:
            self.layers = s; self.active_layer_index = i
            self.update_layer_panel(); self.canvas.update()
            self.update_history_panel(); self._status(f"Redo: {lbl}")

    def select_all(self):
        l = self.active_layer()
        if l:
            w, h = l.image.size
            self.canvas.set_selection_mask(Image.new("L", (w, h), 255))
            self.canvas.selection_rect = None; self.canvas.update()

    def deselect(self): self.canvas.clear_selection()

    def invert_selection(self):
        if self.canvas.selection_mask:
            self.canvas.set_selection_mask(ImageChops.invert(self.canvas.selection_mask))
            self.canvas.update()

    def delete_selection(self):
        l = self.active_layer()
        if l and self.canvas.selection_mask:
            self.history.save_state(self.layers, self.active_layer_index, "Delete")
            r, g, b, a = l.image.split()
            a = ImageChops.darker(a, ImageChops.invert(self.canvas.selection_mask))
            l.image = Image.merge("RGBA", (r, g, b, a)); self.canvas.update()

    def _smart_copy(self):
        """Ctrl+C: copy selection layer if active, otherwise copy full flattened image."""
        if self.canvas.selection_mask is not None:
            self.copy_selection()
        else:
            self.copy_to_clipboard()

    def copy_selection(self):
        l = self.active_layer()
        if l and self.canvas.selection_mask:
            self._clipboard = l.image.copy()
            r, g, b, a = self._clipboard.split()
            a = ImageChops.darker(a, self.canvas.selection_mask)
            self._clipboard = Image.merge("RGBA", (r, g, b, a))

    def cut_selection(self): self.copy_selection(); self.delete_selection()

    def paste_clipboard(self):
        if hasattr(self, "_clipboard") and self._clipboard:
            self.history.save_state(self.layers, self.active_layer_index, "Paste")
            nl = Layer("Pasted"); nl.image = self._clipboard.copy()
            self.layers.append(nl); self.active_layer_index = len(self.layers) - 1
            self.update_layer_panel(); self.canvas.update()

    # ── Selection modify ──────────────────────────────────────────────────────
    def selection_expand(self):
        if not self.canvas.selection_mask: return
        v, ok = QInputDialog.getInt(self, "Expand Selection", "Pixels:", 5, 1, 200)
        if ok:
            mask = self.canvas.selection_mask
            for _ in range(v): mask = mask.filter(ImageFilter.MaxFilter(3))
            self.canvas.set_selection_mask(mask); self.canvas.update()

    def selection_contract(self):
        if not self.canvas.selection_mask: return
        v, ok = QInputDialog.getInt(self, "Contract Selection", "Pixels:", 5, 1, 200)
        if ok:
            mask = self.canvas.selection_mask
            for _ in range(v): mask = mask.filter(ImageFilter.MinFilter(3))
            self.canvas.set_selection_mask(mask); self.canvas.update()

    def selection_feather(self):
        if not self.canvas.selection_mask: return
        v, ok = QInputDialog.getDouble(self, "Feather Selection", "Radius:", 5.0, 0.5, 100.0, 1)
        if ok:
            self.canvas.set_selection_mask(
                self.canvas.selection_mask.filter(ImageFilter.GaussianBlur(v)))
            self.canvas.update()

    def selection_smooth(self):
        if not self.canvas.selection_mask: return
        v, ok = QInputDialog.getInt(self, "Smooth Selection", "Radius:", 3, 1, 50)
        if ok:
            mask = self.canvas.selection_mask.filter(ImageFilter.GaussianBlur(v))
            mask = mask.point(lambda x: 255 if x > 127 else 0)
            self.canvas.set_selection_mask(mask); self.canvas.update()

    def color_range_select(self):
        if not self.layers: return
        items = ["Reds", "Yellows", "Greens", "Cyans", "Blues", "Magentas",
                 "Highlights", "Midtones", "Shadows"]
        item, ok = QInputDialog.getItem(self, "Color Range", "Select:", items, 0, False)
        if not ok: return
        fuzz, ok2 = QInputDialog.getInt(self, "Color Range", "Fuzziness:", 40, 1, 200)
        if not ok2: return
        comp = self.get_composite()
        if not comp: return
        arr = np.array(comp).astype(np.float32)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        match_map = {
            "Reds": (r > g + fuzz / 3) & (r > b + fuzz / 3),
            "Yellows": (r > fuzz) & (g > fuzz) & (b < 255 - fuzz),
            "Greens": (g > r + fuzz / 3) & (g > b + fuzz / 3),
            "Cyans": (g > fuzz) & (b > fuzz) & (r < 255 - fuzz),
            "Blues": (b > r + fuzz / 3) & (b > g + fuzz / 3),
            "Magentas": (r > fuzz) & (b > fuzz) & (g < 255 - fuzz),
            "Highlights": lum > 255 - fuzz,
            "Midtones": (lum > fuzz) & (lum < 255 - fuzz),
            "Shadows": lum < fuzz,
        }
        mask_arr = np.where(match_map.get(item, np.zeros_like(r, dtype=bool)), 255, 0).astype(np.uint8)
        self.canvas.set_selection_mask(Image.fromarray(mask_arr, "L")); self.canvas.update()
        self._status(f"Color Range: {item} ({np.count_nonzero(mask_arr)} px)")

    # ── Image Ops ─────────────────────────────────────────────────────────────
    def resize_canvas(self):
        if not self.layers: return
        w, h = self.layers[0].image.size
        dlg = QDialog(self); dlg.setWindowTitle("Resize Canvas"); form = QFormLayout(dlg)
        ws = QSpinBox(); ws.setRange(1, 20000); ws.setValue(w)
        hs = QSpinBox(); hs.setRange(1, 20000); hs.setValue(h)
        form.addRow("Width:", ws); form.addRow("Height:", hs)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            nw, nh = ws.value(), hs.value()
            self.history.save_state(self.layers, self.active_layer_index, "Resize Canvas")
            for l in self.layers:
                ni = Image.new("RGBA", (nw, nh), (0, 0, 0, 0)); ni.paste(l.image, (0, 0)); l.image = ni
            self.canvas.clear_selection(); self.canvas.fit_in_view(); self.update_layer_panel()

    def resize_image(self):
        if not self.layers: return
        w, h = self.layers[0].image.size
        dlg = QDialog(self); dlg.setWindowTitle("Resize Image"); form = QFormLayout(dlg)
        ws = QSpinBox(); ws.setRange(1, 20000); ws.setValue(w)
        hs = QSpinBox(); hs.setRange(1, 20000); hs.setValue(h)
        mt = QComboBox(); mt.addItems(["Lanczos", "Bilinear", "Bicubic", "Nearest"])
        form.addRow("Width:", ws); form.addRow("Height:", hs); form.addRow("Method:", mt)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            nw, nh = ws.value(), hs.value()
            rs = {"Lanczos": Image.LANCZOS, "Bilinear": Image.BILINEAR,
                  "Bicubic": Image.BICUBIC, "Nearest": Image.NEAREST}[mt.currentText()]
            self.history.save_state(self.layers, self.active_layer_index, "Resize Image")
            for l in self.layers: l.image = l.image.resize((nw, nh), rs)
            self.canvas.clear_selection(); self.canvas.fit_in_view(); self.update_layer_panel()

    def rotate_image(self, deg):
        if not self.layers: return
        self.history.save_state(self.layers, self.active_layer_index, f"Rotate {deg}°")
        for l in self.layers: l.image = l.image.rotate(-deg, expand=True, fillcolor=(0, 0, 0, 0))
        self.canvas.clear_selection(); self.canvas.fit_in_view(); self.update_layer_panel()

    def flip_image(self, d):
        if not self.layers: return
        self.history.save_state(self.layers, self.active_layer_index, "Flip")
        for l in self.layers:
            l.image = ImageOps.mirror(l.image) if d == "h" else ImageOps.flip(l.image)
        self.canvas.update()

    def flatten_image(self):
        if not self.layers: return
        self.history.save_state(self.layers, self.active_layer_index, "Flatten")
        self.layers = [Layer("Background", image=self.get_composite())]
        self.active_layer_index = 0; self.update_layer_panel(); self.canvas.update()

    def merge_down(self):
        idx = self.active_layer_index
        if idx <= 0 or idx >= len(self.layers): return
        self.history.save_state(self.layers, self.active_layer_index, "Merge Down")
        top, bot = self.layers[idx], self.layers[idx - 1]
        result = bot.image.copy()
        if top.visible:
            img = top.image.copy()
            if top.opacity < 255:
                r, g, b, a = img.split()
                a = a.point(lambda x: int(x * top.opacity / 255))
                img = Image.merge("RGBA", (r, g, b, a))
            result = self._blend(result, img, top.blend_mode)
        bot.image = result; bot.name = f"{bot.name}+{top.name}"
        del self.layers[idx]; self.active_layer_index = idx - 1
        self.update_layer_panel(); self.canvas.update()

    def crop_to_selection(self):
        if self.canvas.selection_mask:
            arr = np.array(self.canvas.selection_mask); ys, xs = np.where(arr > 127)
            if len(xs) > 0:
                self._do_crop(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        elif self.canvas.selection_rect:
            r = self.canvas.selection_rect
            self._do_crop(int(r.x()), int(r.y()), int(r.x() + r.width()), int(r.y() + r.height()))

    # ── Layer Mask methods ────────────────────────────────────────────────────
    def mask_from_selection(self):
        """Create/replace mask from current selection."""
        layer = self.active_layer()
        if not layer: return
        sel = self.canvas.selection_mask
        if sel is None:
            # No selection → reveal all
            self.history.save_state(self.layers, self.active_layer_index, "Add Mask from Selection")
            layer.add_mask("white")
        else:
            self.history.save_state(self.layers, self.active_layer_index, "Mask from Selection")
            layer.mask_from_selection(sel)
        layer.editing_mask = False
        self.update_layer_panel(); self.canvas.update()
        self._status("Mask created from selection")

    def mask_to_selection(self):
        """Load mask as selection."""
        layer = self.active_layer()
        if not layer or layer.mask is None: return
        self.canvas.set_selection_mask(layer.mask.copy())
        self.canvas.update()
        self._status("Mask loaded as selection")

    def mask_invert(self):
        """Invert the active layer mask."""
        layer = self.active_layer()
        if not layer or layer.mask is None: return
        self.history.save_state(self.layers, self.active_layer_index, "Invert Mask")
        layer.mask = ImageChops.invert(layer.mask)
        self.canvas.update(); self.update_layer_panel()

    def toggle_quick_mask(self):
        if self.quick_mask_active:
            self.canvas.quick_mask_exit()
        else:
            self.canvas.quick_mask_enter()

    def selection_by_color_dialog(self):
        """Prompt user for a pixel pick to do Select by Color."""
        self._set_tool("select-color")
        self._status("Select by Color — click a color on the canvas")

    def _sel_mode_act(self, mode):
        self.sel_mode = mode
        if hasattr(self, "options_bar") and hasattr(self.options_bar, "_selmode_btns"):
            for mid, btn in self.options_bar._selmode_btns.items():
                btn.setChecked(mid == mode)
        self._status(f"Selection mode: {mode}")

    # ── Transform tool entry points ──────────────────────────────────────────
    def enter_free_transform(self):
        """Activate Free Transform tool and enter transform mode."""
        self._set_tool("transform")
        if self.active_layer():
            self.canvas.xform_enter()
            self.options_bar.update_for_tool("transform")

    def enter_perspective(self):
        """Activate Perspective tool and enter perspective mode."""
        self._set_tool("perspective")
        if self.active_layer():
            self.canvas.persp_enter()
            self.options_bar.update_for_tool("perspective")

    def flip_layer(self, direction):
        """Flip active layer pixels (non-transform, immediate)."""
        layer = self.active_layer()
        if not layer or layer.locked: return
        self.history.save_state(self.layers, self.active_layer_index, "Flip Layer")
        if direction == "h":
            layer.image = layer.image.transpose(Image.FLIP_LEFT_RIGHT)
        else:
            layer.image = layer.image.transpose(Image.FLIP_TOP_BOTTOM)
        self.canvas.update(); self.update_layer_panel()

    def rotate_layer(self, degrees):
        """Rotate active layer pixels in-place (crops to canvas size)."""
        layer = self.active_layer()
        if not layer or layer.locked: return
        self.history.save_state(self.layers, self.active_layer_index, f"Rotate {degrees}°")
        rotated = layer.image.rotate(-degrees, expand=False, resample=Image.BICUBIC)
        layer.image = rotated
        self.canvas.update(); self.update_layer_panel()

    def apply_crop(self):
        if self.canvas.crop_rect is not None:
            r = self.canvas.crop_rect
            self._do_crop(int(r.x()), int(r.y()), int(r.x() + r.width()), int(r.y() + r.height()))
            self.canvas.crop_rect = None
            self.canvas.update()
            self._status(f"Cropped to {int(r.width())} × {int(r.height())} px")
            self.options_bar.update_for_tool(self.current_tool)

    def _do_crop(self, x1, y1, x2, y2):
        if not self.layers: return
        iw, ih = self.layers[0].image.size
        # Clamp to image bounds and ensure minimum 1×1
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(iw, x2), min(ih, y2)
        if x2 - x1 < 1 or y2 - y1 < 1:
            self._status("Crop area too small"); return
        self.history.save_state(self.layers, self.active_layer_index, "Crop")
        for l in self.layers: l.image = l.image.crop((x1, y1, x2, y2))
        self.canvas.clear_selection(); self.canvas.fit_in_view(); self.update_layer_panel()

    # ── Text ──────────────────────────────────────────────────────────────────
    def insert_text_at(self, x, y):
        dlg = QDialog(self); dlg.setWindowTitle("Insert Text")
        dlg.setMinimumWidth(dp(380))
        form = QFormLayout(dlg); form.setSpacing(dp(8))
        te = QTextEdit(); te.setPlaceholderText("Enter text…")
        te.setFixedHeight(dp(80)); form.addRow("Text:", te)

        # Use values from OptionsBar if set, else defaults
        fs = QSpinBox(); fs.setRange(4, 500)
        fs.setValue(getattr(self, "text_size", 36)); form.addRow("Size (px):", fs)

        from PyQt5.QtGui import QFontDatabase
        fam_combo = QComboBox()
        for fam in sorted(QFontDatabase().families()):
            fam_combo.addItem(fam)
        default_fam = getattr(self, "text_font_family", "Arial")
        idx = fam_combo.findText(default_fam)
        if idx >= 0: fam_combo.setCurrentIndex(idx)
        form.addRow("Font:", fam_combo)

        style_row = QHBoxLayout()
        bc = QCheckBox("Bold"); bc.setChecked(getattr(self, "text_bold", False))
        ic = QCheckBox("Italic"); ic.setChecked(getattr(self, "text_italic", False))
        aa = QCheckBox("Anti-alias"); aa.setChecked(True)
        style_row.addWidget(bc); style_row.addWidget(ic); style_row.addWidget(aa)
        style_row.addStretch()
        form.addRow("Style:", style_row)

        # Color button
        color_btn = QPushButton("  ")
        color_btn.setFixedSize(dp(40), dp(22))
        color_btn.setStyleSheet(f"background:{self.fg_color.name()}; border:1px solid {C.BORDER};")
        _text_color = [QColor(self.fg_color)]
        def _pick_color():
            c = QColorDialog.getColor(_text_color[0], dlg, "Text Color")
            if c.isValid():
                _text_color[0] = c
                color_btn.setStyleSheet(f"background:{c.name()}; border:1px solid {C.BORDER};")
        color_btn.clicked.connect(_pick_color)
        form.addRow("Color:", color_btn)

        op_spin = QSpinBox(); op_spin.setRange(0, 100); op_spin.setSuffix("%")
        op_spin.setValue(self.brush_opacity * 100 // 255); form.addRow("Opacity:", op_spin)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            text = te.toPlainText()
            if not text: return
            self.history.save_state(self.layers, self.active_layer_index, "Text")
            l = self.active_layer()
            if not l: return
            draw = ImageDraw.Draw(l.image)
            sz = fs.value()
            family = fam_combo.currentText()
            # Try to load font with full style
            font = None
            try:
                from PyQt5.QtGui import QFontDatabase
                fdb = QFontDatabase()
                style = ""
                if bc.isChecked() and ic.isChecked(): style = "Bold Italic"
                elif bc.isChecked(): style = "Bold"
                elif ic.isChecked(): style = "Italic"
                font_path = fdb.applicationFontFamilies(fdb.addApplicationFont(""))
                # Try Windows/Linux font paths
                import platform
                win_dirs = [
                    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
                    os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts"),
                ]
                linux_dirs = ["/usr/share/fonts", "/usr/local/share/fonts",
                              os.path.expanduser("~/.local/share/fonts")]
                font_dirs = win_dirs + linux_dirs
                # Search for font file
                fname_variants = []
                stem = family.lower().replace(" ", "").replace("-", "")
                if bc.isChecked() and ic.isChecked():
                    fname_variants = [f"{stem}bolditalic", f"{stem}bi", f"{stem}boldoblique"]
                elif bc.isChecked():
                    fname_variants = [f"{stem}bold", f"{stem}bd", f"{stem}b"]
                elif ic.isChecked():
                    fname_variants = [f"{stem}italic", f"{stem}i", f"{stem}oblique"]
                else:
                    fname_variants = [stem, f"{stem}regular", f"{stem}r"]
                found_path = None
                for d in font_dirs:
                    if not os.path.isdir(d): continue
                    for fn in os.listdir(d):
                        fnl = fn.lower().replace(" ", "").replace("-", "").replace("_", "")
                        for v in fname_variants:
                            if fnl.startswith(v) and fnl.endswith((".ttf", ".otf")):
                                found_path = os.path.join(d, fn); break
                        if found_path: break
                    if found_path: break
                if found_path:
                    font = ImageFont.truetype(found_path, sz)
            except Exception:
                pass
            if font is None:
                # Fallback chain
                for candidate in ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
                                   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
                    try:
                        font = ImageFont.truetype(candidate, sz); break
                    except Exception:
                        pass
            if font is None:
                font = ImageFont.load_default()
            opacity = op_spin.value() * 255 // 100
            tc = _text_color[0]
            color = (tc.red(), tc.green(), tc.blue(), opacity)
            draw.text((x, y), text, fill=color, font=font)
            self.canvas.update()
            self.update_layer_panel()

    # ── Adjustments ───────────────────────────────────────────────────────────
    def _slider_dialog(self, title, params):
        """Generic multi-slider dialog. params = [(label, min, max, default, scale), ...]"""
        dlg = QDialog(self); dlg.setWindowTitle(title)
        form = QFormLayout(dlg); sliders = []
        for label, mn, mx, default, _ in params:
            sl = QSlider(Qt.Horizontal); sl.setRange(mn, mx); sl.setValue(default)
            lbl = QLabel(str(default)); sl.valueChanged.connect(lambda v, lb=lbl: lb.setText(str(v)))
            row = QHBoxLayout(); row.addWidget(sl); row.addWidget(lbl)
            form.addRow(label, row); sliders.append(sl)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            return [sl.value() for sl in sliders]
        return None

    def adjust_brightness_contrast(self):
        vals = self._slider_dialog("Brightness / Contrast",
            [("Brightness:", -100, 100, 0, 1), ("Contrast:", -100, 100, 0, 1)])
        if vals:
            bv, cv = vals
            def apply(img):
                r = img
                if bv != 0: r = ImageEnhance.Brightness(r).enhance(1 + bv / 100)
                if cv != 0: r = ImageEnhance.Contrast(r).enhance(1 + cv / 100)
                return r
            self._apply_to_active(apply, "Brightness/Contrast")

    def adjust_hue_saturation(self):
        vals = self._slider_dialog("Hue / Saturation",
            [("Hue:", -180, 180, 0, 1), ("Saturation:", -100, 100, 0, 1), ("Lightness:", -100, 100, 0, 1)])
        if vals:
            hv, sv, lv = vals
            def apply(img):
                r, g, b, a = img.split(); rgb = Image.merge("RGB", (r, g, b))
                if sv != 0: rgb = ImageEnhance.Color(rgb).enhance(1 + sv / 100)
                if lv != 0: rgb = ImageEnhance.Brightness(rgb).enhance(1 + lv / 100)
                if hv != 0:
                    hsv = rgb.convert("HSV"); hc, sc, vc = hsv.split()
                    hc = hc.point(lambda x: (x + hv) % 256)
                    rgb = Image.merge("HSV", (hc, sc, vc)).convert("RGB")
                rr, gg, bb = rgb.split(); return Image.merge("RGBA", (rr, gg, bb, a))
            self._apply_to_active(apply, "Hue/Saturation")

    def adjust_levels(self):
        dlg = QDialog(self); dlg.setWindowTitle("Levels"); form = QFormLayout(dlg)
        bsp = QSpinBox(); bsp.setRange(0, 254); bsp.setValue(0)
        wsp = QSpinBox(); wsp.setRange(1, 255); wsp.setValue(255)
        gsp = QDoubleSpinBox(); gsp.setRange(0.1, 10.0); gsp.setValue(1.0); gsp.setSingleStep(0.1)
        form.addRow("Black Point:", bsp); form.addRow("White Point:", wsp); form.addRow("Gamma:", gsp)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            bp, wp, gm = bsp.value(), wsp.value(), gsp.value()
            def apply(img):
                r, g, b, a = img.split()
                def lv(ch):
                    return ch.point(lambda x: int(255 * max(0, min(1, ((x - bp) / max(1, wp - bp)))) ** (1 / gm)))
                return Image.merge("RGBA", (lv(r), lv(g), lv(b), a))
            self._apply_to_active(apply, "Levels")

    def adjust_curves(self):
        dlg = QDialog(self); dlg.setWindowTitle("Curves"); form = QFormLayout(dlg)
        form.addRow(QLabel("Adjust shadows / midtones / highlights"))
        sh = QSlider(Qt.Horizontal); sh.setRange(-100, 100); sh.setValue(0)
        md = QSlider(Qt.Horizontal); md.setRange(-100, 100); md.setValue(0)
        hi = QSlider(Qt.Horizontal); hi.setRange(-100, 100); hi.setValue(0)
        ch = QComboBox(); ch.addItems(["RGB", "Red", "Green", "Blue"])
        form.addRow("Shadows:", sh); form.addRow("Midtones:", md); form.addRow("Highlights:", hi)
        form.addRow("Channel:", ch)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            sv, mv, hv = sh.value(), md.value(), hi.value()
            channel = ch.currentText()
            lut = []
            for i in range(256):
                t = i / 255.0; val = i
                if t < 0.33: val += sv * (0.33 - t) / 0.33 * 0.5
                elif t < 0.66: val += mv * 0.5
                else: val += hv * (t - 0.66) / 0.34 * 0.5
                lut.append(max(0, min(255, int(val))))
            def apply(img):
                r, g, b, a = img.split()
                if channel in ("RGB", "Red"): r = r.point(lut)
                if channel in ("RGB", "Green"): g = g.point(lut)
                if channel in ("RGB", "Blue"): b = b.point(lut)
                return Image.merge("RGBA", (r, g, b, a))
            self._apply_to_active(apply, "Curves")

    def adjust_gamma(self):
        dlg = QDialog(self); dlg.setWindowTitle("Gamma"); form = QFormLayout(dlg)
        rg = QDoubleSpinBox(); rg.setRange(0.1, 5.0); rg.setValue(1.0); rg.setSingleStep(0.05)
        gg = QDoubleSpinBox(); gg.setRange(0.1, 5.0); gg.setValue(1.0); gg.setSingleStep(0.05)
        bg = QDoubleSpinBox(); bg.setRange(0.1, 5.0); bg.setValue(1.0); bg.setSingleStep(0.05)
        form.addRow("Red:", rg); form.addRow("Green:", gg); form.addRow("Blue:", bg)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            rv, gv, bv = rg.value(), gg.value(), bg.value()
            def apply(img):
                r, g, b, a = img.split()
                r = r.point(lambda x: int(255 * (x / 255) ** (1 / rv)))
                g = g.point(lambda x: int(255 * (x / 255) ** (1 / gv)))
                b = b.point(lambda x: int(255 * (x / 255) ** (1 / bv)))
                return Image.merge("RGBA", (r, g, b, a))
            self._apply_to_active(apply, "Gamma")

    def adjust_vibrance(self):
        v, ok = QInputDialog.getInt(self, "Vibrance", "Amount (−100 to 100):", 30, -100, 100)
        if ok:
            amt = v / 100.0
            def apply(img):
                arr = np.array(img).astype(np.float64)
                for py in range(arr.shape[0]):
                    for px in range(arr.shape[1]):
                        rv, gv, bv = arr[py, px, :3]
                        mx, mn = max(rv, gv, bv), min(rv, gv, bv)
                        sat = 0 if mx == 0 else (mx - mn) / mx
                        boost = amt * (1 - sat) * (1 if sat < 0.5 else 0.5)
                        avg = (rv + gv + bv) / 3
                        for c in range(3):
                            arr[py, px, c] = max(0, min(255, arr[py, px, c] + (arr[py, px, c] - avg) * boost))
                return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
            self._apply_to_active(apply, "Vibrance")

    def adjust_threshold(self):
        v, ok = QInputDialog.getInt(self, "Threshold", "Level (0–255):", 128, 0, 255)
        if ok:
            def apply(img):
                r, g, b, a = img.split()
                gray = img.convert("L"); bw = gray.point(lambda x: 255 if x > v else 0)
                return Image.merge("RGBA", (bw, bw, bw, a))
            self._apply_to_active(apply, "Threshold")

    def invert_colors(self):
        def apply(img):
            r, g, b, a = img.split()
            return Image.merge("RGBA", (ImageChops.invert(r), ImageChops.invert(g), ImageChops.invert(b), a))
        self._apply_to_active(apply, "Invert")

    def grayscale(self):
        def apply(img):
            r, g, b, a = img.split(); gray = img.convert("L").convert("RGB")
            rr, gg, bb = gray.split(); return Image.merge("RGBA", (rr, gg, bb, a))
        self._apply_to_active(apply, "Grayscale")

    def auto_contrast(self):
        def apply(img):
            r, g, b, a = img.split()
            rgb = ImageOps.autocontrast(Image.merge("RGB", (r, g, b)))
            rr, gg, bb = rgb.split(); return Image.merge("RGBA", (rr, gg, bb, a))
        self._apply_to_active(apply, "Auto Contrast")

    def color_balance(self):
        vals = self._slider_dialog("Color Balance",
            [("Red:", -100, 100, 0, 1), ("Green:", -100, 100, 0, 1), ("Blue:", -100, 100, 0, 1)])
        if vals:
            rv, gv, bv = vals
            def apply(img):
                r, g, b, a = img.split()
                r = r.point(lambda x: max(0, min(255, x + rv)))
                g = g.point(lambda x: max(0, min(255, x + gv)))
                b = b.point(lambda x: max(0, min(255, x + bv)))
                return Image.merge("RGBA", (r, g, b, a))
            self._apply_to_active(apply, "Color Balance")

    def sepia(self):
        def apply(img):
            arr = np.array(img).astype(np.float64)
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            tr = np.clip(0.393 * r + 0.769 * g + 0.189 * b, 0, 255)
            tg = np.clip(0.349 * r + 0.686 * g + 0.168 * b, 0, 255)
            tb = np.clip(0.272 * r + 0.534 * g + 0.131 * b, 0, 255)
            arr[:, :, 0], arr[:, :, 1], arr[:, :, 2] = tr, tg, tb
            return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        self._apply_to_active(apply, "Sepia")

    # ── Filters ───────────────────────────────────────────────────────────────
    def gaussian_blur(self):
        v, ok = QInputDialog.getDouble(self, "Gaussian Blur", "Radius:", 3.0, 0.1, 100.0, 1)
        if ok: self._apply_to_active(lambda img: img.filter(ImageFilter.GaussianBlur(v)), "Gaussian Blur")

    def box_blur(self):
        v, ok = QInputDialog.getInt(self, "Box Blur", "Radius:", 3, 1, 100)
        if ok: self._apply_to_active(lambda img: img.filter(ImageFilter.BoxBlur(v)), "Box Blur")

    def motion_blur(self):
        v, ok = QInputDialog.getInt(self, "Motion Blur", "Size:", 10, 1, 100)
        if ok:
            k = [0] * (v * v); c = v // 2
            for i in range(v): k[c * v + i] = 1
            self._apply_to_active(lambda img: img.filter(ImageFilter.Kernel((v, v), k, scale=v)), "Motion Blur")

    def sharpen(self):
        self._apply_to_active(lambda img: img.filter(ImageFilter.SHARPEN), "Sharpen")

    def unsharp_mask(self):
        dlg = QDialog(self); dlg.setWindowTitle("Unsharp Mask"); form = QFormLayout(dlg)
        r = QDoubleSpinBox(); r.setRange(0.1, 100); r.setValue(2.0)
        pct = QSpinBox(); pct.setRange(1, 500); pct.setValue(150)
        th = QSpinBox(); th.setRange(0, 255); th.setValue(3)
        form.addRow("Radius:", r); form.addRow("Amount %:", pct); form.addRow("Threshold:", th)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            self._apply_to_active(
                lambda img: img.filter(ImageFilter.UnsharpMask(r.value(), pct.value(), th.value())),
                "Unsharp Mask")

    def edge_detect(self):
        self._apply_to_active(lambda img: img.filter(ImageFilter.FIND_EDGES), "Edge Detect")

    def emboss(self):
        self._apply_to_active(lambda img: img.filter(ImageFilter.EMBOSS), "Emboss")

    def contour(self):
        self._apply_to_active(lambda img: img.filter(ImageFilter.CONTOUR), "Contour")

    def posterize(self):
        v, ok = QInputDialog.getInt(self, "Posterize", "Levels (2–8):", 4, 2, 8)
        if ok:
            def ap(img):
                r, g, b, a = img.split()
                rgb = ImageOps.posterize(Image.merge("RGB", (r, g, b)), v)
                rr, gg, bb = rgb.split(); return Image.merge("RGBA", (rr, gg, bb, a))
            self._apply_to_active(ap, "Posterize")

    def solarize(self):
        v, ok = QInputDialog.getInt(self, "Solarize", "Threshold:", 128, 0, 255)
        if ok:
            def ap(img):
                r, g, b, a = img.split()
                rgb = ImageOps.solarize(Image.merge("RGB", (r, g, b)), v)
                rr, gg, bb = rgb.split(); return Image.merge("RGBA", (rr, gg, bb, a))
            self._apply_to_active(ap, "Solarize")

    def pixelate(self):
        v, ok = QInputDialog.getInt(self, "Pixelate", "Block size:", 8, 2, 100)
        if ok:
            def ap(img):
                w, h = img.size
                return img.resize((w // v, h // v), Image.NEAREST).resize((w, h), Image.NEAREST)
            self._apply_to_active(ap, "Pixelate")

    def add_noise(self):
        v, ok = QInputDialog.getInt(self, "Add Noise", "Amount (0–200):", 25, 0, 200)
        if ok:
            def ap(img):
                arr = np.array(img).astype(np.float64)
                noise = np.random.normal(0, v, arr[:, :, :3].shape)
                arr[:, :, :3] = np.clip(arr[:, :, :3] + noise, 0, 255)
                return Image.fromarray(arr.astype(np.uint8), "RGBA")
            self._apply_to_active(ap, "Add Noise")

    def vignette(self):
        dlg = QDialog(self); dlg.setWindowTitle("Vignette"); form = QFormLayout(dlg)
        amt = QSlider(Qt.Horizontal); amt.setRange(0, 100); amt.setValue(50)
        rad = QSlider(Qt.Horizontal); rad.setRange(10, 100); rad.setValue(70)
        form.addRow("Amount:", amt); form.addRow("Radius %:", rad)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() == QDialog.Accepted:
            amount, radius = amt.value() / 100.0, rad.value() / 100.0
            def ap(img):
                arr = np.array(img).astype(np.float64)
                h, w = arr.shape[:2]; cx, cy = w / 2, h / 2
                max_r = math.sqrt(cx * cx + cy * cy)
                Y, X = np.ogrid[:h, :w]
                dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / max_r
                vig = np.clip(1 - (dist - radius) / (1 - radius), 0, 1) ** 2
                vig = 1 - amount * (1 - vig)
                for ch in range(3): arr[:, :, ch] = arr[:, :, ch] * vig
                return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
            self._apply_to_active(ap, "Vignette")

    # ── View ──────────────────────────────────────────────────────────────────
    def _zoom(self, f):
        self.canvas.zoom = max(0.05, min(50.0, self.canvas.zoom * f))
        self.canvas.zoom_changed.emit(self.canvas.zoom, self.canvas.pan_offset.x(), self.canvas.pan_offset.y())
        self.canvas.update()

    def _set_zoom(self, v):
        self.canvas.zoom = max(0.05, min(50.0, v))
        self.canvas.zoom_changed.emit(self.canvas.zoom, self.canvas.pan_offset.x(), self.canvas.pan_offset.y())
        self.canvas.update()

    def toggle_grid(self):
        self.canvas._show_grid = not self.canvas._show_grid
        self.canvas.update()
        self._status(f"Grid {'on' if self.canvas._show_grid else 'off'}")

    def _add_h_guide(self):
        if not self.layers: return
        ih = self.layers[0].image.height
        val, ok = QInputDialog.getInt(self, "Horizontal Guide",
                                      "Y position (pixels):", ih // 2, 0, ih)
        if ok:
            self.canvas.add_guide('h', val)

    def _add_v_guide(self):
        if not self.layers: return
        iw = self.layers[0].image.width
        val, ok = QInputDialog.getInt(self, "Vertical Guide",
                                      "X position (pixels):", iw // 2, 0, iw)
        if ok:
            self.canvas.add_guide('v', val)

    def toggle_rulers(self):
        self._show_rulers = not self._show_rulers
        if hasattr(self, "_ruler_h"):
            self._ruler_h.setVisible(self._show_rulers)
        if hasattr(self, "_ruler_v"):
            self._ruler_v.setVisible(self._show_rulers)
        if hasattr(self, "_ruler_corner"):
            self._ruler_corner.setVisible(self._show_rulers)

    # ── Auto Levels ───────────────────────────────────────────────────────────
    def auto_levels(self):
        def ap(img):
            arr = np.array(img).astype(np.float32)
            for ch in range(3):
                ch_data = arr[:, :, ch]
                lo, hi = ch_data.min(), ch_data.max()
                if hi > lo:
                    arr[:, :, ch] = (ch_data - lo) / (hi - lo) * 255
            return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        self._apply_to_active(ap, "Auto Levels")

    # ── New Filters ───────────────────────────────────────────────────────────
    def filter_oil_paint(self):
        dlg = QDialog(self); dlg.setWindowTitle("Oil Paint"); form = QFormLayout(dlg)
        radius = QSpinBox(); radius.setRange(1, 6); radius.setValue(3)
        levels = QSpinBox(); levels.setRange(4, 32); levels.setValue(16)
        form.addRow("Radius:", radius); form.addRow("Levels:", levels)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() != QDialog.Accepted: return
        r, lvl = radius.value(), levels.value()
        def ap(img):
            arr = np.array(img).astype(np.float32)
            h, w = arr.shape[:2]
            # Compute intensity bin index per pixel
            lum = arr[:, :, :3].mean(axis=2)
            bin_idx = (lum * (lvl / 256.0)).clip(0, lvl - 1).astype(np.int32)
            result = arr.copy()
            pad = r
            # Pad arrays
            bin_p = np.pad(bin_idx, pad, mode="edge")
            rgb_p = np.pad(arr[:, :, :3], ((pad, pad), (pad, pad), (0, 0)), mode="edge")
            d = 2 * r + 1
            # Build sliding window view: shape (h, w, d*d)
            from numpy.lib.stride_tricks import as_strided
            sh = bin_p.strides
            wins_bin = as_strided(bin_p, shape=(h, w, d, d),
                                  strides=(sh[0], sh[1], sh[0], sh[1])).reshape(h, w, d * d)
            # For each of 3 channels
            for ch in range(3):
                s = rgb_p[:, :, ch].strides
                wins_ch = as_strided(rgb_p[:, :, ch], shape=(h, w, d, d),
                                     strides=(s[0], s[1], s[0], s[1])).reshape(h, w, d * d)
                # One-hot accumulate per bin
                out_ch = np.zeros((h, w), dtype=np.float32)
                out_cnt = np.zeros((h, w), dtype=np.float32)
                for b in range(lvl):
                    mask = (wins_bin == b)          # (h, w, d*d)
                    cnt = mask.sum(axis=2)           # (h, w)
                    val = (wins_ch * mask).sum(axis=2)
                    # Update where this bin is the new max
                    update = cnt > out_cnt
                    out_cnt = np.where(update, cnt, out_cnt)
                    out_ch = np.where(update, val / np.maximum(cnt, 1), out_ch)
                result[:, :, ch] = out_ch
            result[:, :, 3] = arr[:, :, 3]  # preserve alpha
            return Image.fromarray(result.clip(0, 255).astype(np.uint8), "RGBA")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._apply_to_active(ap, "Oil Paint")
        finally:
            QApplication.restoreOverrideCursor()

    def filter_halftone(self):
        v, ok = QInputDialog.getInt(self, "Halftone", "Dot size (px):", 6, 2, 20)
        if not ok: return
        sz = v
        def ap(img):
            w, h = img.size
            rgb = np.array(img.convert("RGB"))
            out = Image.new("RGB", (w, h), (255, 255, 255))
            draw = ImageDraw.Draw(out)
            for y in range(0, h, sz):
                for x in range(0, w, sz):
                    cell = rgb[y:y+sz, x:x+sz]
                    avg = cell.mean() / 255.0
                    radius = (sz / 2) * (1 - avg)
                    cx, cy = x + sz / 2, y + sz / 2
                    if radius > 0.3:
                        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(0, 0, 0))
            return out.convert("RGBA")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._apply_to_active(ap, "Halftone")
        finally:
            QApplication.restoreOverrideCursor()

    def filter_duotone(self):
        dlg = QDialog(self); dlg.setWindowTitle("Duotone"); form = QFormLayout(dlg)
        from PyQt5.QtWidgets import QPushButton as QPB
        shadow_c = ["#1a1a2e"]
        high_c = ["#e94560"]
        def pick_s():
            c = QColorDialog.getColor(QColor(shadow_c[0]), dlg, "Shadow Color")
            if c.isValid(): shadow_c[0] = c.name()
        def pick_h():
            c = QColorDialog.getColor(QColor(high_c[0]), dlg, "Highlight Color")
            if c.isValid(): high_c[0] = c.name()
        sb = QPB("Shadow Color"); sb.clicked.connect(pick_s)
        hb = QPB("Highlight Color"); hb.clicked.connect(pick_h)
        form.addRow("Shadow:", sb); form.addRow("Highlight:", hb)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() != QDialog.Accepted: return
        sc = QColor(shadow_c[0]); hc = QColor(high_c[0])
        sr, sg, sb2 = sc.red(), sc.green(), sc.blue()
        hr, hg, hb2 = hc.red(), hc.green(), hc.blue()
        def ap(img):
            arr = np.array(img.convert("RGBA")).astype(np.float32)
            lum = (0.299 * arr[:,:,0] + 0.587 * arr[:,:,1] + 0.114 * arr[:,:,2]) / 255.0
            arr[:,:,0] = sr + (hr - sr) * lum
            arr[:,:,1] = sg + (hg - sg) * lum
            arr[:,:,2] = sb2 + (hb2 - sb2) * lum
            return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        self._apply_to_active(ap, "Duotone")

    def filter_tilt_shift(self):
        dlg = QDialog(self); dlg.setWindowTitle("Tilt Shift"); form = QFormLayout(dlg)
        focus_y = QSpinBox(); focus_y.setRange(0, 100); focus_y.setValue(50); focus_y.setSuffix("%")
        focus_w = QSpinBox(); focus_w.setRange(5, 60); focus_w.setValue(20); focus_w.setSuffix("%")
        blur_r = QSpinBox(); blur_r.setRange(1, 25); blur_r.setValue(8)
        form.addRow("Focus Y:", focus_y); form.addRow("Focus Width:", focus_w); form.addRow("Blur:", blur_r)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() != QDialog.Accepted: return
        fy, fw, br = focus_y.value() / 100.0, focus_w.value() / 100.0, blur_r.value()
        def ap(img):
            w, h = img.size
            blurred = img.filter(ImageFilter.GaussianBlur(br))
            orig_arr = np.array(img).astype(np.float32)
            blur_arr = np.array(blurred).astype(np.float32)
            # Build per-row blend factor: 0 = sharp, 1 = fully blurred
            blend = np.zeros(h, dtype=np.float32)
            half_band = fw / 2.0
            falloff = max(0.5 - fw / 2.0, 0.001)
            for row in range(h):
                ny = row / h
                dist = abs(ny - fy)
                blend[row] = float(np.clip((dist - half_band) / falloff, 0.0, 1.0))
            # Apply blend: expand to (h, 1, 1) for broadcasting
            alpha = blend.reshape(h, 1, 1)
            result = orig_arr * (1.0 - alpha) + blur_arr * alpha
            return Image.fromarray(result.clip(0, 255).astype(np.uint8), "RGBA")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._apply_to_active(ap, "Tilt Shift")
        finally:
            QApplication.restoreOverrideCursor()

    def filter_chromatic_aberration(self):
        off, ok = QInputDialog.getInt(self, "Chromatic Aberration", "Offset (px):", 4, 1, 20)
        if not ok: return
        def ap(img):
            arr = np.array(img).copy()
            w = arr.shape[1]
            # Shift red right, blue left
            if off < w:
                arr[:, off:, 0] = arr[:, :w - off, 0]   # R shift right
                arr[:, :w - off, 2] = arr[:, off:, 2]   # B shift left
            return Image.fromarray(arr, "RGBA")
        self._apply_to_active(ap, "Chromatic Aberration")

    def filter_noise_gen(self):
        dlg = QDialog(self); dlg.setWindowTitle("Generate Noise"); form = QFormLayout(dlg)
        noise_type = QComboBox(); noise_type.addItems(["Uniform", "Gaussian", "Salt & Pepper"])
        amt = QSlider(Qt.Horizontal); amt.setRange(1, 100); amt.setValue(30)
        mono = QCheckBox("Monochrome"); mono.setChecked(True)
        form.addRow("Type:", noise_type); form.addRow("Amount:", amt); form.addRow("", mono)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject); form.addRow(btns)
        if dlg.exec_() != QDialog.Accepted: return
        nt, am, mn = noise_type.currentText(), amt.value() / 100.0, mono.isChecked()
        def ap(img):
            arr = np.array(img).astype(np.float32)
            h, w = arr.shape[:2]
            strength = am * 128
            if nt == "Salt & Pepper":
                mask = np.random.random((h, w)) < am * 0.15
                vals = np.where(np.random.random((h, w)) > 0.5, 255.0, 0.0)
                for ch in range(3):
                    arr[:, :, ch] = np.where(mask, vals, arr[:, :, ch])
            elif nt == "Gaussian":
                if mn:
                    n = np.random.normal(0, strength, (h, w))
                    for ch in range(3): arr[:, :, ch] += n
                else:
                    arr[:, :, :3] += np.random.normal(0, strength, (h, w, 3))
            else:  # Uniform
                if mn:
                    n = (np.random.random((h, w)) - 0.5) * 2 * strength
                    for ch in range(3): arr[:, :, ch] += n
                else:
                    arr[:, :, :3] += (np.random.random((h, w, 3)) - 0.5) * 2 * strength
            return Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
        self._apply_to_active(ap, "Noise Generator")

    # ── AI Tools ──────────────────────────────────────────────────────────────
    def ai_remove_background(self):
        """Remove background using rembg (auto-installs, uses u2net ONNX model)."""
        layer = self.active_layer()
        if not layer:
            QMessageBox.information(self, "AI Remove BG", "No active layer."); return

        # Try importing rembg
        try:
            import rembg
        except ImportError:
            progress = AIProgressDialog("Installing rembg...", self)
            progress.show(); QApplication.processEvents()
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "rembg", "-q", "--break-system-packages"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                progress.close()
                import rembg
            except Exception as ex:
                progress.close()
                QMessageBox.critical(self, "Install Failed",
                    f"Could not install rembg:\n{ex}\n\nRun: pip install rembg"); return

        progress = AIProgressDialog("Removing Background", self)
        progress.set_message("Running AI background removal (first run downloads model ~170MB)...")
        progress.set_progress(10)
        progress.show(); QApplication.processEvents()

        try:
            self.history.save_state(self.layers, self.active_layer_index, "AI BG Remove")
            # Convert to PNG bytes
            import io
            buf = io.BytesIO()
            layer.image.save(buf, format="PNG")
            buf.seek(0)
            progress.set_progress(30, "Processing with AI model...")
            QApplication.processEvents()
            result_bytes = rembg.remove(buf.read())
            progress.set_progress(80, "Applying result...")
            QApplication.processEvents()
            result_img = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
            layer.image = result_img.resize(layer.image.size, Image.LANCZOS)
            self.canvas.update()
            self.update_layer_panel()
            progress.set_progress(100, "Done!")
            QApplication.processEvents()
            progress.close()
            self._status("Background removed (AI)")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "AI Error", f"Background removal failed:\n{e}")

    def ai_upscale(self, factor=2):
        """Smart upscale using Lanczos + adaptive sharpening."""
        layer = self.active_layer()
        if not layer:
            QMessageBox.information(self, "AI Upscale", "No active layer."); return
        w, h = layer.image.size
        new_w, new_h = w * factor, h * factor
        progress = AIProgressDialog(f"Smart Upscale {factor}x", self)
        progress.set_message(f"Resizing {w}x{h} → {new_w}x{new_h}...")
        progress.set_progress(0); progress.show(); QApplication.processEvents()
        try:
            self.history.save_state(self.layers, self.active_layer_index, f"Upscale {factor}x")
            # Step 1: Multi-pass Lanczos
            current = layer.image.copy()
            remaining = factor
            step = 0
            while remaining > 1:
                scale = 2 if remaining >= 2 else remaining
                nw = int(current.width * scale); nh = int(current.height * scale)
                current = current.resize((nw, nh), Image.LANCZOS)
                remaining /= scale; step += 1
                progress.set_progress(30 + step * 20, f"Upscale pass {step}")
                QApplication.processEvents()
            # Step 2: Adaptive unsharp mask
            progress.set_progress(70, "Applying adaptive sharpening...")
            QApplication.processEvents()
            current = current.filter(ImageFilter.UnsharpMask(radius=1.0, percent=50, threshold=2))
            layer.image = current
            self.canvas.update()
            self.update_layer_panel()
            progress.set_progress(100, "Done!")
            QApplication.processEvents()
            progress.close()
            self._status(f"Upscaled {factor}x → {new_w}x{new_h}")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "AI Error", f"Upscale failed:\n{e}")

    def ai_depth_map(self):
        """Generate depth map using luminance and edge analysis (local, instant)."""
        layer = self.active_layer()
        if not layer:
            QMessageBox.information(self, "AI Depth Map", "No active layer."); return

        # Try transformers first, fall back to local analysis
        progress = AIProgressDialog("Generating Depth Map", self)
        progress.set_message("Analyzing image depth...")
        progress.set_progress(10); progress.show(); QApplication.processEvents()

        try:
            self.history.save_state(self.layers, self.active_layer_index, "Depth Map")
            arr = np.array(layer.image.convert("RGB")).astype(np.float32)
            h, w = arr.shape[:2]
            progress.set_progress(30, "Computing depth channels...")
            QApplication.processEvents()

            # Local depth estimation: luminance + vertical gradient + edge distance
            lum = (arr[:,:,0] * 0.299 + arr[:,:,1] * 0.587 + arr[:,:,2] * 0.114)
            # Vertical gradient (things higher tend to be farther)
            vert = np.linspace(0, 255, h).reshape(-1, 1) * np.ones((1, w))
            # Saturation (more saturated = closer in natural photos)
            r, g, b2 = arr[:,:,0], arr[:,:,1], arr[:,:,2]
            mx = np.maximum(np.maximum(r, g), b2)
            mn = np.minimum(np.minimum(r, g), b2)
            sat = (mx - mn) / (mx + 1e-6) * 255

            depth = 0.4 * lum + 0.4 * (255 - vert) + 0.2 * sat

            progress.set_progress(60, "Applying plasma colormap...")
            QApplication.processEvents()
            # Normalize and apply plasma colormap
            mn_d, mx_d = depth.min(), depth.max()
            t = (depth - mn_d) / (mx_d - mn_d + 1e-6)
            out = np.zeros((h, w, 4), dtype=np.uint8)
            out[:,:,0] = np.clip((1.5 - abs(t - 0.75) * 4).clip(0, 1) * 255, 0, 255)
            out[:,:,1] = np.clip((1.5 - abs(t - 0.5) * 4).clip(0, 1) * 255, 0, 255)
            out[:,:,2] = np.clip((1.5 - abs(t - 0.25) * 4).clip(0, 1) * 255, 0, 255)
            out[:,:,3] = 220  # slightly transparent

            # Add as new layer
            depth_layer = Layer(f"Depth Map", layer.image.width, layer.image.height)
            depth_layer.image = Image.fromarray(out, "RGBA").resize(layer.image.size, Image.LANCZOS)
            depth_layer.opacity = 200
            depth_layer.blend_mode = "Normal"
            self.layers.append(depth_layer)
            self.active_layer_index = len(self.layers) - 1
            self.canvas.update()
            self.update_layer_panel()
            progress.set_progress(100, "Done!")
            QApplication.processEvents()
            progress.close()
            self._status("Depth map generated (added as new layer)")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "AI Error", f"Depth map failed:\n{e}")

    def ai_object_detect(self):
        """Detect regions of interest using color clustering and edge detection."""
        layer = self.active_layer()
        if not layer:
            QMessageBox.information(self, "AI Object Detect", "No active layer."); return

        progress = AIProgressDialog("Detecting Objects", self)
        progress.set_message("Analyzing image for regions of interest...")
        progress.set_progress(10); progress.show(); QApplication.processEvents()

        try:
            self.history.save_state(self.layers, self.active_layer_index, "Object Detect")
            arr = np.array(layer.image.convert("RGB"))
            h, w = arr.shape[:2]

            progress.set_progress(30, "Finding dominant color regions...")
            QApplication.processEvents()

            # Simple grid-based color region detection
            grid_r, grid_c = 3, 3
            cell_h, cell_w = h // grid_r, w // grid_c
            colors = ["#ff5555", "#55cc55", "#4488ff", "#ffcc44", "#cc55cc", "#55cccc"]
            det_layer = Layer("Object Regions", w, h)
            draw = ImageDraw.Draw(det_layer.image)

            detections = []
            for row in range(grid_r):
                for col in range(grid_c):
                    y0 = row * cell_h; x0 = col * cell_w
                    y1 = min(y0 + cell_h, h); x1 = min(x0 + cell_w, w)
                    cell = arr[y0:y1, x0:x1]
                    # Measure variance (interesting regions have high variance)
                    variance = float(cell.var())
                    if variance > 500:  # Only show interesting regions
                        detections.append((x0, y0, x1, y1, f"Region ({variance:.0f})", variance))

            progress.set_progress(70, "Drawing detection boxes...")
            QApplication.processEvents()
            for i, (x0, y0, x1, y1, label, score) in enumerate(detections):
                color_hex = colors[i % len(colors)]
                c = QColor(color_hex)
                fill_c = (c.red(), c.green(), c.blue(), 40)
                stroke_c = (c.red(), c.green(), c.blue(), 200)
                draw.rectangle([x0, y0, x1, y1], fill=fill_c, outline=stroke_c, width=2)
                try:
                    draw.text((x0 + 4, y0 + 4), label, fill=stroke_c)
                except Exception:
                    pass

            self.layers.append(det_layer)
            self.active_layer_index = len(self.layers) - 1
            self.canvas.update()
            self.update_layer_panel()
            progress.set_progress(100, "Done!")
            QApplication.processEvents()
            progress.close()
            self._status(f"Detected {len(detections)} regions of interest")
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "AI Error", f"Object detection failed:\n{e}")

    # ── Command Palette ───────────────────────────────────────────────────────
    def open_command_palette(self):
        commands = [
            # File
            ("New Image", "File", self.new_image),
            ("Open Image", "File", self.open_image),
            ("Save", "File", self.save_image),
            ("Save As", "File", self.save_image_as),
            ("Export PNG", "File", self.export_png),
            ("Copy to Clipboard", "File", self.copy_to_clipboard),
            ("Open from Clipboard", "File", self.open_from_clipboard),
            # Edit
            ("Undo", "Edit", self.undo),
            ("Redo", "Edit", self.redo),
            ("Select All", "Edit", self.select_all),
            ("Deselect", "Edit", self.deselect),
            ("Invert Selection", "Edit", self.invert_selection),
            # Image
            ("Resize Canvas", "Image", self.resize_canvas),
            ("Resize Image", "Image", self.resize_image),
            ("Rotate 90° CW", "Image", lambda: self.rotate_image(90)),
            ("Rotate 90° CCW", "Image", lambda: self.rotate_image(-90)),
            ("Flip Horizontal", "Image", lambda: self.flip_image("h")),
            ("Flip Vertical", "Image", lambda: self.flip_image("v")),
            ("Flatten Image", "Image", self.flatten_image),
            ("Merge Down", "Image", self.merge_down),
            ("Crop to Selection", "Image", self.crop_to_selection),
            # Adjustments
            ("Brightness / Contrast", "Adjust", self.adjust_brightness_contrast),
            ("Hue / Saturation", "Adjust", self.adjust_hue_saturation),
            ("Levels", "Adjust", self.adjust_levels),
            ("Curves", "Adjust", self.adjust_curves),
            ("Vibrance", "Adjust", self.adjust_vibrance),
            ("Threshold", "Adjust", self.adjust_threshold),
            ("Invert Colors", "Adjust", self.invert_colors),
            ("Grayscale", "Adjust", self.grayscale),
            ("Auto Contrast", "Adjust", self.auto_contrast),
            ("Auto Levels", "Adjust", self.auto_levels),
            ("Sepia", "Adjust", self.sepia),
            # Filters
            ("Gaussian Blur", "Filter", self.gaussian_blur),
            ("Motion Blur", "Filter", self.motion_blur),
            ("Sharpen", "Filter", self.sharpen),
            ("Unsharp Mask", "Filter", self.unsharp_mask),
            ("Edge Detect", "Filter", self.edge_detect),
            ("Emboss", "Filter", self.emboss),
            ("Vignette", "Filter", self.vignette),
            ("Oil Paint", "Filter", self.filter_oil_paint),
            ("Halftone", "Filter", self.filter_halftone),
            ("Duotone", "Filter", self.filter_duotone),
            ("Tilt Shift", "Filter", self.filter_tilt_shift),
            ("Chromatic Aberration", "Filter", self.filter_chromatic_aberration),
            ("Noise Generator", "Filter", self.filter_noise_gen),
            # AI
            ("AI Remove Background", "AI", self.ai_remove_background),
            ("AI Upscale 2x", "AI", lambda: self.ai_upscale(2)),
            ("AI Upscale 4x", "AI", lambda: self.ai_upscale(4)),
            ("AI Depth Map", "AI", self.ai_depth_map),
            ("AI Object Detection", "AI", self.ai_object_detect),
            # View
            ("Toggle Grid", "View", self.toggle_grid),
            ("Toggle Rulers", "View", self.toggle_rulers),
            ("Fit in Window", "View", self.canvas.fit_in_view),
            ("Zoom to 100%", "View", lambda: self._set_zoom(1.0)),
        ]
        dlg = CommandPaletteDialog(commands, self)
        dlg.exec_()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Space:
            self.canvas.setCursor(Qt.OpenHandCursor)
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            if self.current_tool == "crop" and self.canvas.crop_rect:
                self.apply_crop()
                return
        elif k == Qt.Key_Escape:
            if self.current_tool == "crop":
                self.canvas.crop_rect = None
                self.canvas.drawing = False
                self.canvas.update()
                self._status("Crop cancelled")
                return
        elif k == Qt.Key_BracketLeft:
            self.brush_size = max(1, self.brush_size - 2)
        elif k == Qt.Key_BracketRight:
            self.brush_size = min(500, self.brush_size + 2)
        elif k == Qt.Key_X:
            self.fg_color, self.bg_color = self.bg_color, self.fg_color
        # Note: Ctrl+C handled by Edit > Copy QAction (smart: selection or full image)
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space: self.canvas.setCursor(Qt.ArrowCursor)
        super().keyReleaseEvent(e)

    # ── SwiftShot Integration ─────────────────────────────────────────────────
    def get_final_pixmap(self):
        comp = self.get_composite()
        return pil_to_qpixmap(comp) if comp else QPixmap()

    def load_pixmap(self, pixmap):
        pil_img = qpixmap_to_pil(pixmap)
        self.layers = [Layer("Background", image=pil_img)]
        self.active_layer_index = 0; self.history = HistoryManager()
        self.canvas.clear_selection(); self.update_layer_panel(); self.canvas.fit_in_view()
        self.setWindowTitle(f"SwiftShot Editor — {pil_img.width}×{pil_img.height}")

    def open_from_clipboard(self):
        px = QApplication.clipboard().pixmap()
        if px and not px.isNull():
            self.load_pixmap(px)
        else:
            self._status("No image in clipboard")

    def copy_to_clipboard(self):
        px = self.get_final_pixmap()
        if px and not px.isNull():
            QApplication.clipboard().setPixmap(px); self._status("Copied to clipboard")

    def upload_imgur(self):
        try:
            from uploader import Uploader
            self._uploader = Uploader(self)
            self._uploader.upload_complete.connect(self._on_upload_complete)
            self._uploader.upload_to_imgur(self.get_final_pixmap())
        except ImportError:
            self._status("Uploader module not available")

    def _on_upload_complete(self, url):
        if url:
            QApplication.clipboard().setText(url)
            self._status(f"Uploaded: {url}  (copied to clipboard)")
        else:
            self._status("Upload failed")

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Project", self.saved_path or "",
                                               "SwiftShot Project (*.swiftshot)")
        if not path: return
        if not path.endswith(".swiftshot"): path += ".swiftshot"
        self._save_project_to(path)

    def _save_project_to(self, path):
        import zipfile, io
        try:
            meta = {"magic": "SWIFTSHOT_PROJECT", "version": 2,
                    "active_index": self.active_layer_index, "layers": []}
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, layer in enumerate(self.layers):
                    is_group = isinstance(layer, LayerGroup)
                    if not is_group:
                        buf = io.BytesIO(); layer.image.save(buf, "PNG")
                        zf.writestr(f"layer_{i}.png", buf.getvalue())
                    else:
                        # Save group image composite for thumbnail; children saved separately
                        try:
                            g_img = layer.image
                            buf = io.BytesIO(); g_img.save(buf, "PNG")
                            zf.writestr(f"layer_{i}.png", buf.getvalue())
                        except Exception:
                            pass
                        for ci, child in enumerate(layer.children):
                            cbuf = io.BytesIO(); child.image.save(cbuf, "PNG")
                            zf.writestr(f"layer_{i}_child_{ci}.png", cbuf.getvalue())
                    ldata = {
                        "name": layer.name, "visible": layer.visible,
                        "opacity": layer.opacity, "blend_mode": layer.blend_mode,
                        "locked": layer.locked,
                        "mask_enabled": getattr(layer, "mask_enabled", True),
                        "has_mask": layer.mask is not None,
                        "effects": [dict(fx) for fx in getattr(layer, "effects", [])],
                        "is_group": is_group,
                        "group_child_count": len(layer.children) if is_group else 0,
                        "group_collapsed": getattr(layer, "collapsed", False),
                    }
                    if layer.mask is not None:
                        mbuf = io.BytesIO(); layer.mask.save(mbuf, "PNG")
                        zf.writestr(f"mask_{i}.png", mbuf.getvalue())
                    meta["layers"].append(ldata)
                zf.writestr("project.json", json.dumps(meta, indent=2))
            self.saved_path = path; self._status(f"Project saved: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project:\n{e}")

    def open_project(self):
        import zipfile, io
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "SwiftShot Project (*.swiftshot)")
        if not path: return
        try:
            with zipfile.ZipFile(path) as zf:
                meta = json.loads(zf.read("project.json"))
                if meta.get("magic") != "SWIFTSHOT_PROJECT":
                    QMessageBox.critical(self, "Error", "Not a valid SwiftShot project"); return
                layers = []
                for i, lmeta in enumerate(meta["layers"]):
                    img = Image.open(io.BytesIO(zf.read(f"layer_{i}.png"))).convert("RGBA")
                    layer = Layer(lmeta["name"], image=img)
                    layer.visible = lmeta.get("visible", True)
                    layer.opacity = lmeta.get("opacity", 255)
                    layer.blend_mode = lmeta.get("blend_mode", "Normal")
                    layer.locked = lmeta.get("locked", False)
                    layer.mask_enabled = lmeta.get("mask_enabled", True)
                    if lmeta.get("has_mask") and f"mask_{i}.png" in zf.namelist():
                        layer.mask = Image.open(io.BytesIO(zf.read(f"mask_{i}.png"))).convert("L")
                    layer.effects = lmeta.get("effects", [])
                    if lmeta.get("is_group"):
                        # Reconstruct LayerGroup from saved children
                        img = layers[-1].image if layers else None  # placeholder
                        iw = img.width if img else 800
                        ih = img.height if img else 600
                        group = LayerGroup(lmeta["name"], iw, ih)
                        group.visible      = lmeta.get("visible", True)
                        group.opacity      = lmeta.get("opacity", 255)
                        group.blend_mode   = lmeta.get("blend_mode", "Normal")
                        group.locked       = lmeta.get("locked", False)
                        group.collapsed    = lmeta.get("group_collapsed", False)
                        group.effects      = lmeta.get("effects", [])
                        for ci in range(lmeta.get("group_child_count", 0)):
                            cname = f"layer_{i}_child_{ci}.png"
                            if cname in zf.namelist():
                                cimg = Image.open(io.BytesIO(zf.read(cname))).convert("RGBA")
                                group.children.append(Layer(f"Layer", image=cimg))
                        layers.append(group)
                    else:
                        layers.append(layer)
            self.layers = layers
            self.active_layer_index = meta.get("active_index", 0)
            self.history = HistoryManager()
            self.file_path = None          # not an image file
            self.saved_path = path
            self.canvas.clear_selection(); self.update_layer_panel(); self.canvas.fit_in_view()
            self.setWindowTitle(f"SwiftShot Editor — {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def insert_note_at(self, x, y):
        """Insert a colored sticky note annotation on the canvas."""
        layer = self.active_layer()
        if not layer: return
        text, ok = QInputDialog.getMultiLineText(self, "Sticky Note", "Note text:")
        if not ok or not text.strip(): return
        self.history.save_state(self.layers, self.active_layer_index, "Note")
        draw = ImageDraw.Draw(layer.image)
        padding = 6
        try:
            font = ImageFont.truetype("arial.ttf", 13)
        except Exception:
            font = ImageFont.load_default()
        note_lines = text.split("\n")
        max_w = max((len(l) * 8) for l in note_lines) + padding * 2
        box_h = len(note_lines) * 18 + padding * 2
        note_color = (255, 220, 80, 230)
        border_color = (200, 160, 30, 255)
        draw.rectangle([x, y, x + max_w, y + box_h], fill=note_color, outline=border_color, width=2)
        draw.text((x + padding, y + padding), text, fill=(50, 40, 0, 255), font=font)
        self.canvas.update()
        self.update_layer_panel()
        self._status("Note added")

    def run_ocr(self):
        """Extract text from the current image using OCR module."""
        try:
            from ocr import ocr_pixmap
            from ocr_dialog import OcrResultDialog
            px = self.get_final_pixmap()
            if px and not px.isNull():
                text = ocr_pixmap(px)
                if text:
                    OcrResultDialog(text, self).exec_()
                else:
                    self._status("OCR: no text detected")
        except ImportError:
            self._status("OCR module not available")

    # ── SwiftShot App Integration ─────────────────────────────────────────────

    def pin_to_desktop(self):
        """Pin current image as an always-on-top floating window."""
        try:
            from pin_window import PinWindow
            final = self.get_final_pixmap()
            if final and not final.isNull():
                pin = PinWindow(final)
                pin.show()
                if self.swiftshot_app:
                    self.swiftshot_app._pin_windows.append(pin)
                    pin.closed.connect(
                        lambda pw: self.swiftshot_app._pin_windows.remove(pw)
                        if pw in self.swiftshot_app._pin_windows else None
                    )
        except Exception as e:
            self._status(f"Pin failed: {e}")

    def closeEvent(self, event):
        if self.swiftshot_app:
            try:
                self.swiftshot_app.editor_closed(self)
            except Exception:
                pass
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(120, self.canvas.fit_in_view)


# ── Crash handler ─────────────────────────────────────────────────────────────
import traceback

def _exception_handler(exc_type, exc_value, exc_tb):
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    crash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
    try:
        with open(crash_path, "w") as f:
            f.write(msg)
    except Exception:
        pass
    try:
        app = QApplication.instance()
        if app:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(None, "SwiftShot — Crash",
                f"An unexpected error occurred:\n\n{str(exc_value)}\n\n"
                f"Full log saved to:\n{crash_path}")
    except Exception:
        print(msg)
    sys.exit(1)

sys.excepthook = _exception_handler


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    # High-DPI support — must be set before QApplication
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("SwiftShot Editor")
    app.setApplicationVersion("2.5.2")
    app.setOrganizationName("SysAdminDoc")
    app.setStyle("Fusion")

    # Auto-detect screen scale — check config override first
    scale_override = None
    cfg = {}
    try:
        import json
        cfg_path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                                "SwiftShot", "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
        scale_override = cfg.get("ui_scale")
    except Exception:
        pass
    detected = init_ui_scale(force=scale_override)
    log.info(f"UI scale: {detected:.2f}x  (screen {_screen_w()}px wide, DPI {_dpi():.0f})")

    # CLI: python editor.py [path/to/image.png]
    initial_pixmap = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-") and os.path.isfile(arg):
            px = QPixmap(arg)
            if not px.isNull():
                initial_pixmap = px
            break
    editor = ImageEditor(pixmap=initial_pixmap)
    sys.exit(app.exec_())


# ── Standalone entry ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
