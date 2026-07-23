"""
SwiftShot Capture History
Panel showing thumbnails of recent captures with quick actions.
"""

import os
import glob
import hashlib
import json
import re
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QApplication, QGridLayout, QFrame,
    QMenu, QMessageBox, QLineEdit, QCheckBox, QInputDialog
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
HISTORY_QUICK_CHECK_MAX_ERRORS = 10
HISTORY_QUICK_CHECK_TIMEOUT_SECONDS = 1.0
HISTORY_HEALTH_SCHEMA_VERSION = 1
HASH_CHUNK_BYTES = 1024 * 1024
_health_results = {}
_health_lock = threading.Lock()


class _HistoryDatabaseCorrupt(RuntimeError):
    pass


class _HistoryCheckTimeout(RuntimeError):
    pass


def _history_files(history_dir):
    files = []
    if os.path.isdir(history_dir):
        for ext in IMAGE_EXTENSIONS:
            files.extend(glob.glob(os.path.join(history_dir, ext)))
    return files


HISTORY_SCHEMA_VERSION = 2   # 1 = base, 2 = + favorite/tags (R-31)


def _db_path(history_dir):
    return os.path.join(history_dir, "history.sqlite3")


def _backup_db_file(history_dir, suffix):
    """Copy the SQLite file to a timestamped backup before a schema migration
    so a bad migration never loses the index. Best-effort — image files are the
    source of truth and can rebuild the DB regardless."""
    src = _db_path(history_dir)
    if not os.path.exists(src):
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = os.path.join(history_dir, f"history.{suffix}.{stamp}.bak")
    try:
        shutil.copy2(src, dst)
        return dst
    except OSError:
        log.warning("Could not back up history DB before migration", exc_info=True)
        return None


def _normalize_tags(value):
    """Normalize tags (list or comma/space string) to a sorted, deduped,
    lowercase list of non-empty tokens."""
    if isinstance(value, str):
        raw = re.split(r"[,\n]", value)
    else:
        raw = list(value or [])
    seen = []
    for t in raw:
        tok = str(t).strip().lower()
        if tok and tok not in seen:
            seen.append(tok)
    return sorted(seen)


def _tags_to_str(tags):
    """Store tags as a leading/trailing-comma-wrapped string so a LIKE
    '%,tag,%' match is exact (no partial-token false positives)."""
    norm = _normalize_tags(tags)
    return "," + ",".join(norm) + "," if norm else ""


def _tags_from_str(text):
    return [t for t in (text or "").strip(",").split(",") if t]


def _open_schema_db(history_dir):
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
    # Favorites + tags (R-31): a versioned, reversible migration. Back up the
    # database before adding columns to an already-populated table, then apply
    # the additive (non-destructive) ALTERs in one transaction.
    needs_favorites = "favorite" not in columns
    needs_tags = "tags" not in columns
    if needs_favorites or needs_tags:
        has_rows = conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0] > 0
        if has_rows:
            _backup_db_file(history_dir, "pre-favorites")
        with conn:
            if needs_favorites:
                conn.execute(
                    "ALTER TABLE captures ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0")
            if needs_tags:
                conn.execute(
                    "ALTER TABLE captures ADD COLUMN tags TEXT NOT NULL DEFAULT ''")
            conn.execute(f"PRAGMA user_version = {HISTORY_SCHEMA_VERSION}")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_captures_created ON captures(created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_captures_favorite ON captures(favorite)"
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


def _health_report_path(history_dir):
    config_dir = getattr(config, "_config_dir", None)
    return os.path.join(config_dir or os.path.dirname(history_dir),
                        "history-health.json")


def _persist_health_report(history_dir, result):
    public = {
        "schema_version": HISTORY_HEALTH_SCHEMA_VERSION,
        "status": result["status"],
        "checked_at": result["checked_at"],
        "sqlite_version": sqlite3.sqlite_version,
        "quick_check": result["quick_check"],
        "quarantined_database": bool(result.get("quarantine_path")),
        "recovered_file_count": int(result.get("recovered_file_count", 0)),
    }
    try:
        atomic_write_bytes(
            _health_report_path(history_dir),
            json.dumps(public, indent=2).encode("utf-8"),
        )
    except Exception:
        log.warning("Could not persist history health report", exc_info=True)


def _run_quick_check(database_path):
    """Run a read-only, error-count- and time-bounded SQLite quick check."""
    deadline = time.monotonic() + HISTORY_QUICK_CHECK_TIMEOUT_SECONDS
    uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=0.5)
    try:
        conn.set_progress_handler(
            lambda: int(time.monotonic() >= deadline), 1_000
        )
        try:
            rows = conn.execute(
                f"PRAGMA quick_check({HISTORY_QUICK_CHECK_MAX_ERRORS})"
            ).fetchall()
        except sqlite3.OperationalError as error:
            if "interrupted" in str(error).casefold():
                raise _HistoryCheckTimeout from error
            raise
        if rows != [("ok",)]:
            raise _HistoryDatabaseCorrupt("quick_check reported corruption")
    finally:
        conn.set_progress_handler(None, 0)
        conn.close()


def _quarantine_database(history_dir):
    """Atomically move the DB and live sidecars together, rolling back on error."""
    database_path = _db_path(history_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    quarantine_dir = os.path.join(
        history_dir, "DatabaseQuarantine", stamp
    )
    os.makedirs(quarantine_dir, exist_ok=False)
    sources = [
        database_path + "-wal",
        database_path + "-shm",
        database_path,
    ]
    moved = []
    try:
        for source in sources:
            if not os.path.exists(source):
                continue
            destination = os.path.join(quarantine_dir, os.path.basename(source))
            os.replace(source, destination)
            moved.append((source, destination))
    except OSError:
        for source, destination in reversed(moved):
            try:
                if not os.path.exists(source):
                    os.replace(destination, source)
            except OSError:
                log.error("Could not roll back history quarantine move",
                          exc_info=True)
        raise
    return quarantine_dir


def _rebuild_history_index(history_dir):
    conn = _open_schema_db(history_dir)
    try:
        _ensure_history_index(conn, history_dir)
        count = conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
        conn.commit()
        return count
    finally:
        conn.close()


def _is_corruption_error(error):
    message = str(error).casefold()
    return any(marker in message for marker in (
        "database disk image is malformed",
        "file is not a database",
        "file is encrypted",
        "malformed database schema",
    ))


def ensure_history_health(history_dir, force=False):
    """Check once per startup and rebuild only after proven corruption."""
    key = os.path.normcase(os.path.abspath(history_dir))
    with _health_lock:
        if not force and key in _health_results:
            return dict(_health_results[key])

        checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        database_path = _db_path(history_dir)
        result = {
            "status": "new",
            "checked_at": checked_at,
            "quick_check": "not_needed",
            "recovered_file_count": 0,
        }
        if os.path.isfile(database_path):
            try:
                _run_quick_check(database_path)
                result.update(status="healthy", quick_check="ok")
            except _HistoryCheckTimeout:
                result.update(status="check_timeout", quick_check="timeout")
                log.warning("History database quick_check reached its time limit")
            except (sqlite3.DatabaseError, _HistoryDatabaseCorrupt) as error:
                if (not isinstance(error, _HistoryDatabaseCorrupt) and
                        not _is_corruption_error(error)):
                    result.update(status="check_unavailable",
                                  quick_check="unavailable")
                    log.warning("History database health check unavailable",
                                exc_info=True)
                else:
                    log.warning("History database failed quick_check; rebuilding",
                                exc_info=True)
                    try:
                        quarantine_path = _quarantine_database(history_dir)
                        recovered_count = _rebuild_history_index(history_dir)
                        result.update(
                            status="recovered",
                            quick_check="failed",
                            quarantine_path=quarantine_path,
                            recovered_file_count=recovered_count,
                        )
                    except Exception:
                        result.update(status="recovery_failed",
                                      quick_check="failed")
                        log.error("History database recovery failed", exc_info=True)

        _health_results[key] = dict(result)
        _persist_health_report(history_dir, result)
        return dict(result)


def _connect_db(history_dir):
    ensure_history_health(history_dir)
    return _open_schema_db(history_dir)


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


def _sha256_file(filepath):
    """Hash a capture without duplicating a potentially large image in RAM."""
    digest = hashlib.sha256()
    with open(filepath, "rb") as file_obj:
        while True:
            chunk = file_obj.read(HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _index_file(conn, filepath, mtime):
    pixmap = _safe_pixmap(filepath)
    if pixmap.isNull():
        conn.execute(
            "INSERT OR REPLACE INTO seen_files (path, mtime) VALUES (?, ?)",
            (filepath, mtime))
        return
    digest = _sha256_file(filepath)
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
        try:
            _index_file(conn, filepath, mtime)
        except Exception as error:
            # One unreadable/locked capture must not abort a database rebuild
            # or hide every other intact image. The file remains for retry.
            log.warning(f"Could not index history file {filepath}: {error}")
    conn.commit()


def _escape_like(text):
    """Escape SQL LIKE wildcards so searching '100%' matches literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _history_entries(history_dir, search_text="", favorites_only=False,
                     tag_filter=""):
    if not os.path.isdir(history_dir):
        return []
    with _db(history_dir) as conn:
        _ensure_history_index(conn, history_dir)
        params = []
        where = "WHERE 1=1"
        if search_text:
            where += (" AND (created_at LIKE ? ESCAPE '\\'"
                      " OR path LIKE ? ESCAPE '\\'"
                      " OR ocr_text LIKE ? ESCAPE '\\'"
                      " OR tags LIKE ? ESCAPE '\\')")
            like = f"%{_escape_like(search_text)}%"
            params.extend([like, like, like, like])
        if favorites_only:
            where += " AND favorite = 1"
        tag = _normalize_tags(tag_filter)
        if tag:
            # Match the exact tag token via the ,tag, wrapping.
            where += " AND tags LIKE ? ESCAPE '\\'"
            params.append(f"%,{_escape_like(tag[0])},%")
        # Favorites are never dropped by the display cap: keep every favorite,
        # then fill the rest of the window with the newest non-favorites.
        rows = conn.execute(
            f"""
            SELECT path, created_at, width, height, sha256, ocr_text,
                   favorite, tags, thumbnail_blob
            FROM captures
            {where}
            ORDER BY favorite DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            (*params, config.CAPTURE_HISTORY_MAX),
        ).fetchall()
    out = []
    for row in rows:
        if not os.path.exists(row["path"]):
            continue
        d = dict(row)
        d["tags"] = _tags_from_str(d.get("tags", ""))
        out.append(d)
    return out


def set_history_favorite(history_dir, filepath, favorite):
    """Flag/unflag a capture as a favorite (protected from count retention)."""
    try:
        with _db(history_dir) as conn:
            conn.execute("UPDATE captures SET favorite = ? WHERE path = ?",
                         (1 if favorite else 0, filepath))
    except Exception as e:
        log.warning(f"Failed to update history favorite: {e}")


def set_history_tags(history_dir, filepath, tags):
    """Replace the tag set for a capture (list or comma/space string)."""
    try:
        with _db(history_dir) as conn:
            conn.execute("UPDATE captures SET tags = ? WHERE path = ?",
                         (_tags_to_str(tags), filepath))
    except Exception as e:
        log.warning(f"Failed to update history tags: {e}")


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
        # Favorites are exempt from count-based retention: only non-favorites
        # past the newest CAPTURE_HISTORY_MAX are eligible for pruning (R-31).
        old_entries = conn.execute(
            """
            SELECT path FROM captures
            WHERE favorite = 0
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
    toggle_favorite = pyqtSignal(str, bool)   # filepath, favorite
    edit_tags = pyqtSignal(str)               # filepath

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.filepath = entry["path"] if isinstance(entry, dict) else entry
        self._favorite = bool(entry.get("favorite")) if isinstance(entry, dict) else False
        self._tags = entry.get("tags", []) if isinstance(entry, dict) else []
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
        tooltip = f"{self._filename}\n{self._timestamp}"
        if self._favorite:
            tooltip += "\nFavorite (kept during history pruning)"
        if self._tags:
            tooltip += "\nTags: " + ", ".join(self._tags)
        self.setToolTip(tooltip)
        self.setFocusPolicy(Qt.StrongFocus)
        name = f"Capture {self._filename}"
        if self._favorite:
            name += ", favorite"
        if self._tags:
            name += ", tagged " + ", ".join(self._tags)
        self.setAccessibleName(name)
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

        # Favorite star (top-right) and a tag dot (top-left) indicators.
        if self._favorite:
            painter.setPen(QColor(colors["ACCENT"]))
            star_font = QFont("Segoe UI", 12)
            painter.setFont(star_font)
            painter.drawText(w - 22, 20, "★")   # ★
        if self._tags:
            painter.setPen(QColor(colors["TEXT_MUT"]))
            tag_font = QFont("Segoe UI", 8)
            painter.setFont(tag_font)
            painter.drawText(8, 18, "●")         # ● tag marker

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

        fav_act = menu.addAction(
            "Remove Favorite" if self._favorite else "Mark as Favorite")
        fav_act.triggered.connect(
            lambda: self.toggle_favorite.emit(self.filepath, not self._favorite))

        tags_label = f"Edit Tags ({len(self._tags)})…" if self._tags else "Edit Tags…"
        tags_act = menu.addAction(tags_label)
        tags_act.triggered.connect(lambda: self.edit_tags.emit(self.filepath))

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
        try:
            if sys.platform == 'win32':
                subprocess.Popen([
                    "explorer.exe",
                    f"/select,{os.path.normpath(self.filepath)}",
                ])
            else:
                folder = os.path.dirname(self.filepath)
                subprocess.Popen(['xdg-open', folder])
        except OSError as error:
            log.warning("Could not open capture location", exc_info=True)
            QMessageBox.warning(
                self,
                "Location Not Opened",
                "SwiftShot could not open this capture's folder.\n\n"
                f"{error}",
            )


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
        refresh_btn.setMinimumWidth(80)
        refresh_btn.clicked.connect(self._load_history)
        title_bar.addWidget(refresh_btn)

        self.clear_btn = QPushButton("Clear All")
        self.clear_btn.setMinimumWidth(80)
        self.clear_btn.setToolTip("Permanently delete every stored capture")
        self.clear_btn.clicked.connect(self._clear_history)
        title_bar.addWidget(self.clear_btn)

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

        self.favorites_filter = QCheckBox("Show favorites only")
        self.favorites_filter.setToolTip(
            "Favorites are protected from automatic history pruning")
        self.favorites_filter.toggled.connect(lambda _: self._load_history())
        layout.addWidget(self.favorites_filter)

        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Capture history status")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # Scroll area with grid of thumbnails
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.scroll)

        self._load_history()

    def _load_history(self):
        container = QWidget()
        self.grid = QGridLayout(container)
        self.grid.setSpacing(8)
        self.grid.setContentsMargins(8, 8, 8, 8)

        history_dir = config.CAPTURE_HISTORY_DIR
        search = self.search_box.text().strip()
        favorites_only = bool(getattr(self, "favorites_filter", None)
                              and self.favorites_filter.isChecked())
        if os.path.isdir(history_dir):
            entries = _history_entries(history_dir, search,
                                       favorites_only=favorites_only)
        else:
            entries = []   # dir not created yet — show the same empty guidance
        self.clear_btn.setEnabled(bool(_history_files(history_dir)))

        if not entries:
            if search and favorites_only:
                lbl = QLabel(f'No favorite captures match "{search}"')
            elif search:
                lbl = QLabel(f'No captures match "{search}"')
            elif favorites_only:
                lbl = QLabel("No favorites yet.\n"
                             "Right-click a capture and choose "
                             "'Mark as Favorite' to keep it here.")
            else:
                lbl = QLabel("No captures yet.\n"
                             "Screenshots you take will show up here.")
            lbl.setTextFormat(Qt.PlainText)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignCenter)
            self.grid.addWidget(lbl, 0, 0)
            self.status_label.hide()
        else:
            cols = 3
            for i, entry in enumerate(entries):
                thumb = HistoryThumbnail(entry)
                thumb.open_editor.connect(self._on_open)
                thumb.copy_clipboard.connect(self._on_copy)
                thumb.pin_image.connect(self._on_pin)
                thumb.delete_entry.connect(self._on_delete)
                thumb.toggle_favorite.connect(self._on_toggle_favorite)
                thumb.edit_tags.connect(self._on_edit_tags)
                self.grid.addWidget(thumb, i // cols, i % cols)
            suffix = "result" if len(entries) == 1 else "results"
            self.status_label.setText(f"Showing {len(entries)} {suffix}.")
            self.status_label.show()

        self.scroll.setWidget(container)

    def _on_open(self, filepath):
        self.open_in_editor.emit(filepath)

    def _on_copy(self, filepath):
        pixmap = _safe_pixmap(filepath)
        if not pixmap.isNull():
            try:
                QApplication.clipboard().setPixmap(pixmap)
            except Exception as error:
                log.warning("Could not copy history image", exc_info=True)
                QMessageBox.warning(
                    self,
                    "Capture Not Copied",
                    "Windows did not accept this image on the clipboard. "
                    "Try opening it in the editor and copying again.\n\n"
                    f"{error}",
                )
                return
            self.status_label.setText(
                f"Copied {os.path.basename(filepath)} to the clipboard.")
            self.status_label.show()
        else:
            QMessageBox.warning(
                self,
                "Capture Not Copied",
                "SwiftShot could not read this capture. Refresh history; if "
                "the item remains, verify that the image file is intact.",
            )

    def _on_pin(self, filepath):
        self.pin_to_desktop.emit(filepath)

    def _on_toggle_favorite(self, filepath, favorite):
        set_history_favorite(config.CAPTURE_HISTORY_DIR, filepath, favorite)
        self.status_label.setText(
            f"{'Marked' if favorite else 'Unmarked'} "
            f"{os.path.basename(filepath)} as favorite.")
        self.status_label.show()
        self._load_history()

    def _on_edit_tags(self, filepath):
        with _db(config.CAPTURE_HISTORY_DIR) as conn:
            row = conn.execute("SELECT tags FROM captures WHERE path = ?",
                               (filepath,)).fetchone()
        current = ", ".join(_tags_from_str(row["tags"])) if row else ""
        text, ok = QInputDialog.getText(
            self, "Edit Tags",
            "Comma-separated tags (e.g. invoice, receipt):", text=current)
        if not ok:
            return
        set_history_tags(config.CAPTURE_HISTORY_DIR, filepath, text)
        self.status_label.setText(f"Updated tags for {os.path.basename(filepath)}.")
        self.status_label.show()
        self._load_history()

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
        self.status_label.setText(f"Deleted {filename}.")
        self.status_label.show()

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
        else:
            self.status_label.setText(
                f"Deleted all {len(removed_paths)} stored capture file(s).")
            self.status_label.show()


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
