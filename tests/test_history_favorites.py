"""Favorites + tags with a reversible migration and retention protection (R-31)."""

import sqlite3
import sys
from pathlib import Path

from PyQt5.QtGui import QColor, QPixmap


def _load(fresh_config, tmp_path, max_items=10):
    cfg = fresh_config.config
    cfg.CAPTURE_HISTORY_ENABLED = True
    cfg.CAPTURE_HISTORY_DIR = str(tmp_path)
    cfg.CAPTURE_HISTORY_MAX = max_items
    sys.modules.pop("capture_history", None)
    import capture_history
    return capture_history


def _save(ch, n, tmp_path):
    px = QPixmap(8 + n, 8)      # unique size -> unique sha256
    px.fill(QColor(n * 7 % 256, n, 50))
    return ch.save_to_history(px)


# ── tag normalization (pure) ────────────────────────────────────────────────

def test_normalize_tags_dedupes_sorts_lowercases(fresh_config, qapp, tmp_path):
    ch = _load(fresh_config, tmp_path)
    assert ch._normalize_tags("Invoice, receipt, INVOICE") == ["invoice", "receipt"]
    assert ch._normalize_tags(["  A ", "b", "a"]) == ["a", "b"]
    assert ch._normalize_tags("") == []


def test_tags_str_roundtrip(fresh_config, qapp, tmp_path):
    ch = _load(fresh_config, tmp_path)
    s = ch._tags_to_str(["b", "a"])
    assert s == ",a,b,"                       # wrapped, sorted
    assert ch._tags_from_str(s) == ["a", "b"]


# ── migration adds columns to an existing v1 database ───────────────────────

def test_migration_adds_favorite_and_tags_to_existing_db(fresh_config, qapp, tmp_path):
    # Build a v1-style DB (no favorite/tags) with one row.
    db = Path(tmp_path) / "history.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE captures (
        id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
        sha256 TEXT NOT NULL UNIQUE, ocr_text TEXT NOT NULL DEFAULT '',
        thumbnail_blob BLOB NOT NULL)""")
    conn.execute("INSERT INTO captures (path, created_at, width, height, sha256, "
                 "thumbnail_blob) VALUES (?,?,?,?,?,?)",
                 (str(tmp_path / "a.png"), "2026-01-01T00:00:00", 8, 8, "deadbeef", b"x"))
    conn.commit(); conn.close()

    ch = _load(fresh_config, tmp_path)
    with ch._db(str(tmp_path)) as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(captures)")}
        assert "favorite" in cols and "tags" in cols
        assert c.execute("PRAGMA user_version").fetchone()[0] == ch.HISTORY_SCHEMA_VERSION
    # A backup of the pre-migration DB was written (reversible).
    assert list(Path(tmp_path).glob("history.pre-favorites.*.bak"))


# ── favorite / tags setters + filtered search ───────────────────────────────

def test_favorite_and_tag_search(fresh_config, qapp, tmp_path):
    ch = _load(fresh_config, tmp_path)
    p1 = _save(ch, 1, tmp_path)
    _save(ch, 2, tmp_path)

    ch.set_history_favorite(str(tmp_path), p1, True)
    ch.set_history_tags(str(tmp_path), p1, "invoice, receipt")

    favs = ch._history_entries(str(tmp_path), favorites_only=True)
    assert len(favs) == 1 and favs[0]["path"] == p1
    assert favs[0]["favorite"] == 1
    assert favs[0]["tags"] == ["invoice", "receipt"]

    # Tag filter matches the exact token, and free-text search matches tags too.
    assert len(ch._history_entries(str(tmp_path), tag_filter="invoice")) == 1
    assert ch._history_entries(str(tmp_path), tag_filter="invoi") == []
    assert len(ch._history_entries(str(tmp_path), "receipt")) == 1


def test_favorites_survive_count_retention(fresh_config, qapp, tmp_path):
    # Save with a high cap so nothing auto-prunes during setup.
    ch = _load(fresh_config, tmp_path, max_items=10)
    paths = [_save(ch, i, tmp_path) for i in range(1, 5)]  # 4 captures
    ch.set_history_favorite(str(tmp_path), paths[0], True)  # oldest = favorite

    # Now tighten retention and prune explicitly.
    fresh_config.config.CAPTURE_HISTORY_MAX = 2
    ch._prune_history_retention(str(tmp_path))

    # The oldest is a favorite -> protected; a non-favorite was pruned instead.
    assert Path(paths[0]).exists()
    with ch._db(str(tmp_path)) as c:
        rows = {r["path"] for r in c.execute("SELECT path FROM captures")}
    assert paths[0] in rows
    assert Path(paths[-1]).exists()   # newest non-favorite kept
    assert not Path(paths[1]).exists()  # an old non-favorite pruned
