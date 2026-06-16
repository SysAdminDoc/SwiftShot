"""
SwiftShot Dark Theme
Professional dark theme matching Matt's preferred aesthetic.
"""

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt


# Shared Catppuccin Mocha roles used by both the main app and editor.
EDITOR_COLORS = {
    "BG0": "#181825",
    "BG1": "#1e1e2e",
    "BG2": "#313244",
    "BG3": "#45475a",
    "BORDER": "#45475a",
    "TEXT_PRI": "#cdd6f4",
    "TEXT_SEC": "#a6adc8",
    "TEXT_MUT": "#6c7086",
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
    "BORDER": "#94a3b8",
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
THEME_LABELS = {"dark": "Dark", "light": "Light"}


DARK_STYLESHEET = """
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
    background-color: #313244;
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

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background-color: #313244;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
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
    stylesheet = DARK_STYLESHEET
    for dark_hex, role in _DARK_HEX_ROLES:
        stylesheet = stylesheet.replace(dark_hex, colors[role])
    return stylesheet


LIGHT_STYLESHEET = _build_stylesheet(LIGHT_COLORS)


def normalize_theme(theme_name):
    return theme_name if theme_name in THEME_LABELS else "dark"


def colors_for_theme(theme_name):
    return LIGHT_COLORS if normalize_theme(theme_name) == "light" else DARK_COLORS


def stylesheet_for_theme(theme_name):
    return LIGHT_STYLESHEET if normalize_theme(theme_name) == "light" else DARK_STYLESHEET


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
    palette.setColor(QPalette.Highlight, QColor(colors["ACCENT"]))
    highlight_text = "#ffffff" if colors is LIGHT_COLORS else colors["BG1"]
    palette.setColor(QPalette.HighlightedText, QColor(highlight_text))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["TEXT_MUT"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors["TEXT_MUT"]))
    app.setPalette(palette)


def apply_theme(app: QApplication, theme_name="dark"):
    """Apply the selected SwiftShot theme to the application."""
    colors = colors_for_theme(theme_name)
    _apply_palette(app, colors)
    app.setStyleSheet(stylesheet_for_theme(theme_name))


def apply_dark_theme(app: QApplication):
    """Apply the dark theme to the application."""
    apply_theme(app, "dark")


def apply_light_theme(app: QApplication):
    """Apply the light theme to the application."""
    apply_theme(app, "light")
