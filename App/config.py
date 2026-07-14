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
import tempfile


MAX_CONFIG_BYTES = 1024 * 1024
MAX_FILENAME_PATTERN_LENGTH = 512
MAX_FILENAME_STEM_LENGTH = 180
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _read_json_object(path):
    with open(path, "rb") as file_obj:
        payload = file_obj.read(MAX_CONFIG_BYTES + 1)
    if len(payload) > MAX_CONFIG_BYTES:
        raise ValueError("settings file exceeds the 1 MiB safety limit")
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("settings file must contain a JSON object")
    return data


def _atomic_write_json(path, data):
    payload = json.dumps(data, indent=2).encode("utf-8")
    if len(payload) > MAX_CONFIG_BYTES:
        raise ValueError("settings data exceeds the 1 MiB safety limit")
    destination = os.path.abspath(path)
    parent = os.path.dirname(destination) or "."
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(destination)}.", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "wb") as file_obj:
            file_obj.write(payload)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temp_path, destination)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def _avif_supported():
    """AVIF export is available only when Pillow was built with libavif
    (bundled in the 12.3.0+ wheels). Probe at import so the format is offered
    only when it will actually save."""
    try:
        from PIL import features
        return features.check("avif")
    except Exception:
        return False


OUTPUT_FILE_FORMAT_CHOICES = ("png", "jpg", "bmp", "gif", "tiff", "webp")
if _avif_supported():
    OUTPUT_FILE_FORMAT_CHOICES = OUTPUT_FILE_FORMAT_CHOICES + ("avif",)
AFTER_CAPTURE_ACTION_CHOICES = ("editor", "save", "clipboard")
BACKDROP_FRAME_CHOICES = ("none", "macos", "windows")
BEAUTIFICATION_PRESETS = {
    "none": {
        "label": "None",
        "padding": 0,
        "background": None,
        "corner_radius": 0,
        "shadow_radius": 0,
        "shadow_offset": (0, 0),
        "shadow_opacity": 0,
    },
    "presentation": {
        "label": "Presentation",
        "padding": 36,
        "background": "#f8fafc",
        "corner_radius": 14,
        "shadow_radius": 24,
        "shadow_offset": (0, 12),
        "shadow_opacity": 96,
    },
    "social": {
        "label": "Social Media",
        "padding": 52,
        "background": "#e0f2fe",
        "corner_radius": 18,
        "shadow_radius": 28,
        "shadow_offset": (0, 16),
        "shadow_opacity": 88,
    },
}
FILENAME_TEMPLATE_HELP = (
    "Variables: {YYYY}, {MM}, {DD}, {hh}, {mm}, {ss}, "
    "{app}, {title}, {user}, {counter}, {w}, {h}"
)
_FILENAME_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class Config:
    """Application configuration with sensible defaults."""

    APP_NAME = "SwiftShot"
    APP_VERSION = "2.8.0"

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
    CAPTURE_COLOR_PICKER_HOTKEY = ""   # grab the pixel under the cursor as hex

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
    BEAUTIFY_PRESET = "none"

    # --- Backdrop (padded solid/gradient background behind the capture) ---
    BACKDROP_ENABLED = False
    BACKDROP_TYPE = "solid"          # "solid" | "gradient"
    BACKDROP_COLOR = "#1e1e2e"
    BACKDROP_COLOR2 = "#45475a"      # gradient end colour
    BACKDROP_PADDING = 48
    BACKDROP_FRAME = "none"          # "none" | "macos" | "windows" window chrome

    # --- Pin Window ---
    PIN_OPACITY = 95
    PIN_BORDER_COLOR = "#89b4fa"

    # --- Capture History ---
    CAPTURE_HISTORY_ENABLED = True
    CAPTURE_HISTORY_MAX = 50
    CAPTURE_HISTORY_DIR = ""
    CAPTURE_HISTORY_AUTO_OCR = False

    # --- Clipboard Watcher ---
    CLIPBOARD_WATCHER_ENABLED = False

    # --- General ---
    LAUNCH_AT_STARTUP = False
    CHECK_FOR_UPDATES = True
    SHOW_NOTIFICATIONS = True
    THEME = "dark"  # "dark" or "light"

    # --- Persisted State ---
    LAST_SAVE_DIR = ""
    LAST_REGION = ""
    WINDOW_GEOMETRY = ""

    _STATE_KEYS = {"LAST_SAVE_DIR", "LAST_REGION", "WINDOW_GEOMETRY",
                   "CAPTURE_HISTORY_DIR"}
    # Identity constants: never persisted, never overwritten from a file.
    # (Older builds saved APP_VERSION into swiftshot.json, which pinned the
    # running version string to the release the config was written by.)
    _IDENTITY_KEYS = {"APP_NAME", "APP_VERSION"}
    _COLOR_KEYS = {
        "EDITOR_DEFAULT_COLOR", "BORDER_COLOR", "SHADOW_COLOR",
        "BACKDROP_COLOR", "BACKDROP_COLOR2", "PIN_BORDER_COLOR",
    }
    _HOTKEY_KEYS = (
        "CAPTURE_REGION_HOTKEY", "CAPTURE_WINDOW_HOTKEY",
        "CAPTURE_FULLSCREEN_HOTKEY", "CAPTURE_LAST_REGION_HOTKEY",
        "CAPTURE_OCR_HOTKEY", "CAPTURE_FREEHAND_HOTKEY",
        "CAPTURE_SCROLLING_HOTKEY", "CAPTURE_COLOR_PICKER_HOTKEY",
    )
    # Numeric keys are clamped to their Settings-UI ranges on load/import —
    # e.g. a hand-edited CAPTURE_HISTORY_MAX of 0 made the history pruner
    # delete every capture immediately after saving it.
    _NUMERIC_RANGES = {
        "CAPTURE_DELAY_MS": (0, 10000),
        "CAPTURE_TIMER_SECONDS": (1, 30),
        "OUTPUT_JPEG_QUALITY": (1, 100),
        "EDITOR_DEFAULT_LINE_WIDTH": (1, 20),
        "EDITOR_DEFAULT_FONT_SIZE": (6, 72),
        "EDITOR_OBFUSCATE_FACTOR": (2, 50),
        "BORDER_WIDTH": (0, 50),
        "SHADOW_RADIUS": (0, 50),
        "SHADOW_OPACITY": (0, 255),
        "ROUNDED_CORNERS_RADIUS": (0, 100),
        "CAPTURE_HISTORY_MAX": (5, 500),
        "PIN_OPACITY": (10, 100),
    }

    def __init__(self):
        self._config_dir = self._get_config_dir()
        self._config_file = os.path.join(self._config_dir, "swiftshot.json")
        # Give the instance its own copies of mutable class defaults so
        # in-place mutation never pollutes the class-level values (which
        # reset_to_defaults() reads back).
        self.EDITOR_RECENT_COLORS = list(Config.EDITOR_RECENT_COLORS)
        self.AFTER_CAPTURE_ACTIONS = list(Config.AFTER_CAPTURE_ACTIONS)
        # Keys written by a newer build that this build doesn't know — kept
        # verbatim so saving here doesn't erase the user's newer settings on a
        # downgrade/upgrade round-trip.
        self._unknown_keys = {}
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
        return [k for k in dir(self) if k.isupper() and not k.startswith('_')
                and k not in self._IDENTITY_KEYS]

    def _apply_value(self, key, value):
        """Apply a persisted/imported value only if it matches the type of
        the default -- malformed files must not corrupt runtime settings."""
        if key in self._IDENTITY_KEYS:
            return
        default = getattr(Config, key, None)
        if isinstance(default, bool):
            if not isinstance(value, bool):
                return
        elif isinstance(default, int):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return
            value = int(value)
        elif isinstance(default, str):
            if not isinstance(value, str):
                return
        elif isinstance(default, list):
            if not isinstance(value, list):
                return
            value = list(value)
        setattr(self, key, value)

    def _normalize_enums(self):
        if self.OUTPUT_FILE_FORMAT not in OUTPUT_FILE_FORMAT_CHOICES:
            self.OUTPUT_FILE_FORMAT = Config.OUTPUT_FILE_FORMAT
        if self.THEME not in ("dark", "light"):
            self.THEME = Config.THEME
        if self.BEAUTIFY_PRESET not in BEAUTIFICATION_PRESETS:
            self.BEAUTIFY_PRESET = Config.BEAUTIFY_PRESET
        if self.EDITOR_OBFUSCATE_MODE not in ("pixelate", "blur"):
            self.EDITOR_OBFUSCATE_MODE = Config.EDITOR_OBFUSCATE_MODE
        if self.BACKDROP_TYPE not in ("solid", "gradient"):
            self.BACKDROP_TYPE = Config.BACKDROP_TYPE
        if self.BACKDROP_FRAME not in BACKDROP_FRAME_CHOICES:
            self.BACKDROP_FRAME = Config.BACKDROP_FRAME
        for key, (lo, hi) in self._NUMERIC_RANGES.items():
            val = getattr(self, key, None)
            if isinstance(val, int) and not isinstance(val, bool):
                setattr(self, key, min(max(val, lo), hi))
        for key in self._COLOR_KEYS:
            value = getattr(self, key, "")
            if not isinstance(value, str) or not _HEX_COLOR_RE.fullmatch(value):
                setattr(self, key, getattr(Config, key))
        recent_colors = []
        for value in self.EDITOR_RECENT_COLORS:
            if (isinstance(value, str) and _HEX_COLOR_RE.fullmatch(value)
                    and value.lower() not in recent_colors):
                recent_colors.append(value.lower())
        self.EDITOR_RECENT_COLORS = recent_colors[:12]
        self.OUTPUT_FILENAME_PATTERN = self.OUTPUT_FILENAME_PATTERN[
            :MAX_FILENAME_PATTERN_LENGTH]
        self._normalize_hotkeys()

    def _normalize_hotkeys(self):
        """Reject malformed/imported shortcuts and resolve physical collisions."""
        try:
            from hotkeys import HotkeyManager
            parser = HotkeyManager()
        except Exception:
            return

        seen = set()
        for key in self._HOTKEY_KEYS:
            combo = getattr(self, key)
            if not combo:
                continue
            binding = parser._parse_combo(combo)
            if binding[1] is None:
                combo = getattr(Config, key)
                binding = parser._parse_combo(combo) if combo else (0, None)
            if binding[1] is None or binding in seen:
                combo = ""
            elif combo:
                seen.add(binding)
            setattr(self, key, combo)

    def _load(self):
        if not os.path.exists(self._config_file):
            return
        try:
            data = _read_json_object(self._config_file)
            for key, value in data.items():
                if not key.isupper() or key in self._IDENTITY_KEYS:
                    continue
                if hasattr(self, key):
                    self._apply_value(key, value)
                else:
                    self._unknown_keys[key] = value   # newer-build key
            if "AFTER_CAPTURE_ACTIONS" not in data:
                self.AFTER_CAPTURE_ACTIONS = [self.AFTER_CAPTURE_ACTION]
            self._normalize_after_capture_actions()
            self._normalize_enums()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            backup = self._config_file + ".corrupt"
            try:
                shutil.copy2(self._config_file, backup)
                saved = f"Backup saved to {backup}"
            except Exception as be:
                saved = f"Backup copy also failed ({be})"
            self._log_warning(
                f"Config file is corrupt ({e}); using defaults. {saved}")
        except Exception as e:
            self._log_warning(f"Could not load config: {e}")

    def save(self):
        data = dict(self._unknown_keys)   # preserve newer-build keys first
        data.update({k: getattr(self, k) for k in self._get_saveable_keys()})
        try:
            _atomic_write_json(self._config_file, data)
            return True
        except Exception as e:
            self._log_warning(f"Could not save config: {e}")
            return False

    @staticmethod
    def _log_warning(message):
        try:
            from logger import log
            log.warning(message)
        except Exception:
            pass

    def reset_to_defaults(self):
        """Reset all settings to class-level defaults (preserves state keys)."""
        snapshot = {
            key: (list(getattr(self, key))
                  if isinstance(getattr(self, key), list)
                  else getattr(self, key))
            for key in self._get_saveable_keys()
        }
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
        if self.save():
            return True
        for key, value in snapshot.items():
            setattr(self, key, value)
        return False

    def export_settings(self, filepath):
        """Export user settings to a JSON file (excludes internal state)."""
        data = {}
        for key in self._get_saveable_keys():
            if key not in self._STATE_KEYS:
                data[key] = getattr(self, key)
        try:
            _atomic_write_json(filepath, data)
            return True
        except Exception as e:
            self._log_warning(f"Settings export failed: {e}")
            return False

    def import_settings(self, filepath):
        """Import settings from a JSON file."""
        snapshot = {
            key: (list(getattr(self, key))
                  if isinstance(getattr(self, key), list)
                  else getattr(self, key))
            for key in self._get_saveable_keys()
        }
        try:
            data = _read_json_object(filepath)
            for key, value in data.items():
                if hasattr(self, key) and key.isupper() and key not in self._STATE_KEYS:
                    self._apply_value(key, value)
            if "AFTER_CAPTURE_ACTIONS" not in data:
                self.AFTER_CAPTURE_ACTIONS = [self.AFTER_CAPTURE_ACTION]
            self._normalize_after_capture_actions()
            self._normalize_enums()
            if not self.save():
                raise OSError("could not persist imported settings")
            return True
        except Exception as e:
            for key, value in snapshot.items():
                setattr(self, key, value)
            self._log_warning(f"Settings import failed: {e}")
            return False

    def add_recent_color(self, hex_color):
        """Track recently used colors (max 12, most recent first)."""
        if not isinstance(hex_color, str) or not _HEX_COLOR_RE.fullmatch(hex_color):
            return False
        hex_color = hex_color.lower()
        if hex_color in self.EDITOR_RECENT_COLORS:
            self.EDITOR_RECENT_COLORS.remove(hex_color)
        self.EDITOR_RECENT_COLORS.insert(0, hex_color)
        if len(self.EDITOR_RECENT_COLORS) > 12:
            self.EDITOR_RECENT_COLORS = self.EDITOR_RECENT_COLORS[:12]
        return True

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
                # 0x0010 = CSIDL_DESKTOPDIRECTORY (the on-disk Desktop folder).
                # 0x0000 = CSIDL_DESKTOP is the virtual namespace root and can
                # resolve to an empty/namespace path.
                ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
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
        name = name[:MAX_FILENAME_STEM_LENGTH].rstrip(" ._")
        name = name or "SwiftShot"
        if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
            name = f"_{name}"
        return name

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
