"""
SwiftShot Shared Utilities
Common helpers used across multiple modules.
"""

import sys
import math
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QRect, QPoint

from logger import log


def virtual_geometry():
    """Get the virtual desktop geometry spanning all monitors.
    Canonical implementation -- import this everywhere instead of duplicating.
    """
    screens = QApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    rect = screens[0].geometry()
    for screen in screens[1:]:
        rect = rect.united(screen.geometry())
    return rect


def clamp(value, lo, hi):
    """Clamp a value between lo and hi."""
    return max(lo, min(hi, value))


def distance(p1: QPoint, p2: QPoint) -> float:
    """Euclidean distance between two QPoints."""
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    return math.sqrt(dx * dx + dy * dy)


def pixel_color_at(pixmap, x, y):
    """Get the color of a pixel in a QPixmap. Returns (r, g, b) tuple."""
    from PyQt5.QtGui import QImage
    img = pixmap.toImage()
    if 0 <= x < img.width() and 0 <= y < img.height():
        c = img.pixelColor(x, y)
        return (c.red(), c.green(), c.blue())
    return (0, 0, 0)


def color_to_hex(r, g, b):
    """Convert RGB tuple to hex string."""
    return f"#{r:02X}{g:02X}{b:02X}"


def play_camera_sound():
    """Play a camera shutter sound using Windows APIs."""
    if sys.platform != 'win32':
        return
    try:
        import winsound
        # Use the system asterisk sound as a lightweight capture feedback
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


def set_startup_registry(enable=True):
    """Add/remove SwiftShot from Windows startup registry."""
    if sys.platform != 'win32':
        return False
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            # Determine the command to run
            if getattr(sys, 'frozen', False):
                cmd = f'"{sys.executable}"'
            else:
                cmd = f'"{sys.executable}" "{__file__}"'
                # Try to find main.py relative to this file
                import os
                main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')
                if os.path.exists(main_py):
                    cmd = f'"{sys.executable}" "{main_py}"'
            winreg.SetValueEx(key, "SwiftShot", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "SwiftShot")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
