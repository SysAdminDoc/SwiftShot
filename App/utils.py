"""
SwiftShot Shared Utilities
Common helpers used across multiple modules.
"""

import sys
import math
import os
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
    """Save a QPixmap with SwiftShot output-format semantics."""
    fmt = file_format.lower()
    if fmt == "jpg":
        fmt = "jpeg"

    try:
        if fmt == "webp":
            image = qpixmap_to_pil(pixmap)
            image.save(filepath, "WEBP", lossless=True, quality=100, method=6)
            return True

        if fmt == "gif":
            # Qt has no GIF encoder -- route through Pillow.
            from PIL import Image
            image = qpixmap_to_pil(pixmap)
            image = image.convert("RGB").convert("P", palette=Image.ADAPTIVE)
            image.save(filepath, "GIF")
            return True

        qt_format = "JPEG" if fmt == "jpeg" else fmt.upper()
        quality = int(jpeg_quality) if qt_format == "JPEG" else -1
        return pixmap.save(filepath, qt_format, quality)
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
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            # Determine the command to run
            if getattr(sys, 'frozen', False):
                cmd = f'"{sys.executable}"'
            else:
                cmd = f'"{sys.executable}" "{__file__}"'
                # Try to find main.py relative to this file
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
