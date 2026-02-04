#!/usr/bin/env python3
"""
SwiftShot - A debloated, no-nonsense screenshot tool
Inspired by Greenshot, built without any 3rd-party integrations or plugin bloat.

Core Features:
  - Region, Window, Fullscreen capture
  - Built-in image editor (crop, annotate, shapes, blur, highlight)
  - Save to file, copy to clipboard, print
  - System tray with hotkey support
  - Dark theme throughout

Author: SwiftShot Project
License: GPL-3.0 (same as Greenshot)
"""

import sys
import os

# Ensure high-DPI awareness on Windows
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

def check_dependencies():
    """Auto-install missing dependencies."""
    required = ['PyQt5', 'Pillow']
    missing = []
    for pkg in required:
        try:
            __import__(pkg if pkg != 'Pillow' else 'PIL')
        except ImportError:
            missing.append(pkg)
    
    if missing:
        import subprocess
        print(f"Installing missing dependencies: {', '.join(missing)}")
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install',
            '--break-system-packages', *missing
        ])

check_dependencies()

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from app import SwiftShotApp


def main():
    # Enable high-DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("SwiftShot")
    app.setApplicationVersion("1.0.0")
    
    # Apply dark theme
    from theme import apply_dark_theme
    apply_dark_theme(app)
    
    swiftshot = SwiftShotApp(app)
    swiftshot.start()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
