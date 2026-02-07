"""
SwiftShot Capture History
Panel showing thumbnails of recent captures with quick actions.
"""

import os
import glob
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QApplication, QGridLayout, QFrame,
    QMenu, QAction, QToolTip
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QCursor, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QPoint

from config import config
from logger import log


class HistoryThumbnail(QFrame):
    """Clickable thumbnail card for a captured image."""

    open_editor = pyqtSignal(str)       # filepath
    copy_clipboard = pyqtSignal(str)    # filepath
    pin_image = pyqtSignal(str)         # filepath
    delete_entry = pyqtSignal(str)      # filepath

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._hovered = False
        self._pixmap = QPixmap(filepath)
        self._filename = os.path.basename(filepath)

        # Parse timestamp from filename or file mod time
        try:
            mtime = os.path.getmtime(filepath)
            self._timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            self._timestamp = ""

        self.setFixedSize(180, 150)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setToolTip(f"{self._filename}\n{self._timestamp}")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()

        # Background
        bg = QColor("#313244") if self._hovered else QColor("#1e1e2e")
        border = QColor("#89b4fa") if self._hovered else QColor("#45475a")
        painter.setBrush(bg)
        painter.setPen(QPen(border, 2 if self._hovered else 1))
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 6, 6)

        # Thumbnail
        if not self._pixmap.isNull():
            margin = 8
            thumb_area_w = w - margin * 2
            thumb_area_h = h - 40
            scaled = self._pixmap.scaled(
                thumb_area_w, thumb_area_h,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            tx = margin + (thumb_area_w - scaled.width()) // 2
            ty = margin + (thumb_area_h - scaled.height()) // 2
            painter.drawPixmap(tx, ty, scaled)

        # Filename label
        painter.setPen(QColor("#cdd6f4"))
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        fm = painter.fontMetrics()
        label = fm.elidedText(self._filename, Qt.ElideMiddle, w - 16)
        painter.drawText(8, h - 22, label)

        # Timestamp
        painter.setPen(QColor("#6c7086"))
        font.setPointSize(7)
        painter.setFont(font)
        if self._timestamp:
            time_part = self._timestamp.split(" ")[-1] if " " in self._timestamp else self._timestamp
            painter.drawText(8, h - 8, time_part)

        painter.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_editor.emit(self.filepath)
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())

    def _show_context_menu(self, pos):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e2e; color: #cdd6f4;
                    border: 1px solid #45475a; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #45475a; }
            QMenu::separator { height: 1px; background-color: #313244; margin: 4px 8px; }
        """)

        open_act = menu.addAction("Open in Editor")
        open_act.triggered.connect(lambda: self.open_editor.emit(self.filepath))

        copy_act = menu.addAction("Copy to Clipboard")
        copy_act.triggered.connect(lambda: self.copy_clipboard.emit(self.filepath))

        pin_act = menu.addAction("Pin to Desktop")
        pin_act.triggered.connect(lambda: self.pin_image.emit(self.filepath))

        menu.addSeparator()

        folder_act = menu.addAction("Open File Location")
        folder_act.triggered.connect(self._open_folder)

        menu.addSeparator()

        del_act = menu.addAction("Delete")
        del_act.triggered.connect(lambda: self.delete_entry.emit(self.filepath))

        menu.exec_(pos)

    def _open_folder(self):
        import subprocess
        import sys
        if sys.platform == 'win32':
            subprocess.Popen(f'explorer /select,"{self.filepath}"')
        else:
            folder = os.path.dirname(self.filepath)
            subprocess.Popen(['xdg-open', folder])


class CaptureHistoryDialog(QDialog):
    """Dialog showing recent capture thumbnails."""

    open_in_editor = pyqtSignal(str)
    copy_to_clipboard = pyqtSignal(str)
    pin_to_desktop = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture History - SwiftShot")
        self.setMinimumSize(620, 450)
        self.setModal(False)

        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; background: transparent; }
            QPushButton {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 6px 16px;
            }
            QPushButton:hover { background-color: #45475a; border-color: #89b4fa; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Title bar
        title_bar = QHBoxLayout()
        title = QLabel("Recent Captures")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_bar.addWidget(title)
        title_bar.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(80)
        refresh_btn.clicked.connect(self._load_history)
        title_bar.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self._clear_history)
        title_bar.addWidget(clear_btn)

        layout.addLayout(title_bar)

        # Scroll area with grid of thumbnails
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background-color: #181825; }")
        layout.addWidget(self.scroll)

        self._load_history()

    def _load_history(self):
        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(8, 8, 8, 8)

        history_dir = config.CAPTURE_HISTORY_DIR
        if not os.path.isdir(history_dir):
            self.scroll.setWidget(container)
            return

        # Get image files sorted by modification time (newest first)
        extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp']
        files = []
        for ext in extensions:
            files.extend(glob.glob(os.path.join(history_dir, ext)))
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
        files = files[:config.CAPTURE_HISTORY_MAX]

        if not files:
            lbl = QLabel("No captures yet")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #6c7086; font-size: 12pt;")
            self.grid.addWidget(lbl, 0, 0)
        else:
            cols = 3
            for i, filepath in enumerate(files):
                thumb = HistoryThumbnail(filepath)
                thumb.open_editor.connect(self._on_open)
                thumb.copy_clipboard.connect(self._on_copy)
                thumb.pin_image.connect(self._on_pin)
                thumb.delete_entry.connect(self._on_delete)
                self.grid.addWidget(thumb, i // cols, i % cols)

        self.scroll.setWidget(container)

    def _on_open(self, filepath):
        self.open_in_editor.emit(filepath)

    def _on_copy(self, filepath):
        pixmap = QPixmap(filepath)
        if not pixmap.isNull():
            QApplication.clipboard().setPixmap(pixmap)

    def _on_pin(self, filepath):
        self.pin_to_desktop.emit(filepath)

    def _on_delete(self, filepath):
        try:
            os.remove(filepath)
        except Exception:
            pass
        self._load_history()

    def _clear_history(self):
        history_dir = config.CAPTURE_HISTORY_DIR
        if not os.path.isdir(history_dir):
            return
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.bmp']:
            for f in glob.glob(os.path.join(history_dir, ext)):
                try:
                    os.remove(f)
                except Exception:
                    pass
        self._load_history()


def save_to_history(pixmap):
    """Save a QPixmap to the capture history directory."""
    if not config.CAPTURE_HISTORY_ENABLED:
        return None
    try:
        history_dir = config.CAPTURE_HISTORY_DIR
        os.makedirs(history_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filepath = os.path.join(history_dir, f"capture_{timestamp}.png")
        pixmap.save(filepath, "PNG")

        # Prune old entries
        extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp']
        files = []
        for ext in extensions:
            files.extend(glob.glob(os.path.join(history_dir, ext)))
        files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

        for old_file in files[config.CAPTURE_HISTORY_MAX:]:
            try:
                os.remove(old_file)
            except Exception:
                pass

        log.info(f"Saved to history: {filepath}")
        return filepath
    except Exception as e:
        log.error(f"Failed to save to history: {e}")
        return None
