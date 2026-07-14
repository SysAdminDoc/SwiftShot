"""
SwiftShot Shared Utilities
Common helpers used across multiple modules.
"""

import sys
import math
import os
import tempfile
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QRect, QPoint

from logger import log


WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011


def exclude_window_from_capture(widget, user32=None):
    """Exclude a transient SwiftShot window from Windows screen capture.

    Windows 10 version 2004+ supports ``WDA_EXCLUDEFROMCAPTURE``. Older
    supported Windows builds reject that flag, so retry with ``WDA_MONITOR``;
    it blanks the window in captures instead of omitting it. Returning the
    applied affinity makes the fallback observable in tests and diagnostics.

    Callers opt in explicitly. In particular, pinned reference windows do not
    call this helper and therefore remain capturable by design.
    """
    if sys.platform != "win32":
        return WDA_NONE
    try:
        if user32 is None:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            user32.SetWindowDisplayAffinity.argtypes = [
                wintypes.HWND, wintypes.DWORD
            ]
            user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        hwnd = int(widget.winId())
        if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
            return WDA_EXCLUDEFROMCAPTURE
        if user32.SetWindowDisplayAffinity(hwnd, WDA_MONITOR):
            return WDA_MONITOR
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return WDA_NONE


def atomic_replace(path, writer, verifier=None):
    """Write and verify a sibling temporary file before replacing ``path``.

    ``writer`` receives the temporary path and must close everything it opens.
    Keeping the temporary file beside the destination makes ``os.replace`` an
    atomic same-filesystem operation. The old destination is left untouched if
    writing, flushing, verification, or replacement fails.
    """
    target = os.path.abspath(os.fspath(path))
    directory = os.path.dirname(target) or os.curdir
    basename = os.path.basename(target) or "swiftshot"
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{basename}.", suffix=".tmp", dir=directory
    )
    os.close(fd)
    try:
        writer(temp_path)
        # The writer has closed its handle; force buffered data to the storage
        # layer before validating and publishing the file.
        with open(temp_path, "rb+") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        if verifier is not None:
            verifier(temp_path)
        os.replace(temp_path, target)
        return target
    except Exception:
        try:
            os.remove(temp_path)
        except FileNotFoundError:
            pass
        except OSError as cleanup_error:
            log.warning(f"Could not remove failed atomic-write temp {temp_path}: "
                        f"{cleanup_error}")
        raise


def atomic_write_bytes(path, data, verifier=None):
    """Atomically publish a byte payload, optionally validating the temp file."""
    def _write(temp_path):
        with open(temp_path, "wb") as handle:
            handle.write(data)

    return atomic_replace(path, _write, verifier)


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
    img = pixmap.toImage()
    if 0 <= x < img.width() and 0 <= y < img.height():
        c = img.pixelColor(x, y)
        return (c.red(), c.green(), c.blue())
    return (0, 0, 0)


def qpixmap_to_pil(pixmap):
    """Convert a QPixmap to a Pillow RGBA image."""
    from PIL import Image
    from PyQt5.QtGui import QImage

    qimg = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    width, height = qimg.width(), qimg.height()
    ptr = qimg.bits()
    ptr.setsize(height * qimg.bytesPerLine())
    return Image.frombuffer(
        "RGBA",
        (width, height),
        bytes(ptr),
        "raw",
        "RGBA",
        qimg.bytesPerLine(),
        1,
    ).copy()


def pil_to_qpixmap(pil_image):
    """Convert a Pillow image to a QPixmap."""
    from PyQt5.QtGui import QImage, QPixmap

    image = pil_image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimage = QImage(
        data, image.width, image.height, 4 * image.width, QImage.Format_RGBA8888
    )
    return QPixmap.fromImage(qimage.copy())


def apply_beautification_preset(pixmap, preset_name):
    """Apply a one-click beautification preset to a QPixmap."""
    from PIL import Image, ImageColor, ImageDraw, ImageFilter
    from config import BEAUTIFICATION_PRESETS

    preset = BEAUTIFICATION_PRESETS.get(preset_name) or BEAUTIFICATION_PRESETS["none"]
    if preset_name == "none" or preset["padding"] <= 0:
        return pixmap

    image = qpixmap_to_pil(pixmap)
    width, height = image.size
    padding = int(preset["padding"])
    corner_radius = int(preset["corner_radius"])
    shadow_radius = int(preset["shadow_radius"])
    offset_x, offset_y = preset["shadow_offset"]
    shadow_opacity = int(preset["shadow_opacity"])

    mask = Image.new("L", image.size, 255)
    if corner_radius > 0:
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle(
            (0, 0, width - 1, height - 1),
            radius=corner_radius,
            fill=255,
        )
        rounded = Image.new("RGBA", image.size, (0, 0, 0, 0))
        rounded.paste(image, (0, 0), mask)
        image = rounded

    extra = shadow_radius * 2
    canvas_width = width + padding * 2 + extra
    canvas_height = height + padding * 2 + extra + max(0, offset_y)
    background = preset["background"] or "#ffffff"
    canvas = Image.new(
        "RGBA",
        (canvas_width, canvas_height),
        ImageColor.getrgb(background) + (255,),
    )

    x = padding + shadow_radius
    y = padding + shadow_radius
    if shadow_radius > 0 and shadow_opacity > 0:
        shadow_alpha = Image.new("L", image.size, 0)
        shadow_alpha.paste(mask, (0, 0))
        shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(shadow_radius))
        shadow = Image.new("RGBA", image.size, (0, 0, 0, shadow_opacity))
        shadow.putalpha(shadow_alpha)
        canvas.alpha_composite(shadow, (x + int(offset_x), y + int(offset_y)))

    canvas.alpha_composite(image, (x, y))
    return pil_to_qpixmap(canvas)


def apply_frame(pixmap):
    """Apply the configured post-capture frame — rounded corners, border,
    and/or drop shadow — from Settings > Frame. No-op unless at least one is
    enabled, so it is safe to call unconditionally in the capture funnel."""
    from PIL import Image, ImageColor, ImageDraw, ImageFilter
    import config as _cfg
    cfg = _cfg.config if hasattr(_cfg, "config") else _cfg

    rounded = getattr(cfg, "ROUNDED_CORNERS_ENABLED", False)
    border = getattr(cfg, "BORDER_ENABLED", False)
    shadow = getattr(cfg, "SHADOW_ENABLED", False)
    if not (rounded or border or shadow):
        return pixmap

    image = qpixmap_to_pil(pixmap)
    width, height = image.size
    radius = int(getattr(cfg, "ROUNDED_CORNERS_RADIUS", 12)) if rounded else 0

    if radius > 0:
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, width - 1, height - 1), radius=radius, fill=255)
        clipped = Image.new("RGBA", image.size, (0, 0, 0, 0))
        clipped.paste(image, (0, 0), mask)
        image = clipped
    else:
        mask = Image.new("L", image.size, 255)

    if border:
        bw = max(1, int(getattr(cfg, "BORDER_WIDTH", 3)))
        bcol = ImageColor.getrgb(getattr(cfg, "BORDER_COLOR", "#45475a")) + (255,)
        draw = ImageDraw.Draw(image)
        box = (0, 0, width - 1, height - 1)  # stroke grows inward from the edge
        if radius > 0:
            draw.rounded_rectangle(box, radius=radius, outline=bcol, width=bw)
        else:
            draw.rectangle(box, outline=bcol, width=bw)

    if shadow:
        sr = max(1, int(getattr(cfg, "SHADOW_RADIUS", 15)))
        sop = int(getattr(cfg, "SHADOW_OPACITY", 80))
        scol = ImageColor.getrgb(getattr(cfg, "SHADOW_COLOR", "#000000"))
        pad = sr * 2 + 4
        canvas = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
        shadow_alpha = mask.filter(ImageFilter.GaussianBlur(sr)).point(
            lambda v: int(v * sop / 255))
        sh = Image.new("RGBA", image.size, scol + (0,))
        sh.putalpha(shadow_alpha)
        canvas.alpha_composite(sh, (pad, pad + sr // 2))
        canvas.alpha_composite(image, (pad, pad))
        image = canvas

    return pil_to_qpixmap(image)


def _window_frame(img, style):
    """Wrap `img` in a titlebar/chrome so a capture looks like a real window.
    style: 'macos' (rounded, traffic-light dots) or 'windows' (min/max/close).
    Returns a new RGBA image; the whole result is rounded for macOS."""
    from PIL import Image, ImageDraw
    w, h = img.size
    bar_h = 30 if style == "macos" else 34
    radius = 12 if style == "macos" else 0
    fw, fh = w, h + bar_h

    frame = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    draw.rectangle((0, 0, fw, bar_h), fill=(52, 54, 70, 255))     # titlebar
    frame.alpha_composite(img, (0, bar_h))
    draw = ImageDraw.Draw(frame)                                   # re-draw over

    cy = bar_h // 2
    if style == "macos":
        for i, col in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
            cx = 16 + i * 20
            draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=col + (255,))
    else:  # windows-style controls on the right
        pen = (205, 208, 220, 255)
        gx = fw - 20
        draw.line((gx - 5, cy - 5, gx + 5, cy + 5), fill=(232, 90, 90, 255), width=2)
        draw.line((gx - 5, cy + 5, gx + 5, cy - 5), fill=(232, 90, 90, 255), width=2)
        gx -= 34
        draw.rectangle((gx - 5, cy - 5, gx + 5, cy + 5), outline=pen, width=2)
        gx -= 34
        draw.line((gx - 5, cy + 5, gx + 5, cy + 5), fill=pen, width=2)

    if radius > 0:
        mask = Image.new("L", (fw, fh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, fw - 1, fh - 1), radius, fill=255)
        rounded = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
        rounded.paste(frame, (0, 0), mask)
        frame = rounded
    return frame


def apply_backdrop(pixmap):
    """Place the (already framed) capture on a padded solid or gradient
    backdrop. No-op unless BACKDROP_ENABLED. Runs after apply_frame so a
    rounded/shadowed screenshot sits on the coloured padding. An optional
    window/browser chrome (BACKDROP_FRAME) wraps the capture with a soft
    drop shadow so it reads as a floating window."""
    from PIL import Image, ImageColor, ImageFilter
    import config as _cfg
    import numpy as np
    cfg = _cfg.config if hasattr(_cfg, "config") else _cfg

    if not getattr(cfg, "BACKDROP_ENABLED", False):
        return pixmap

    # Match the settings/config contract defensively. A poisoned runtime value
    # must not turn one capture into an unbounded Pillow/NumPy allocation.
    pad = max(0, min(400, int(getattr(cfg, "BACKDROP_PADDING", 48))))
    img = qpixmap_to_pil(pixmap)
    frame_style = getattr(cfg, "BACKDROP_FRAME", "none")
    if frame_style in ("macos", "windows"):
        img = _window_frame(img, frame_style)
    w, h = img.size
    cw, ch = w + pad * 2, h + pad * 2
    c1 = ImageColor.getrgb(getattr(cfg, "BACKDROP_COLOR", "#1e1e2e"))

    if getattr(cfg, "BACKDROP_TYPE", "solid") == "gradient":
        c2 = ImageColor.getrgb(getattr(cfg, "BACKDROP_COLOR2", "#45475a"))
        t = np.linspace(0.0, 1.0, ch).reshape(ch, 1, 1)
        row = (np.array(c1).reshape(1, 1, 3) * (1 - t)
               + np.array(c2).reshape(1, 1, 3) * t)
        arr = np.repeat(row, cw, axis=1).astype(np.uint8)
        alpha = np.full((ch, cw, 1), 255, dtype=np.uint8)
        canvas = Image.fromarray(np.concatenate([arr, alpha], axis=2), "RGBA")
    else:
        canvas = Image.new("RGBA", (cw, ch), c1 + (255,))

    # Soft drop shadow under a framed window so it floats off the backdrop.
    if frame_style in ("macos", "windows") and pad > 0:
        shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        silhouette = Image.new("RGBA", img.size, (0, 0, 0, 0))
        silhouette.putalpha(img.split()[3].point(lambda a: int(a * 0.45)))
        shadow.alpha_composite(silhouette, (pad, pad + 12))
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))

    canvas.alpha_composite(img, (pad, pad))
    return pil_to_qpixmap(canvas)


def apply_freehand_mask(pixmap, points, bounding_rect):
    """Mask a cropped pixmap to a freehand polygon (transparent outside).

    points are in the same coordinate space as bounding_rect (the overlay),
    pixmap is the crop of bounding_rect.
    """
    from PyQt5.QtGui import QPainter, QPainterPath, QPolygonF, QPixmap
    from PyQt5.QtCore import QPointF, Qt

    if len(points) < 3:
        return pixmap
    result = QPixmap(pixmap.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    polygon = QPolygonF([
        QPointF(p.x() - bounding_rect.x(), p.y() - bounding_rect.y())
        for p in points
    ])
    path = QPainterPath()
    path.addPolygon(polygon)
    path.closeSubpath()
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()
    return result


def save_pixmap(pixmap, filepath, file_format, jpeg_quality=90):
    """Atomically save a verified QPixmap with SwiftShot format semantics."""
    fmt = file_format.lower()
    if fmt == "jpg":
        fmt = "jpeg"

    try:
        expected_format = "JPEG" if fmt == "jpeg" else fmt.upper()

        def _write(temp_path):
            if fmt == "webp":
                image = qpixmap_to_pil(pixmap)
                image.save(
                    temp_path, "WEBP", lossless=True, quality=100, method=6)
                return
            if fmt == "gif":
                # Qt has no GIF encoder -- route through Pillow.
                from PIL import Image
                image = qpixmap_to_pil(pixmap)
                image = image.convert("RGB").convert(
                    "P", palette=Image.ADAPTIVE)
                image.save(temp_path, "GIF")
                return
            if fmt == "avif":
                # Qt has no AVIF encoder -- route through Pillow/libavif.
                image = qpixmap_to_pil(pixmap)
                image.save(temp_path, "AVIF", quality=90)
                return

            quality = int(jpeg_quality) if expected_format == "JPEG" else -1
            if not pixmap.save(temp_path, expected_format, quality):
                raise OSError(f"Qt could not encode {expected_format}")

        def _verify(temp_path):
            from safe_io import load_image
            load_image(temp_path, allowed_formats={expected_format})

        atomic_replace(filepath, _write, _verify)
        return True
    except Exception as e:
        log.error(f"save_pixmap failed for {filepath} ({fmt}): {e}")
        return False


def color_to_hex(r, g, b):
    """Convert RGB tuple to hex string."""
    return f"#{r:02X}{g:02X}{b:02X}"


def get_foreground_window_metadata():
    """Return best-effort foreground app and title metadata for filenames."""
    metadata = {"app_name": "", "window_title": ""}
    if sys.platform != 'win32':
        return metadata

    try:
        import ctypes
        import ctypes.wintypes

        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = ctypes.wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [ctypes.wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [
            ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return metadata

        title_len = user32.GetWindowTextLengthW(hwnd)
        if title_len:
            title_buf = ctypes.create_unicode_buffer(title_len + 1)
            user32.GetWindowTextW(hwnd, title_buf, title_len + 1)
            metadata["window_title"] = title_buf.value

        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return metadata

        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [
            ctypes.wintypes.DWORD, ctypes.wintypes.BOOL,
            ctypes.wintypes.DWORD]
        kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
            ctypes.wintypes.LPWSTR, ctypes.POINTER(ctypes.wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = ctypes.wintypes.BOOL
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        process = kernel32.OpenProcess(0x1000, False, pid.value)
        if not process:
            return metadata

        try:
            size = ctypes.wintypes.DWORD(32768)
            path_buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(
                process, 0, path_buf, ctypes.byref(size)
            ):
                app = os.path.splitext(os.path.basename(path_buf.value))[0]
                metadata["app_name"] = app
        finally:
            kernel32.CloseHandle(process)
    except Exception:
        pass

    return metadata


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
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0,
                winreg.KEY_SET_VALUE) as key:
            if enable:
                # Determine the command to run
                if getattr(sys, 'frozen', False):
                    cmd = f'"{sys.executable}"'
                else:
                    cmd = f'"{sys.executable}" "{__file__}"'
                    # Try to find main.py relative to this file
                    main_py = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), 'main.py')
                    if os.path.exists(main_py):
                        cmd = f'"{sys.executable}" "{main_py}"'
                winreg.SetValueEx(key, "SwiftShot", 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, "SwiftShot")
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False
