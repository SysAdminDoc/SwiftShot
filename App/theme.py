"""
SwiftShot Dark Theme
Professional dark theme matching Matt's preferred aesthetic.
"""

import ctypes
import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor


# Shared Catppuccin Mocha roles used by both the main app and editor.
EDITOR_COLORS = {
    "BG0": "#181825",
    "BG1": "#1e1e2e",
    "BG2": "#313244",
    "BG3": "#45475a",
    # Component boundaries need 3:1 contrast against both dark surfaces.
    "BORDER": "#7f849c",
    "TEXT_PRI": "#cdd6f4",
    "TEXT_SEC": "#a6adc8",
    # Muted copy is still copy: keep it above 4.5:1 on BG1 and BG2.
    "TEXT_MUT": "#9ca3bd",
    "ACCENT": "#89b4fa",
    "ACCENT_D": "#313244",
    "ACCENT_H": "#b4befe",
    "RED": "#f38ba8",
    "GREEN": "#a6e3a1",
    "YELLOW": "#f9e2af",
    "CANVAS_BG": "#313244",
}
DARK_COLORS = EDITOR_COLORS
LIGHT_COLORS = {
    "BG0": "#e2e8f0",
    "BG1": "#f8fafc",
    "BG2": "#ffffff",
    "BG3": "#dbeafe",
    "BORDER": "#64748b",
    "TEXT_PRI": "#0f172a",
    "TEXT_SEC": "#334155",
    "TEXT_MUT": "#475569",
    "ACCENT": "#2563eb",
    "ACCENT_D": "#bfdbfe",
    "ACCENT_H": "#1d4ed8",
    "RED": "#b91c1c",
    "GREEN": "#166534",
    "YELLOW": "#854d0e",
    "CANVAS_BG": "#e2e8f0",
}
THEME_LABELS = {"system": "System (follow Windows)", "dark": "Dark", "light": "Light"}


_BASE_STYLESHEET = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Consolas", sans-serif;
    font-size: 10pt;
}

QMainWindow {
    background-color: #1e1e2e;
}

QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
    padding: 2px;
}

QMenuBar::item {
    padding: 4px 10px;
    background-color: transparent;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #45475a;
}

QMenu {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 28px 6px 20px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #45475a;
}

QMenu::separator {
    height: 1px;
    background-color: #585b70;
    margin: 4px 8px;
}

QToolBar {
    background-color: #181825;
    border: none;
    border-bottom: 1px solid #313244;
    padding: 4px;
    spacing: 2px;
}

QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px;
    margin: 1px;
    color: #cdd6f4;
}

QToolButton:hover {
    background-color: #313244;
    border-color: #45475a;
}

QToolButton:pressed, QToolButton:checked {
    background-color: #45475a;
    border-color: #89b4fa;
}

QToolButton:focus, QPushButton:focus, QCheckBox:focus, QRadioButton:focus {
    border: 2px solid #89b4fa;
}

QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 16px;
    min-width: 70px;
}

QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}

QPushButton:pressed {
    background-color: #585b70;
}

QPushButton:default {
    border-color: #89b4fa;
}

QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QListWidget:focus, QTreeWidget:focus, QTabBar:focus {
    border: 2px solid #89b4fa;
}

QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}

QLabel {
    color: #cdd6f4;
    background-color: transparent;
}

QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 12px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 6px;
    min-height: 20px;
    margin: 2px;
}

QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #1e1e2e;
    height: 12px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #45475a;
    border-radius: 6px;
    min-width: 20px;
    margin: 2px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #585b70;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QSpinBox, QDoubleSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px;
}

QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 80px;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #45475a;
    selection-background-color: #45475a;
}

QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #89b4fa;
}

QCheckBox {
    spacing: 6px;
    color: #cdd6f4;
    background-color: transparent;
}

QSlider::groove:horizontal {
    height: 4px;
    background-color: #313244;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background-color: #89b4fa;
    border-radius: 8px;
}

QSlider:focus::handle:horizontal {
    border: 2px solid #cdd6f4;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
    border-radius: 4px;
}

QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    border: 1px solid #45475a;
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border-bottom-color: #1e1e2e;
}

QDialog {
    background-color: #1e1e2e;
}

QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    color: #cdd6f4;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 3px;
}

QListWidget {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
}

QListWidget::item {
    padding: 4px 6px;
    border-radius: 3px;
}

QListWidget::item:selected {
    background-color: #45475a;
    color: #cdd6f4;
}

QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px;
}

QColorDialog {
    background-color: #1e1e2e;
}

QFileDialog {
    background-color: #1e1e2e;
}
"""


_DARK_HEX_ROLES = (
    ("#1e1e2e", "BG1"),
    ("#181825", "BG0"),
    ("#313244", "BG2"),
    ("#45475a", "BG3"),
    ("#585b70", "BORDER"),
    ("#cdd6f4", "TEXT_PRI"),
    ("#a6adc8", "TEXT_SEC"),
    ("#6c7086", "TEXT_MUT"),
    ("#89b4fa", "ACCENT"),
    ("#f38ba8", "RED"),
    ("#f9e2af", "YELLOW"),
)


def _build_stylesheet(colors):
    stylesheet = _BASE_STYLESHEET
    # The dark theme uses #45475a for both hover backgrounds and borders.
    # Border usages must map to the BORDER token, or light-theme controls
    # get near-invisible pale borders (BG3 on white).
    stylesheet = stylesheet.replace("solid #45475a", f"solid {colors['BORDER']}")
    for dark_hex, role in _DARK_HEX_ROLES:
        stylesheet = stylesheet.replace(dark_hex, colors[role])
    return stylesheet


DARK_STYLESHEET = _build_stylesheet(DARK_COLORS)
LIGHT_STYLESHEET = _build_stylesheet(LIGHT_COLORS)


def normalize_theme(theme_name):
    return theme_name if theme_name in THEME_LABELS else "dark"


def windows_prefers_light():
    """Read the Windows app-theme preference (True = light). False off Windows
    or when the key is unreadable (defaults to dark)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
    except OSError:
        return False


def effective_theme(theme_name):
    """Resolve a theme setting to a concrete 'dark'/'light'. 'system' follows
    the Windows app-theme preference; anything else normalizes directly."""
    if theme_name == "system":
        return "light" if windows_prefers_light() else "dark"
    return normalize_theme(theme_name)


def is_high_contrast_enabled():
    """Return the live Windows high-contrast preference without caching it."""
    if sys.platform != "win32":
        return False
    try:
        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = (
                ("cbSize", ctypes.c_uint),
                ("dwFlags", ctypes.c_uint),
                ("lpszDefaultScheme", ctypes.c_wchar_p),
            )

        value = HIGHCONTRAST()
        value.cbSize = ctypes.sizeof(value)
        user32 = ctypes.windll.user32
        user32.SystemParametersInfoW.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        user32.SystemParametersInfoW.restype = ctypes.c_int
        ok = user32.SystemParametersInfoW(
            0x0042, value.cbSize, ctypes.byref(value), 0
        )
        return bool(ok and value.dwFlags & 0x00000001)
    except (AttributeError, OSError):
        return False


def _system_colors():
    """Map SwiftShot roles to the active Qt/system palette."""
    app = QApplication.instance()
    palette = app.palette() if app is not None else QPalette()
    color = lambda role: palette.color(role).name()
    return {
        "BG0": color(QPalette.Window),
        "BG1": color(QPalette.Window),
        "BG2": color(QPalette.Base),
        "BG3": color(QPalette.AlternateBase),
        "BORDER": color(QPalette.WindowText),
        "TEXT_PRI": color(QPalette.WindowText),
        "TEXT_SEC": color(QPalette.Text),
        "TEXT_MUT": color(QPalette.Text),
        "ACCENT": color(QPalette.Highlight),
        "ACCENT_D": color(QPalette.Highlight),
        "ACCENT_H": color(QPalette.Highlight),
        "RED": color(QPalette.BrightText),
        "GREEN": color(QPalette.Link),
        "YELLOW": color(QPalette.Link),
        "CANVAS_BG": color(QPalette.Window),
    }


def colors_for_theme(theme_name, high_contrast=None):
    if high_contrast is None:
        high_contrast = is_high_contrast_enabled()
    if high_contrast:
        return _system_colors()
    return LIGHT_COLORS if effective_theme(theme_name) == "light" else DARK_COLORS


def stylesheet_for_theme(theme_name, high_contrast=None):
    if high_contrast is None:
        high_contrast = is_high_contrast_enabled()
    if high_contrast:
        # Native styling is the only reliable way to preserve user-selected
        # Windows high-contrast colors and focus indicators.
        return ""
    return LIGHT_STYLESHEET if effective_theme(theme_name) == "light" else DARK_STYLESHEET


def _apply_palette(app: QApplication, colors):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors["BG1"]))
    palette.setColor(QPalette.WindowText, QColor(colors["TEXT_PRI"]))
    palette.setColor(QPalette.Base, QColor(colors["BG2"]))
    palette.setColor(QPalette.AlternateBase, QColor(colors["BG3"]))
    palette.setColor(QPalette.ToolTipBase, QColor(colors["BG2"]))
    palette.setColor(QPalette.ToolTipText, QColor(colors["TEXT_PRI"]))
    palette.setColor(QPalette.Text, QColor(colors["TEXT_PRI"]))
    palette.setColor(QPalette.Button, QColor(colors["BG2"]))
    palette.setColor(QPalette.ButtonText, QColor(colors["TEXT_PRI"]))
    palette.setColor(QPalette.BrightText, QColor(colors["RED"]))
    palette.setColor(QPalette.Link, QColor(colors["ACCENT"]))
    palette.setColor(QPalette.LinkVisited, QColor(colors["ACCENT_H"]))
    palette.setColor(QPalette.Highlight, QColor(colors["ACCENT"]))
    highlight_text = "#ffffff" if colors is LIGHT_COLORS else colors["BG1"]
    palette.setColor(QPalette.HighlightedText, QColor(highlight_text))
    if hasattr(QPalette, "PlaceholderText"):
        palette.setColor(QPalette.PlaceholderText, QColor(colors["TEXT_MUT"]))
    palette.setColor(
        QPalette.Disabled, QPalette.WindowText, QColor(colors["TEXT_MUT"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["TEXT_MUT"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors["TEXT_MUT"]))
    app.setPalette(palette)


def apply_theme(app: QApplication, theme_name="dark"):
    """Apply the selected SwiftShot theme to the application."""
    if is_high_contrast_enabled():
        app.setStyleSheet("")
        app.setPalette(app.style().standardPalette())
        return
    colors = colors_for_theme(theme_name)
    _apply_palette(app, colors)
    app.setStyleSheet(stylesheet_for_theme(theme_name))
