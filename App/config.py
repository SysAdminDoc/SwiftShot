"""
SwiftShot Configuration Manager
Handles all settings persistence via JSON file.
Includes config backup, reset-to-defaults, import/export, and recent color tracking.
"""

import os
import json
import getpass
import re
import shutil
from pathlib import Path


OUTPUT_FILE_FORMAT_CHOICES = ("png", "jpg", "bmp", "gif", "tiff", "webp")
AFTER_CAPTURE_ACTION_CHOICES = ("editor", "save", "clipboard")
FILENAME_TEMPLATE_HELP = (
    "Variables: {YYYY}, {MM}, {DD}, {hh}, {mm}, {ss}, "
    "{app}, {title}, {user}, {counter}, {w}, {h}"
)
_FILENAME_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class Config:
    """Application configuration with sensible defaults."""

    APP_NAME = "SwiftShot"
    APP_VERSION = "2.6.5"

    # --- Capture Settings ---
    CAPTURE_MOUSE_POINTER = False
    CAPTURE_DELAY_MS = 0
    CAPTURE_REGION_HOTKEY = "Print"
    CAPTURE_WINDOW_HOTKEY = "Alt+Print"
    CAPTURE_FULLSCREEN_HOTKEY = "Ctrl+Print"
    CAPTURE_LAST_REGION_HOTKEY = "Shift+Print"
    CAPTURE_OCR_HOTKEY = ""
    CAPTURE_FREEHAND_HOTKEY = ""
    CAPTURE_SCROLLING_HOTKEY = ""

    # --- Timed Capture ---
    CAPTURE_TIMER_ENABLED = False
    CAPTURE_TIMER_SECONDS = 3

    # --- Output Settings ---
    OUTPUT_FILE_FORMAT = "png"
    OUTPUT_JPEG_QUALITY = 90
    OUTPUT_FILE_PATH = ""
    OUTPUT_FILENAME_PATTERN = "SwiftShot_{YYYY}-{MM}-{DD}_{hh}-{mm}-{ss}"
    OUTPUT_FILE_INCREMENT = True

    # --- After Capture ---
    AFTER_CAPTURE_ACTION = "editor"   # "editor", "save", "clipboard"
    AFTER_CAPTURE_ACTIONS = ["editor"]
    COPY_PATH_TO_CLIPBOARD = False
    PLAY_CAMERA_SOUND = True

    # --- Editor Settings ---
    EDITOR_MATCH_CAPTURE_SIZE = True
    EDITOR_DEFAULT_COLOR = "#f38ba8"
    EDITOR_DEFAULT_LINE_WIDTH = 2
    EDITOR_DEFAULT_FONT_SIZE = 14
    EDITOR_DEFAULT_FONT_FAMILY = "Segoe UI"
    EDITOR_HIGHLIGHT_COLOR = "#f9e2af"
    EDITOR_OBFUSCATE_FACTOR = 12
    EDITOR_OBFUSCATE_MODE = "pixelate"   # "pixelate" or "blur"
    EDITOR_SHOW_MAGNIFIER = True
    EDITOR_REUSE_EDITOR = False
    EDITOR_RECENT_COLORS = []  # list of hex strings, max 12

    # --- Border / Shadow / Rounded Corners ---
    BORDER_ENABLED = False
    BORDER_COLOR = "#45475a"
    BORDER_WIDTH = 3
    SHADOW_ENABLED = False
    SHADOW_RADIUS = 15
    SHADOW_COLOR = "#000000"
    SHADOW_OPACITY = 80
    ROUNDED_CORNERS_ENABLED = False
    ROUNDED_CORNERS_RADIUS = 12

    # --- Pin Window ---
    PIN_OPACITY = 95
    PIN_BORDER_COLOR = "#89b4fa"

    # --- Capture History ---
    CAPTURE_HISTORY_ENABLED = True
    CAPTURE_HISTORY_MAX = 50
    CAPTURE_HISTORY_DIR = ""

    # --- Clipboard Watcher ---
    CLIPBOARD_WATCHER_ENABLED = False

    # --- General ---
    LAUNCH_AT_STARTUP = False
    MINIMIZE_TO_TRAY = True
    CHECK_FOR_UPDATES = True
    SHOW_NOTIFICATIONS = True
    LANGUAGE = "en-US"
    THEME = "dark"  # "dark" or "light"

    # --- Persisted State ---
    LAST_SAVE_DIR = ""
    LAST_REGION = ""
    WINDOW_GEOMETRY = ""

    _STATE_KEYS = {"LAST_SAVE_DIR", "LAST_REGION", "WINDOW_GEOMETRY",
                   "CAPTURE_HISTORY_DIR"}

    def __init__(self):
        self._config_dir = self._get_config_dir()
        self._config_file = os.path.join(self._config_dir, "swiftshot.json")
        self._ensure_history_dir()
        self._load()

    def _get_config_dir(self):
        if os.name == 'nt':
            base = os.environ.get('APPDATA', os.path.expanduser('~'))
        else:
            base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        config_dir = os.path.join(base, self.APP_NAME)
        os.makedirs(config_dir, exist_ok=True)
        return config_dir

    def _ensure_history_dir(self):
        if not self.CAPTURE_HISTORY_DIR:
            self.CAPTURE_HISTORY_DIR = os.path.join(self._config_dir, "history")
        os.makedirs(self.CAPTURE_HISTORY_DIR, exist_ok=True)

    def _get_saveable_keys(self):
        return [k for k in dir(self) if k.isupper() and not k.startswith('_')]

    def _load(self):
        if not os.path.exists(self._config_file):
            return
        try:
            with open(self._config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self, key) and key.isupper():
                    setattr(self, key, value)
            if "AFTER_CAPTURE_ACTIONS" not in data:
                self.AFTER_CAPTURE_ACTIONS = [self.AFTER_CAPTURE_ACTION]
            self._normalize_after_capture_actions()
        except json.JSONDecodeError:
            backup = self._config_file + ".corrupt"
            try:
                shutil.copy2(self._config_file, backup)
            except Exception:
                pass
        except Exception:
            pass

    def save(self):
        data = {k: getattr(self, k) for k in self._get_saveable_keys()}
        try:
            tmp_path = self._config_file + ".tmp"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self._config_file)
        except Exception:
            pass

    def reset_to_defaults(self):
        """Reset all settings to class-level defaults (preserves state keys)."""
        saved_state = {k: getattr(self, k) for k in self._STATE_KEYS
                       if hasattr(self, k)}
        for key in self._get_saveable_keys():
            if key in self._STATE_KEYS:
                continue
            cls_val = getattr(Config, key, None)
            if cls_val is not None:
                setattr(self, key, cls_val if not isinstance(cls_val, list)
                        else list(cls_val))
        for k, v in saved_state.items():
            setattr(self, k, v)
        self._normalize_after_capture_actions()
        self.save()

    def export_settings(self, filepath):
        """Export user settings to a JSON file (excludes internal state)."""
        data = {}
        for key in self._get_saveable_keys():
            if key not in self._STATE_KEYS:
                data[key] = getattr(self, key)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    def import_settings(self, filepath):
        """Import settings from a JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self, key) and key.isupper() and key not in self._STATE_KEYS:
                    setattr(self, key, value)
            if "AFTER_CAPTURE_ACTIONS" not in data:
                self.AFTER_CAPTURE_ACTIONS = [self.AFTER_CAPTURE_ACTION]
            self._normalize_after_capture_actions()
            self.save()
            return True
        except Exception:
            return False

    def add_recent_color(self, hex_color):
        """Track recently used colors (max 12, most recent first)."""
        hex_color = hex_color.lower()
        if hex_color in self.EDITOR_RECENT_COLORS:
            self.EDITOR_RECENT_COLORS.remove(hex_color)
        self.EDITOR_RECENT_COLORS.insert(0, hex_color)
        if len(self.EDITOR_RECENT_COLORS) > 12:
            self.EDITOR_RECENT_COLORS = self.EDITOR_RECENT_COLORS[:12]

    def _normalize_after_capture_actions(self):
        configured = getattr(self, "AFTER_CAPTURE_ACTIONS", None)
        if isinstance(configured, str):
            configured = [configured]
        if not isinstance(configured, list):
            configured = []

        actions = []
        for action in configured:
            if action in AFTER_CAPTURE_ACTION_CHOICES and action not in actions:
                actions.append(action)

        legacy_action = getattr(self, "AFTER_CAPTURE_ACTION", "editor")
        if not actions and legacy_action in AFTER_CAPTURE_ACTION_CHOICES:
            actions = [legacy_action]
        if not actions:
            actions = ["editor"]

        self.AFTER_CAPTURE_ACTIONS = actions
        self.AFTER_CAPTURE_ACTION = actions[0]

    def get_after_capture_actions(self):
        self._normalize_after_capture_actions()
        return list(self.AFTER_CAPTURE_ACTIONS)

    def get_output_directory(self):
        if self.OUTPUT_FILE_PATH and os.path.isdir(self.OUTPUT_FILE_PATH):
            return self.OUTPUT_FILE_PATH
        if os.name == 'nt':
            try:
                import ctypes.wintypes
                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)
                desktop = buf.value
                if os.path.isdir(desktop):
                    return desktop
            except Exception:
                pass
        return os.path.expanduser("~/Desktop")

    def _sanitize_filename(self, name):
        name = _FILENAME_UNSAFE_RE.sub("_", str(name))
        name = " ".join(name.split())
        name = name.strip(" ._")
        return name or "SwiftShot"

    def _render_filename_pattern(
        self,
        pattern=None,
        now=None,
        app_name="",
        window_title="",
        user_name=None,
        width=None,
        height=None,
        counter=1,
    ):
        from datetime import datetime

        now = now or datetime.now()
        variables = {
            "YYYY": now.strftime("%Y"),
            "MM": now.strftime("%m"),
            "DD": now.strftime("%d"),
            "hh": now.strftime("%H"),
            "mm": now.strftime("%M"),
            "ss": now.strftime("%S"),
            "app": app_name or "app",
            "title": window_title or "window",
            "user": user_name or getpass.getuser(),
            "counter": f"{int(counter):03d}",
            "w": str(width or 0),
            "h": str(height or 0),
        }

        name = pattern if pattern is not None else self.OUTPUT_FILENAME_PATTERN
        for key, value in variables.items():
            name = name.replace(f"{{{key}}}", str(value))
        return self._sanitize_filename(name)

    def preview_filename(
        self,
        pattern=None,
        file_format=None,
        width=1920,
        height=1080,
        app_name="notepad",
        window_title="Release notes",
        user_name=None,
    ):
        name = self._render_filename_pattern(
            pattern=pattern,
            app_name=app_name,
            window_title=window_title,
            user_name=user_name,
            width=width,
            height=height,
            counter=1,
        )
        ext = (file_format or self.OUTPUT_FILE_FORMAT).lower()
        return f"{name}.{ext}"

    def get_filename(
        self,
        app_name="",
        window_title="",
        user_name=None,
        width=None,
        height=None,
    ):
        pattern = self.OUTPUT_FILENAME_PATTERN

        ext = self.OUTPUT_FILE_FORMAT.lower()
        output_dir = self.get_output_directory()
        uses_counter = "{counter}" in pattern
        counter = 1
        name = self._render_filename_pattern(
            pattern=pattern,
            app_name=app_name,
            window_title=window_title,
            user_name=user_name,
            width=width,
            height=height,
            counter=counter,
        )
        full_path = os.path.join(output_dir, f"{name}.{ext}")

        if self.OUTPUT_FILE_INCREMENT and os.path.exists(full_path):
            while os.path.exists(full_path):
                counter += 1
                if uses_counter:
                    name = self._render_filename_pattern(
                        pattern=pattern,
                        app_name=app_name,
                        window_title=window_title,
                        user_name=user_name,
                        width=width,
                        height=height,
                        counter=counter,
                    )
                    full_path = os.path.join(output_dir, f"{name}.{ext}")
                else:
                    full_path = os.path.join(
                        output_dir,
                        f"{name}_{counter - 1}.{ext}"
                    )

        return full_path

    @property
    def config_dir(self):
        return self._config_dir

    @property
    def log_file(self):
        return os.path.join(self._config_dir, "swiftshot.log")


# Global config instance
config = Config()
