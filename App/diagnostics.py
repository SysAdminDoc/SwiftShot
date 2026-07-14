"""Privacy-safe SwiftShot diagnostics bundles.

Bundles are built from explicit schemas and sanitized text. They never copy a
configuration file, history database, capture, or malformed input verbatim.
"""

import glob
import json
import os
import platform
import re
import sqlite3
import sys
import zipfile
from datetime import datetime


DIAGNOSTICS_SCHEMA_VERSION = 2
MAX_TEXT_FILE_BYTES = 512 * 1024

# This is the complete configuration export surface. Path/state/geometry,
# filename templates, recent colors, and unknown future keys are deliberately
# absent. Adding a setting to Config does not add it to diagnostics. Each field
# also has a value contract so a malformed safe-named setting cannot smuggle a
# path, username, or secret into the bundle.
_BOOL_CONFIG_FIELDS = frozenset({
    "CAPTURE_MOUSE_POINTER",
    "CAPTURE_TIMER_ENABLED",
    "OUTPUT_FILE_INCREMENT",
    "COPY_PATH_TO_CLIPBOARD",
    "PLAY_CAMERA_SOUND",
    "EDITOR_MATCH_CAPTURE_SIZE",
    "EDITOR_SHOW_MAGNIFIER",
    "EDITOR_REUSE_EDITOR",
    "BORDER_ENABLED",
    "SHADOW_ENABLED",
    "ROUNDED_CORNERS_ENABLED",
    "BACKDROP_ENABLED",
    "CAPTURE_HISTORY_ENABLED",
    "CAPTURE_HISTORY_AUTO_OCR",
    "CLIPBOARD_WATCHER_ENABLED",
    "LAUNCH_AT_STARTUP",
    "CHECK_FOR_UPDATES",
    "SHOW_NOTIFICATIONS",
})
_INT_CONFIG_FIELDS = frozenset({
    "CAPTURE_DELAY_MS",
    "CAPTURE_TIMER_SECONDS",
    "OUTPUT_JPEG_QUALITY",
    "EDITOR_DEFAULT_LINE_WIDTH",
    "EDITOR_DEFAULT_FONT_SIZE",
    "EDITOR_OBFUSCATE_FACTOR",
    "BORDER_WIDTH",
    "SHADOW_RADIUS",
    "SHADOW_OPACITY",
    "ROUNDED_CORNERS_RADIUS",
    "BACKDROP_PADDING",
    "PIN_OPACITY",
    "CAPTURE_HISTORY_MAX",
})
_HOTKEY_CONFIG_FIELDS = frozenset({
    "CAPTURE_REGION_HOTKEY",
    "CAPTURE_WINDOW_HOTKEY",
    "CAPTURE_FULLSCREEN_HOTKEY",
    "CAPTURE_LAST_REGION_HOTKEY",
    "CAPTURE_OCR_HOTKEY",
    "CAPTURE_FREEHAND_HOTKEY",
    "CAPTURE_SCROLLING_HOTKEY",
    "CAPTURE_COLOR_PICKER_HOTKEY",
})
_ENUM_CONFIG_FIELDS = {
    "OUTPUT_FILE_FORMAT": frozenset({
        "png", "jpg", "bmp", "gif", "tiff", "webp", "avif",
    }),
    "AFTER_CAPTURE_ACTION": frozenset({"editor", "save", "clipboard"}),
    "EDITOR_OBFUSCATE_MODE": frozenset({"pixelate", "blur"}),
    "BEAUTIFY_PRESET": frozenset({"none", "presentation", "social"}),
    "BACKDROP_TYPE": frozenset({"solid", "gradient"}),
    "BACKDROP_FRAME": frozenset({"none", "macos", "windows"}),
    "THEME": frozenset({"dark", "light"}),
}
_LIST_ENUM_CONFIG_FIELDS = {
    "AFTER_CAPTURE_ACTIONS": frozenset({"editor", "save", "clipboard"}),
}
CONFIG_FIELD_ALLOWLIST = frozenset(
    _BOOL_CONFIG_FIELDS
    | _INT_CONFIG_FIELDS
    | _HOTKEY_CONFIG_FIELDS
    | _ENUM_CONFIG_FIELDS.keys()
    | _LIST_ENUM_CONFIG_FIELDS.keys()
)

LEGACY_EDITOR_FIELD_ALLOWLIST = frozenset({"ui_scale"})
_HOTKEY_VALUE_RE = re.compile(r"[A-Za-z0-9+ _-]{0,64}\Z")

_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([a-z0-9_-]*(?:token|secret|password|passwd|api[_-]?key|authorization)"
    r"[a-z0-9_-]*)\b(\s*[:=]\s*)[^,;\r\n]+"
)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_WINDOWS_PATH_RE = re.compile(r"(?i)(?<![\w])(?:[A-Z]:[\\/]|\\\\)[^\r\n\"<>|]+")
_POSIX_USER_PATH_RE = re.compile(
    r"(?<![\w])/(?:Users|home|tmp|var|etc|opt|mnt|Volumes)/[^\r\n\"<>|]+"
)


def _valid_config_value(key, value):
    """Return whether an allowlisted setting also has a non-sensitive shape."""
    if key in _BOOL_CONFIG_FIELDS:
        return type(value) is bool
    if key in _INT_CONFIG_FIELDS:
        return type(value) is int
    if key in _HOTKEY_CONFIG_FIELDS:
        return isinstance(value, str) and bool(_HOTKEY_VALUE_RE.fullmatch(value))
    if key in _ENUM_CONFIG_FIELDS:
        return isinstance(value, str) and value in _ENUM_CONFIG_FIELDS[key]
    if key in _LIST_ENUM_CONFIG_FIELDS:
        choices = _LIST_ENUM_CONFIG_FIELDS[key]
        return (
            isinstance(value, list)
            and len(value) <= len(choices)
            and all(isinstance(item, str) and item in choices for item in value)
        )
    return False


def _valid_legacy_editor_value(key, value):
    return (
        key == "ui_scale"
        and type(value) in (int, float)
        and 0.5 <= value <= 3.0
    )


def _config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "SwiftShot")


def _app_version():
    try:
        from config import Config
        return Config.APP_VERSION
    except Exception:
        return "unknown"


def _wgc_available():
    """Whether a Windows Graphics Capture backend package is importable."""
    for mod in ("windows_capture", "winrt.windows.graphics.capture"):
        try:
            __import__(mod)
            return True
        except Exception:
            continue
    return False


def collect_versions():
    """Return the allowlisted runtime manifest."""
    info = {
        "swiftshot": _app_version(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "frozen": bool(getattr(sys, "frozen", False)),
        "windows_graphics_capture": _wgc_available(),
    }
    try:
        from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        info["qt"] = QT_VERSION_STR
        info["pyqt5"] = PYQT_VERSION_STR
    except Exception:
        pass
    try:
        import PIL
        info["pillow"] = PIL.__version__
    except Exception:
        pass
    try:
        import numpy
        info["numpy"] = numpy.__version__
    except Exception:
        pass
    return info


class PathPseudonymizer:
    """Assign stable, bundle-local aliases without retaining path components."""

    def __init__(self):
        self._aliases = {}
        self._known_literals = {}

    @staticmethod
    def _key(path):
        return os.path.normcase(os.path.normpath(str(path))).casefold()

    def alias(self, path):
        raw = str(path)
        key = self._key(path)
        if key not in self._aliases:
            self._aliases[key] = f"<PATH-{len(self._aliases) + 1:03d}>"
        alias = self._aliases[key]
        if raw:
            variants = {raw, raw.replace("\\", "/"), raw.replace("/", "\\")}
            basename = raw.replace("\\", "/").rsplit("/", 1)[-1]
            if basename:
                variants.add(basename)
            for literal in variants:
                self._known_literals[literal] = alias
        return alias

    def sanitize_text(self, text):
        """Pseudonymize paths/users and redact secret assignments in text."""
        def replace_path(match):
            return self.alias(match.group(0).rstrip())

        sanitized = text
        for literal in sorted(self._known_literals, key=len, reverse=True):
            sanitized = re.sub(
                re.escape(literal),
                self._known_literals[literal],
                sanitized,
                flags=re.IGNORECASE,
            )
        sanitized = _WINDOWS_PATH_RE.sub(replace_path, sanitized)
        sanitized = _POSIX_USER_PATH_RE.sub(replace_path, sanitized)
        sanitized = _SECRET_ASSIGNMENT_RE.sub(
            lambda m: f"{m.group(1)}{m.group(2)}***redacted***",
            sanitized,
        )
        sanitized = _EMAIL_RE.sub("<EMAIL>", sanitized)

        usernames = {
            os.environ.get("USERNAME", ""),
            os.environ.get("USER", ""),
            os.path.basename(os.path.expanduser("~")),
        }
        for username in sorted(filter(None, usernames), key=len, reverse=True):
            sanitized = re.sub(
                rf"(?i)(?<![\w]){re.escape(username)}(?![\w])",
                "<USER>",
                sanitized,
            )
        return sanitized


def _load_json_object(path):
    """Parse an object without ever returning malformed source text."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {
                "status": "malformed",
                "error": "root value is not an object",
                "data": {},
            }
    except json.JSONDecodeError as error:
        return {
            "status": "malformed",
            "error": f"invalid JSON at line {error.lineno}, column {error.colno}",
            "data": {},
        }
    except (OSError, UnicodeError) as error:
        return {
            "status": "unreadable",
            "error": type(error).__name__,
            "data": {},
        }
    return {"status": "ok", "data": data}


def _safe_json_file(path, allowlist, value_validator):
    """Read an object JSON file into a schema-validated safe record."""
    loaded = _load_json_object(path)
    if loaded["status"] != "ok":
        return {
            "status": loaded["status"],
            "error": loaded["error"],
            "settings": {},
        }
    data = loaded["data"]
    settings = {}
    invalid_fields = []
    for key in sorted(allowlist):
        if key not in data:
            continue
        if value_validator(key, data[key]):
            settings[key] = data[key]
        else:
            invalid_fields.append(key)
    return {
        "status": "ok",
        "settings": settings,
        "invalid_fields": invalid_fields,
    }


def _recent_file_aliases(path, pseudonymizer):
    loaded = _load_json_object(path)
    if loaded["status"] != "ok":
        return {"status": loaded["status"], "items": []}
    recent = loaded["data"].get("recent", [])
    if not isinstance(recent, list):
        return {"status": "malformed", "items": []}
    aliases = []
    for item in recent[:50]:
        if isinstance(item, str):
            aliases.append(pseudonymizer.alias(item))
    return {"status": "ok", "count": len(aliases), "items": aliases}


def _read_sanitized_text(path, pseudonymizer):
    """Read at most the newest 512 KiB and never return undecoded raw bytes."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - MAX_TEXT_FILE_BYTES)
            handle.seek(start)
            payload = handle.read(MAX_TEXT_FILE_BYTES)
    except OSError:
        return None
    text = payload.decode("utf-8", errors="replace")
    if start:
        text = "[older log content omitted]\n" + text
    return pseudonymizer.sanitize_text(text)


def diagnostics_preview(config_dir=None):
    """Describe included categories without exposing filenames or contents."""
    cfg_dir = config_dir or _config_dir()
    log_count = len(glob.glob(os.path.join(cfg_dir, "swiftshot.log*")))
    if os.path.isfile(os.path.join(cfg_dir, "crash.log")):
        log_count += 1
    config_count = sum(
        os.path.isfile(os.path.join(cfg_dir, name))
        for name in ("swiftshot.json", "config.json")
    )
    recent = os.path.isfile(os.path.join(cfg_dir, "recent.json"))
    included = ["Runtime and dependency versions"]
    if log_count:
        included.append(f"Sanitized application/crash logs ({log_count})")
    if config_count:
        included.append("Allowlisted non-path settings")
    if recent:
        included.append("Pseudonymized recent-file entries")
    return {
        "included": included,
        "excluded": [
            "Screenshots, clipboard/OCR content, and capture-history files",
            "History database and window/capture geometry",
            "Raw configuration, paths, usernames, and secret values",
        ],
    }


def format_diagnostics_preview(preview):
    """Format the category preview for the GUI confirmation dialog."""
    included = "\n".join(f"  • {item}" for item in preview["included"])
    excluded = "\n".join(f"  • {item}" for item in preview["excluded"])
    return (
        "SwiftShot will create a local diagnostics bundle.\n\n"
        f"Included:\n{included}\n\nNever included:\n{excluded}\n\n"
        "Review the ZIP before sharing it. Continue?"
    )


def _privacy_manifest(preview):
    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "privacy": "paths/usernames are pseudonymized; secrets are redacted",
        **preview,
    }


def build_diagnostics_zip(dest_path=None, config_dir=None):
    """Write a sanitized diagnostics zip and return its path."""
    cfg_dir = config_dir or _config_dir()
    if dest_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(cfg_dir, f"swiftshot-diagnostics-{stamp}.zip")

    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    pseudonymizer = PathPseudonymizer()
    preview = diagnostics_preview(cfg_dir)
    recent_path = os.path.join(cfg_dir, "recent.json")
    recent_record = None
    if os.path.isfile(recent_path):
        # Register paths and basenames before sanitizing logs so the same
        # bundle-local aliases are used everywhere they appear.
        recent_record = _recent_file_aliases(recent_path, pseudonymizer)

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, log_path in enumerate(sorted(
                glob.glob(os.path.join(cfg_dir, "swiftshot.log*"))), start=1):
            text = _read_sanitized_text(log_path, pseudonymizer)
            if text is not None:
                suffix = "" if index == 1 else f".{index - 1}"
                archive.writestr(f"logs/swiftshot.log{suffix}", text)

        crash_path = os.path.join(cfg_dir, "crash.log")
        if os.path.isfile(crash_path):
            text = _read_sanitized_text(crash_path, pseudonymizer)
            if text is not None:
                archive.writestr("logs/crash.log", text)

        config_records = {}
        config_specs = (
            ("swiftshot.json", CONFIG_FIELD_ALLOWLIST, _valid_config_value),
            ("config.json", LEGACY_EDITOR_FIELD_ALLOWLIST,
             _valid_legacy_editor_value),
        )
        for name, allowlist, validator in config_specs:
            path = os.path.join(cfg_dir, name)
            if os.path.isfile(path):
                config_records[name] = _safe_json_file(
                    path, allowlist, validator
                )
        if config_records:
            archive.writestr(
                "configuration.json", json.dumps(config_records, indent=2)
            )

        if recent_record is not None:
            archive.writestr(
                "recent-files.json",
                json.dumps(recent_record, indent=2),
            )

        archive.writestr("versions.json", json.dumps(collect_versions(), indent=2))
        archive.writestr(
            "manifest.json", json.dumps(_privacy_manifest(preview), indent=2)
        )
    return dest_path
