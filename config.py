"""
SwiftShot Configuration Manager
Handles all settings persistence via INI file (like Greenshot).
"""

import os
import json
from pathlib import Path


class Config:
    """Application configuration with sensible defaults."""
    
    # Default config location
    APP_NAME = "SwiftShot"
    
    # --- Capture Settings ---
    CAPTURE_MOUSE_POINTER = False
    CAPTURE_DELAY_MS = 0
    CAPTURE_REGION_HOTKEY = "Print"           # PrintScreen
    CAPTURE_WINDOW_HOTKEY = "Alt+Print"       # Alt+PrintScreen
    CAPTURE_FULLSCREEN_HOTKEY = "Ctrl+Print"  # Ctrl+PrintScreen
    CAPTURE_LAST_REGION_HOTKEY = "Shift+Print"
    
    # --- Output Settings ---
    OUTPUT_FILE_FORMAT = "png"  # png, jpg, bmp, gif, tiff
    OUTPUT_JPEG_QUALITY = 90
    OUTPUT_FILE_PATH = ""  # Empty = Desktop
    OUTPUT_FILENAME_PATTERN = "SwiftShot_{YYYY}-{MM}-{DD}_{hh}-{mm}-{ss}"
    OUTPUT_FILE_INCREMENT = True
    
    # --- After Capture ---
    # What to do after capture: "editor", "save", "clipboard", "ask"
    AFTER_CAPTURE_ACTION = "editor"
    COPY_PATH_TO_CLIPBOARD = False
    PLAY_CAMERA_SOUND = True
    
    # --- Editor Settings ---
    EDITOR_MATCH_CAPTURE_SIZE = True
    EDITOR_DEFAULT_COLOR = "#f38ba8"       # Red for annotations
    EDITOR_DEFAULT_LINE_WIDTH = 2
    EDITOR_DEFAULT_FONT_SIZE = 14
    EDITOR_DEFAULT_FONT_FAMILY = "Segoe UI"
    EDITOR_HIGHLIGHT_COLOR = "#f9e2af"     # Yellow for highlight
    EDITOR_OBFUSCATE_FACTOR = 12           # Pixelation block size
    EDITOR_OBFUSCATE_MODE = "pixelate"     # "pixelate" or "blur"
    EDITOR_SHOW_MAGNIFIER = True
    EDITOR_REUSE_EDITOR = False
    
    # --- General ---
    LAUNCH_AT_STARTUP = False
    MINIMIZE_TO_TRAY = True
    CHECK_FOR_UPDATES = False  # No update checks - debloated!
    LANGUAGE = "en-US"
    
    # --- Last used values (persisted state) ---
    LAST_SAVE_DIR = ""
    LAST_REGION = ""  # "x,y,w,h" for last region capture
    WINDOW_GEOMETRY = ""
    
    def __init__(self):
        self._config_dir = self._get_config_dir()
        self._config_file = os.path.join(self._config_dir, "swiftshot.json")
        self._load()
    
    def _get_config_dir(self):
        """Get configuration directory (cross-platform)."""
        if os.name == 'nt':
            base = os.environ.get('APPDATA', os.path.expanduser('~'))
        else:
            base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        config_dir = os.path.join(base, self.APP_NAME)
        os.makedirs(config_dir, exist_ok=True)
        return config_dir
    
    def _load(self):
        """Load configuration from JSON file."""
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, 'r') as f:
                    data = json.load(f)
                for key, value in data.items():
                    if hasattr(self, key) and key.isupper():
                        setattr(self, key, value)
            except Exception as e:
                print(f"Warning: Could not load config: {e}")
    
    def save(self):
        """Save configuration to JSON file."""
        data = {}
        for key in dir(self):
            if key.isupper() and not key.startswith('_'):
                data[key] = getattr(self, key)
        try:
            with open(self._config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save config: {e}")
    
    def get_output_directory(self):
        """Get the output directory, defaulting to Desktop."""
        if self.OUTPUT_FILE_PATH and os.path.isdir(self.OUTPUT_FILE_PATH):
            return self.OUTPUT_FILE_PATH
        # Default to Desktop
        if os.name == 'nt':
            import ctypes.wintypes
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x0000, None, 0, buf)  # CSIDL_DESKTOP
            desktop = buf.value
            if os.path.isdir(desktop):
                return desktop
        return os.path.expanduser("~/Desktop")
    
    def get_filename(self):
        """Generate a filename from the pattern."""
        from datetime import datetime
        now = datetime.now()
        name = self.OUTPUT_FILENAME_PATTERN
        name = name.replace("{YYYY}", now.strftime("%Y"))
        name = name.replace("{MM}", now.strftime("%m"))
        name = name.replace("{DD}", now.strftime("%d"))
        name = name.replace("{hh}", now.strftime("%H"))
        name = name.replace("{mm}", now.strftime("%M"))
        name = name.replace("{ss}", now.strftime("%S"))
        
        ext = self.OUTPUT_FILE_FORMAT.lower()
        full_path = os.path.join(self.get_output_directory(), f"{name}.{ext}")
        
        # Auto-increment if file exists
        if self.OUTPUT_FILE_INCREMENT and os.path.exists(full_path):
            counter = 1
            while os.path.exists(full_path):
                full_path = os.path.join(
                    self.get_output_directory(),
                    f"{name}_{counter}.{ext}"
                )
                counter += 1
        
        return full_path


# Global config instance
config = Config()
