"""
SwiftShot Capture History
Panel showing thumbnails of recent captures with quick actions.
"""

import os
import glob
import hashlib
import sqlite3
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QApplication, QGridLayout, QFrame,
    QMenu, QAction, QToolTip, QMessageBox, QLineEdit
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QCursor, QIcon
from PyQt5.QtCore import (
    Qt, QSize, pyqtSignal, QPoint, QByteArray, QBuffer, QIODevice
)

from config import config
from logger import log


IMAGE_EXTENSIONS = [
    '*.png', '*.jpg', '*.jpeg', '*.bmp',
    '*.gif', '*.tiff', '*.tif', '*.webp',
]


def _history_files(history_dir):
    files = []
    if os.path.isdir(history_dir):
        for ext in IMAGE_EXTENSIONS:
            files.extend(glob.glob(os.path.join(history_dir, ext)))
    return files


def _db_path(history_dir):
    return os.path.join(history_dir, "history.sqlite3")


def _connect_db(history_dir):
    os.makedirs(history_dir, exist_ok=True)
    conn = sqlite3.connect(_db_path(history_dir))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            sha256 TEXT NOT NULL UNIQUE,
            ocr_text TEXT NOT NULL DEFAULT '',
            thumbnail_blob BLOB NOT NULL
        )
    """)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(captures)")
    }
    if "ocr_text" not in columns:
        conn.execute("ALTER TABLE captures ADD COLUMN ocr_text TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_captures_created ON captures(created_at)"
    )
    return conn


def _pixmap_png_bytes(pixmap):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _thumbnail_blob(pixmap):
    thumb = pixmap.scaled(164, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return _pixmap_png_bytes(thumb)


def _index_file(conn, filepath):
    pixmap = QPixmap(filepath)
    if pixmap.isNull():
        return
    with open(filepath, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    created_at = datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat(
        timespec="seconds"
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO captures
            (path, created_at, width, height, sha256, ocr_text, thumbnail_blob)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filepath,
            created_at,
            pixmap.width(),
            pixmap.height(),
            digest,
            "",
            _thumbnail_blob(pixmap),
        ),
    )


def _ensure_history_index(history_dir):
    conn = _connect_db(history_dir)
    indexed = {
        row["path"] for row in conn.execute("SELECT path FROM captures")
    }
    for filepath in _history_files(history_dir):
        if filepath not in indexed:
            _index_file(conn, filepath)
    conn.commit()
    return conn


def _history_entries(history_dir, search_text=""):
    if not os.path.isdir(history_dir):
        return []
    with _ensure_history_index(history_dir) as conn:
        params = []
        where = "WHERE 1=1"
        if search_text:
            where += " AND (created_at LIKE ? OR path LIKE ? OR ocr_text LIKE ?)"
            like = f"%{search_text}%"
            params.extend([like, like, like])
        rows = conn.execute(
            f"""
            SELECT path, created_at, width, height, sha256, ocr_text, thumbnail_blob
            FROM captures
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (*params, config.CAPTURE_HISTORY_MAX),
        ).fetchall()
    return [dict(row) for row in rows if os.path.exists(row["path"])]


def _delete_history_entry(history_dir, filepath):
    with _connect_db(history_dir) as conn:
        conn.execute("DELETE FROM captures WHERE path = ?", (filepath,))


class HistoryThumbnail(QFrame):
    """Clickable thumbnail card for a captured image."""

    open_editor = pyqtSignal(str)       # filepath
    copy_clipboard = pyqtSignal(str)    # filepath
    pin_image = pyqtSignal(str)         # filepath
    delete_entry = pyqtSignal(str)      # filepath

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.filepath = entry["path"] if isinstance(entry, dict) else entry
        self._hovered = False
        self._pixmap = QPixmap()
        if isinstance(entry, dict) and entry.get("thumbnail_blob"):
            self._pixmap.loadFromData(entry["thumbnail_blob"])
        if self._pixmap.isNull():
            self._pixmap = QPixmap(self.filepath)
        self._filename = os.path.basename(self.filepath)

        # Parse timestamp from filename or file mod time
        if isinstance(entry, dict):
            self._timestamp = entry.get("created_at", "").replace("T", " ")
        else:
            try:
                mtime = os.path.getmtime(self.filepath)
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

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search date, filename, or OCR text...")
        self.search_box.setToolTip("Search capture history by date, time, filename, or OCR text")
        self.search_box.textChanged.connect(self._load_history)
        layout.addWidget(self.search_box)

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

        entries = _history_entries(history_dir, self.search_box.text().strip())

        if not entries:
            lbl = QLabel("No captures yet")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #6c7086; font-size: 12pt;")
            self.grid.addWidget(lbl, 0, 0)
        else:
            cols = 3
            for i, entry in enumerate(entries):
                thumb = HistoryThumbnail(entry)
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
        filename = os.path.basename(filepath)
        response = QMessageBox.question(
            self,
            "Delete Capture",
            f"Delete '{filename}' from capture history?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if response != QMessageBox.Yes:
            return

        try:
            os.remove(filepath)
        except Exception:
            pass
        _delete_history_entry(config.CAPTURE_HISTORY_DIR, filepath)
        self._load_history()

    def _clear_history(self):
        history_dir = config.CAPTURE_HISTORY_DIR
        if not os.path.isdir(history_dir):
            return
        files = _history_files(history_dir)
        if not files:
            return

        response = QMessageBox.question(
            self,
            "Clear Capture History",
            f"Delete all {len(files)} capture history image(s)?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if response != QMessageBox.Yes:
            return

        for f in files:
            try:
                os.remove(f)
            except Exception:
                pass
        with _connect_db(history_dir) as conn:
            conn.execute("DELETE FROM captures")
        self._load_history()


def save_to_history(pixmap, ocr_text=""):
    """Save a QPixmap to the capture history directory."""
    if not config.CAPTURE_HISTORY_ENABLED:
        return None
    try:
        history_dir = config.CAPTURE_HISTORY_DIR
        os.makedirs(history_dir, exist_ok=True)

        png_bytes = _pixmap_png_bytes(pixmap)
        digest = hashlib.sha256(png_bytes).hexdigest()
        with _connect_db(history_dir) as conn:
            existing = conn.execute(
                "SELECT path FROM captures WHERE sha256 = ?",
                (digest,),
            ).fetchone()
            if existing:
                if os.path.exists(existing["path"]):
                    if ocr_text:
                        conn.execute(
                            "UPDATE captures SET ocr_text = ? WHERE sha256 = ?",
                            (ocr_text, digest),
                        )
                    log.info(f"Duplicate capture skipped: {existing['path']}")
                    return existing["path"]
                conn.execute("DELETE FROM captures WHERE sha256 = ?", (digest,))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filepath = os.path.join(history_dir, f"capture_{timestamp}.png")
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(
                history_dir, f"capture_{timestamp}_{counter}.png"
            )
            counter += 1
        with open(filepath, "wb") as f:
            f.write(png_bytes)

        created_at = datetime.now().isoformat(timespec="seconds")
        with _connect_db(history_dir) as conn:
            conn.execute(
                """
                INSERT INTO captures
                    (path, created_at, width, height, sha256, ocr_text, thumbnail_blob)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filepath,
                    created_at,
                    pixmap.width(),
                    pixmap.height(),
                    digest,
                    ocr_text or "",
                    _thumbnail_blob(pixmap),
                ),
            )
            old_entries = conn.execute(
                """
                SELECT path FROM captures
                ORDER BY created_at DESC, id DESC
                LIMIT -1 OFFSET ?
                """,
                (config.CAPTURE_HISTORY_MAX,),
            ).fetchall()
            for row in old_entries:
                try:
                    os.remove(row["path"])
                except Exception:
                    pass
                conn.execute("DELETE FROM captures WHERE path = ?", (row["path"],))

        log.info(f"Saved to history: {filepath}")
        return filepath
    except Exception as e:
        log.error(f"Failed to save to history: {e}")
        return None
