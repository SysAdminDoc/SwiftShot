"""
SwiftShot Capture History
Panel showing thumbnails of recent captures with quick actions.
"""

import os
import glob
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QApplication, QGridLayout, QFrame,
    QMenu, QMessageBox, QLineEdit
)
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPen
from PyQt5.QtCore import (
    Qt, pyqtSignal, QByteArray, QBuffer, QIODevice, QTimer
)

from config import config
from logger import log
from safe_io import load_image
from theme import colors_for_theme
from utils import atomic_write_bytes, pil_to_qpixmap


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
    # Files we've already examined. A content-duplicate file can't be inserted
    # into `captures` (its sha256 is taken), so without this we'd re-read and
    # re-hash it on every panel open. mtime lets us re-index if the file changes.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_files (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL
        )
    """)
    return conn


@contextmanager
def _db(history_dir):
    """Open a history-DB connection that is committed on success and ALWAYS
    closed. ``with sqlite3.connect(...) as conn`` only manages the transaction
    (commit/rollback) — it never closes the connection, so the tray process
    leaked a connection + file handle on every capture and history op."""
    conn = _connect_db(history_dir)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _pixmap_png_bytes(pixmap):
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    saved = pixmap.save(buffer, "PNG")
    buffer.close()
    payload = bytes(data)
    if not saved or not payload:
        raise OSError("Failed to encode capture as PNG")
    return payload


def _verify_png(path):
    load_image(path, allowed_formats={"PNG"})


def _safe_pixmap(path):
    try:
        return pil_to_qpixmap(load_image(path))
    except Exception as error:
        log.warning(f"Rejected history image {path}: {error}")
        return QPixmap()


def _thumbnail_blob(pixmap):
    thumb = pixmap.scaled(164, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return _pixmap_png_bytes(thumb)


def _index_file(conn, filepath, mtime):
    pixmap = _safe_pixmap(filepath)
    if pixmap.isNull():
        conn.execute(
            "INSERT OR REPLACE INTO seen_files (path, mtime) VALUES (?, ?)",
            (filepath, mtime))
        return
    with open(filepath, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    created_at = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
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
    # Record the path either way — a content-duplicate that INSERT OR IGNORE
    # dropped must not be re-hashed on the next panel open.
    conn.execute(
        "INSERT OR REPLACE INTO seen_files (path, mtime) VALUES (?, ?)",
        (filepath, mtime))


def _ensure_history_index(conn, history_dir):
    indexed = {
        row["path"] for row in conn.execute("SELECT path FROM captures")
    }
    # Files already examined (including content-duplicates with no captures row),
    # with the mtime we saw — so we only re-index a file that actually changed.
    seen = {row["path"]: row["mtime"]
            for row in conn.execute("SELECT path, mtime FROM seen_files")}
    # Purge rows whose file was deleted outside the app. Otherwise they keep
    # occupying LIMIT slots (the panel filtered missing files AFTER the query,
    # so dead rows could starve the panel down to zero visible captures).
    for path in indexed:
        if not os.path.exists(path):
            conn.execute("DELETE FROM captures WHERE path = ?", (path,))
    # Prune seen_files rows whose file is gone so the table can't grow forever.
    for path in list(seen):
        if not os.path.exists(path):
            conn.execute("DELETE FROM seen_files WHERE path = ?", (path,))
            del seen[path]
    for filepath in _history_files(history_dir):
        if filepath in indexed:
            continue
        try:
            mtime = os.path.getmtime(filepath)
        except OSError:
            continue
        if seen.get(filepath) == mtime:
            continue                       # unchanged duplicate — skip re-hash
        _index_file(conn, filepath, mtime)
    conn.commit()


def _escape_like(text):
    """Escape SQL LIKE wildcards so searching '100%' matches literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _history_entries(history_dir, search_text=""):
    if not os.path.isdir(history_dir):
        return []
    with _db(history_dir) as conn:
        _ensure_history_index(conn, history_dir)
        params = []
        where = "WHERE 1=1"
        if search_text:
            where += (" AND (created_at LIKE ? ESCAPE '\\'"
                      " OR path LIKE ? ESCAPE '\\'"
                      " OR ocr_text LIKE ? ESCAPE '\\')")
            like = f"%{_escape_like(search_text)}%"
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
    with _db(history_dir) as conn:
        conn.execute("DELETE FROM captures WHERE path = ?", (filepath,))
        conn.execute("DELETE FROM seen_files WHERE path = ?", (filepath,))


def _remove_history_file(filepath):
    """Return ``(removed, error)``; missing already means safely removed."""
    try:
        os.remove(filepath)
    except FileNotFoundError:
        return True, None
    except OSError as error:
        return False, str(error)
    if os.path.exists(filepath):
        return False, "the file still exists after the delete operation"
    return True, None


def _prune_history_retention(history_dir):
    """Retry old files without dropping their only DB reference on failure."""
    with _db(history_dir) as conn:
        old_entries = conn.execute(
            """
            SELECT path FROM captures
            ORDER BY created_at DESC, id DESC
            LIMIT -1 OFFSET ?
            """,
            (max(0, int(config.CAPTURE_HISTORY_MAX)),),
        ).fetchall()
    for row in old_entries:
        filepath = row["path"]
        removed, error = _remove_history_file(filepath)
        if not removed:
            log.warning(f"History retention could not delete {filepath}: {error}")
            continue
        try:
            _delete_history_entry(history_dir, filepath)
        except Exception as db_error:
            # The file is already gone; the next index pass will purge the
            # stale row. Do not make a successfully saved new capture fail.
            log.warning(
                f"History retention removed {filepath} but could not remove "
                f"its index row: {db_error}"
            )


def update_history_ocr(history_dir, filepath, ocr_text):
    """Set the OCR text for an already-saved capture (used when auto-OCR runs
    asynchronously after the row is inserted, so it never blocks capture)."""
    try:
        with _db(history_dir) as conn:
            conn.execute(
                "UPDATE captures SET ocr_text = ? WHERE path = ?",
                (ocr_text or "", filepath))
    except Exception as e:
        log.warning(f"Failed to update history OCR text: {e}")


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
            self._pixmap = _safe_pixmap(self.filepath)
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
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f"Capture {self._filename}")
        self.setAccessibleDescription(
            "Press Enter to open in the editor, or the menu key for more actions.")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w, h = self.width(), self.height()
        colors = colors_for_theme(config.THEME)

        # Background
        active = self._hovered or self.hasFocus()
        bg = QColor(colors["BG2"]) if active else QColor(colors["BG1"])
        border = QColor(colors["ACCENT"]) if active else QColor(colors["BORDER"])
        painter.setBrush(bg)
        painter.setPen(QPen(border, 2 if active else 1))
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
        painter.setPen(QColor(colors["TEXT_PRI"]))
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        fm = painter.fontMetrics()
        label = fm.elidedText(self._filename, Qt.ElideMiddle, w - 16)
        painter.drawText(8, h - 22, label)

        # Timestamp
        painter.setPen(QColor(colors["TEXT_MUT"]))
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

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_editor.emit(self.filepath)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.open_editor.emit(self.filepath)
        elif event.key() == Qt.Key_Delete:
            self.delete_entry.emit(self.filepath)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        # Handles both right-click and the keyboard context-menu key.
        self._show_context_menu(event.globalPos())

    def _show_context_menu(self, pos):
        menu = QMenu(self)

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
        # Styling comes from the app-wide theme stylesheet.

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
        self.search_box.setAccessibleName("Search capture history")
        # Debounce so each keystroke doesn't rescan the directory and DB
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._load_history)
        self.search_box.textChanged.connect(
            lambda _: self._search_timer.start())
        layout.addWidget(self.search_box)

        # Scroll area with grid of thumbnails
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        colors = colors_for_theme(config.THEME)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: {colors['BG0']}; }}")
        layout.addWidget(self.scroll)

        self._load_history()

    def _load_history(self):
        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(8, 8, 8, 8)

        history_dir = config.CAPTURE_HISTORY_DIR
        search = self.search_box.text().strip()
        if os.path.isdir(history_dir):
            entries = _history_entries(history_dir, search)
        else:
            entries = []   # dir not created yet — show the same empty guidance

        if not entries:
            if search:
                lbl = QLabel(f'No captures match "{search}"')
            else:
                lbl = QLabel("No captures yet.\n"
                             "Screenshots you take will show up here.")
            lbl.setAlignment(Qt.AlignCenter)
            colors = colors_for_theme(config.THEME)
            lbl.setStyleSheet(f"color: {colors['TEXT_MUT']}; font-size: 12pt;")
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
        pixmap = _safe_pixmap(filepath)
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

        removed, error = _remove_history_file(filepath)
        if not removed:
            QMessageBox.warning(
                self,
                "Capture Not Deleted",
                f"SwiftShot could not delete '{filename}'. The file remains "
                f"in capture history so you can retry.\n\n{error}",
            )
            return
        try:
            _delete_history_entry(config.CAPTURE_HISTORY_DIR, filepath)
        except Exception as db_error:
            log.warning(f"Deleted capture but could not update history index: {db_error}")
        self._load_history()

    def _clear_history(self):
        history_dir = config.CAPTURE_HISTORY_DIR
        if not os.path.isdir(history_dir):
            return
        files = _history_files(history_dir)
        if not files:
            return

        visible = len(_history_entries(history_dir))
        stored = len(files)
        count_text = f"{stored} stored capture file(s)"
        if visible != stored:
            count_text += f" ({visible} visible history entries)"
        response = QMessageBox.question(
            self,
            "Clear Capture History",
            f"Permanently delete all {count_text}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if response != QMessageBox.Yes:
            return

        removed_paths = []
        failures = []
        for filepath in files:
            removed, error = _remove_history_file(filepath)
            if removed:
                removed_paths.append(filepath)
            else:
                failures.append((filepath, error))
        if removed_paths:
            try:
                with _db(history_dir) as conn:
                    for filepath in removed_paths:
                        conn.execute("DELETE FROM captures WHERE path = ?", (filepath,))
                        conn.execute("DELETE FROM seen_files WHERE path = ?", (filepath,))
            except Exception as db_error:
                log.warning(f"Clear history could not update the index: {db_error}")
        self._load_history()
        if failures:
            details = "\n".join(
                f"• {os.path.basename(path)} — {error}" for path, error in failures
            )
            QMessageBox.warning(
                self,
                "Capture History Partially Cleared",
                f"Deleted {len(removed_paths)} of {stored} stored capture "
                f"file(s). {len(failures)} remain in history for retry.\n\n{details}",
            )


def save_to_history(pixmap, ocr_text=""):
    """Save a QPixmap to the capture history directory."""
    if not config.CAPTURE_HISTORY_ENABLED:
        return None
    try:
        history_dir = config.CAPTURE_HISTORY_DIR
        os.makedirs(history_dir, exist_ok=True)

        png_bytes = _pixmap_png_bytes(pixmap)
        digest = hashlib.sha256(png_bytes).hexdigest()
        with _db(history_dir) as conn:
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
        atomic_write_bytes(filepath, png_bytes, _verify_png)

        created_at = datetime.now().isoformat(timespec="seconds")
        try:
            with _db(history_dir) as conn:
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
        except Exception:
            # The image is published before the DB transaction. Compensate if
            # indexing/commit fails so history never accumulates hidden files.
            try:
                os.remove(filepath)
            except FileNotFoundError:
                pass
            raise

        _prune_history_retention(history_dir)

        log.info(f"Saved to history: {filepath}")
        return filepath
    except Exception as e:
        log.error(f"Failed to save to history: {e}")
        return None
