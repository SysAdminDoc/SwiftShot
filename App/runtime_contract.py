"""SwiftShot's supported interpreter and DPI initialization contract."""

import ctypes
import sys


REQUIRED_PYTHON = (3, 12)


def python_version_error(version_info=None):
    """Return one actionable error for an unsupported interpreter, else None."""
    version = sys.version_info if version_info is None else version_info
    if tuple(version[:2]) == REQUIRED_PYTHON:
        return None
    found = ".".join(str(part) for part in tuple(version[:3]))
    return (
        "SwiftShot requires Python 3.12.x; found Python "
        f"{found}. Install Python 3.12, then run: py -3.12 App\\main.py"
    )


def require_supported_python(version_info=None, stream=None):
    """Return true on Python 3.12; otherwise print exactly one error line."""
    message = python_version_error(version_info)
    if message is None:
        return True
    print(message, file=stream or sys.stderr)
    return False


def _set_windows_dpi_awareness():
    """Use physical pixels throughout capture math on supported Windows."""
    if sys.platform != "win32":
        return
    try:
        try:
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1703+)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Windows 8.1+
            except (AttributeError, OSError):
                ctypes.windll.user32.SetProcessDPIAware()       # Windows Vista+
    except (AttributeError, OSError):
        # DPI setup is best-effort: startup must still reach the logger/UI.
        return


def configure_dpi_policy():
    """Apply the one DPI policy before any SwiftShot QApplication is created.

    Per-monitor-v2 awareness keeps Qt widget coordinates in physical pixels;
    Qt's own logical-coordinate scaling is disabled to prevent mixed-space
    capture rectangles. High-resolution pixmaps remain enabled for UI assets.
    """
    _set_windows_dpi_awareness()
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    try:
        QApplication.setAttribute(Qt.AA_DisableHighDpiScaling, True)
    except AttributeError:
        pass
    try:
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass
