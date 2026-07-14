"""
SwiftShot Capture Module
Handles all screenshot capture operations: fullscreen, window, region.
Uses native Windows APIs where available, falls back to Qt for cross-platform.
Includes mouse pointer overlay and camera sound support.
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QImage, QPainter, QCursor
from PyQt5.QtCore import QPoint, QRect, Qt

from utils import virtual_geometry
from config import config
from logger import log
from safe_io import MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS


# Win32 BITMAPINFOHEADER
if sys.platform == 'win32':
    import ctypes

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32),
            ('biWidth', ctypes.c_int32),
            ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16),
            ('biBitCount', ctypes.c_uint16),
            ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32),
            ('biXPelsPerMeter', ctypes.c_int32),
            ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32),
            ('biClrImportant', ctypes.c_uint32),
        ]


class CaptureManager:
    """Static methods for capturing screenshots."""

    @staticmethod
    def capture_fullscreen():
        """Capture the entire virtual desktop (all monitors)."""
        pixmap = None
        try:
            if sys.platform == 'win32':
                pixmap = CaptureManager._capture_fullscreen_win32()
        except Exception as e:
            log.warning(f"Win32 fullscreen capture failed, falling back to Qt: {e}")

        if pixmap is None:
            pixmap = CaptureManager.capture_rect(virtual_geometry())

        if pixmap and config.CAPTURE_MOUSE_POINTER:
            pixmap = CaptureManager._draw_cursor(pixmap)

        # Camera sound is played by the app when a capture completes,
        # not here: this method also grabs overlay backdrops.
        return pixmap

    @staticmethod
    def capture_rect(rect):
        """Capture a global desktop rectangle through each intersecting screen.

        ``QScreen.grabWindow`` coordinates are local to that QScreen on mixed
        DPI desktops. Routing global coordinates through the primary screen
        returns the wrong pixels for secondary monitors, so composite the
        visible intersections from their owning screens instead.
        """
        if rect is None:
            return None
        target = QRect(rect).intersected(virtual_geometry())
        if target.width() < 1 or target.height() < 1:
            return None
        if (target.width() > MAX_IMAGE_DIMENSION
                or target.height() > MAX_IMAGE_DIMENSION
                or target.width() * target.height() > MAX_IMAGE_PIXELS):
            log.warning(
                "Capture rectangle exceeds safe image limits: %dx%d",
                target.width(), target.height(),
            )
            return None

        result = QPixmap(target.size())
        if result.isNull():
            return None
        result.fill(Qt.black)
        painter = QPainter(result)
        drew_pixels = False
        try:
            for screen in QApplication.screens():
                screen_rect = screen.geometry()
                overlap = target.intersected(screen_rect)
                if overlap.width() < 1 or overlap.height() < 1:
                    continue
                local_x = overlap.x() - screen_rect.x()
                local_y = overlap.y() - screen_rect.y()
                screen_pixmap = screen.grabWindow(
                    0, local_x, local_y, overlap.width(), overlap.height())
                if screen_pixmap.isNull():
                    continue
                # A high-DPI QScreen can return more device pixels than the
                # requested logical size. Draw the complete grab into the
                # logical destination instead of cropping its top-left corner.
                destination = QRect(
                    overlap.x() - target.x(), overlap.y() - target.y(),
                    overlap.width(), overlap.height(),
                )
                painter.drawPixmap(destination, screen_pixmap,
                                   screen_pixmap.rect())
                drew_pixels = True
        finally:
            painter.end()
        return result if drew_pixels else None

    @staticmethod
    def _draw_cursor(pixmap):
        """Draw the mouse cursor onto the screenshot."""
        if sys.platform != 'win32':
            return pixmap

        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            class CURSORINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.DWORD),
                    ('flags', wintypes.DWORD),
                    ('hCursor', wintypes.HANDLE),
                    ('ptScreenPos', wintypes.POINT),
                ]

            user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
            user32.GetCursorInfo.restype = wintypes.BOOL
            gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
            gdi32.DeleteObject.restype = wintypes.BOOL

            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(CURSORINFO)
            if not user32.GetCursorInfo(ctypes.byref(ci)):
                return pixmap

            CURSOR_SHOWING = 0x00000001
            if not (ci.flags & CURSOR_SHOWING):
                return pixmap

            # Get virtual screen offset
            geo = virtual_geometry()

            # Draw cursor icon onto pixmap
            result = pixmap.copy()
            painter = QPainter(result)
            cursor_x = ci.ptScreenPos.x - geo.x()
            cursor_y = ci.ptScreenPos.y - geo.y()

            # Get cursor hotspot and draw
            class ICONINFO(ctypes.Structure):
                _fields_ = [
                    ('fIcon', wintypes.BOOL),
                    ('xHotspot', wintypes.DWORD),
                    ('yHotspot', wintypes.DWORD),
                    ('hbmMask', wintypes.HBITMAP),
                    ('hbmColor', wintypes.HBITMAP),
                ]

            user32.GetIconInfo.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(ICONINFO)]
            user32.GetIconInfo.restype = wintypes.BOOL

            ii = ICONINFO()
            if user32.GetIconInfo(ci.hCursor, ctypes.byref(ii)):
                cursor_x -= ii.xHotspot
                cursor_y -= ii.yHotspot
                if ii.hbmMask:
                    gdi32.DeleteObject(ii.hbmMask)
                if ii.hbmColor:
                    gdi32.DeleteObject(ii.hbmColor)

            # Render the ACTUAL cursor shape (I-beam / hand / resize / arrow)
            # via DrawIconEx, not the app's QCursor (which is usually null and
            # forced the generic arrow fallback).
            cursor_img = CaptureManager._cursor_to_qimage(ci.hCursor)
            if cursor_img is not None and not cursor_img.isNull():
                painter.drawImage(cursor_x, cursor_y, cursor_img)
            else:
                c_pixmap = QCursor().pixmap()
                if not c_pixmap.isNull():
                    painter.drawPixmap(cursor_x, cursor_y, c_pixmap)
                else:
                    # Last-resort generic arrow
                    from PyQt5.QtGui import QPen, QColor, QPolygon
                    painter.setPen(QPen(QColor("white"), 1))
                    painter.setBrush(QColor("black"))
                    arrow = QPolygon([
                        QPoint(cursor_x, cursor_y),
                        QPoint(cursor_x, cursor_y + 18),
                        QPoint(cursor_x + 5, cursor_y + 14),
                        QPoint(cursor_x + 10, cursor_y + 20),
                        QPoint(cursor_x + 13, cursor_y + 18),
                        QPoint(cursor_x + 8, cursor_y + 12),
                        QPoint(cursor_x + 14, cursor_y + 10),
                    ])
                    painter.drawPolygon(arrow)

            painter.end()
            return result

        except Exception:
            return pixmap

    @staticmethod
    def _cursor_to_qimage(hcursor):
        """Rasterize a Win32 HCURSOR to an ARGB32 QImage via DrawIconEx.

        Draws the cursor over both a black and a white background and
        reconstructs straight alpha from the difference. This renders legacy
        AND/XOR-mask cursors (I-beam, resize) correctly — a single DrawIconEx
        leaves their alpha channel zero, so they'd otherwise vanish.
        Returns None on failure or a fully-transparent result.
        """
        if sys.platform != 'win32' or not hcursor:
            return None
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            user32.GetSystemMetrics.argtypes = [ctypes.c_int]
            user32.GetSystemMetrics.restype = ctypes.c_int
            user32.GetDC.argtypes = [wintypes.HWND]
            user32.GetDC.restype = wintypes.HDC
            user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
            user32.ReleaseDC.restype = ctypes.c_int
            user32.DrawIconEx.argtypes = [
                wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HANDLE,
                ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HANDLE,
                wintypes.UINT,
            ]
            user32.DrawIconEx.restype = wintypes.BOOL
            gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
            gdi32.CreateCompatibleDC.restype = wintypes.HDC
            gdi32.CreateDIBSection.argtypes = [
                wintypes.HDC, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
                ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                wintypes.DWORD,
            ]
            gdi32.CreateDIBSection.restype = wintypes.HBITMAP
            gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
            gdi32.SelectObject.restype = wintypes.HANDLE
            gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
            gdi32.DeleteObject.restype = wintypes.BOOL
            gdi32.DeleteDC.argtypes = [wintypes.HDC]
            gdi32.DeleteDC.restype = wintypes.BOOL
            gdi32.GdiFlush.argtypes = []
            gdi32.GdiFlush.restype = wintypes.BOOL

            cx = user32.GetSystemMetrics(13) or 32   # SM_CXCURSOR
            cy = user32.GetSystemMetrics(14) or 32   # SM_CYCURSOR
            DI_NORMAL = 0x0003

            def render(fill_byte):
                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = cx
                bmi.biHeight = -cy          # top-down
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0       # BI_RGB
                hdc_screen = user32.GetDC(0)
                if not hdc_screen:
                    raise OSError("GetDC failed while rendering the cursor")
                hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
                if not hdc_mem:
                    user32.ReleaseDC(0, hdc_screen)
                    raise OSError(
                        "CreateCompatibleDC failed while rendering the cursor")
                bits = ctypes.c_void_p()
                hbmp = gdi32.CreateDIBSection(
                    hdc_screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
                old = None
                try:
                    if not hbmp or not bits.value:
                        raise OSError(
                            "CreateDIBSection failed while rendering the cursor")
                    old = gdi32.SelectObject(hdc_mem, hbmp)
                    if not old or old == ctypes.c_void_p(-1).value:
                        raise OSError(
                            "SelectObject failed while rendering the cursor")
                    ctypes.memset(bits, fill_byte, cx * cy * 4)
                    if not user32.DrawIconEx(
                            hdc_mem, 0, 0, hcursor, cx, cy, 0, None,
                            DI_NORMAL):
                        raise OSError("DrawIconEx failed")
                    gdi32.GdiFlush()
                    data = bytes((ctypes.c_ubyte * (cx * cy * 4)).from_address(bits.value))
                    return data
                finally:
                    if old:
                        gdi32.SelectObject(hdc_mem, old)
                    if hbmp:
                        gdi32.DeleteObject(hbmp)
                    gdi32.DeleteDC(hdc_mem)
                    user32.ReleaseDC(0, hdc_screen)

            on_black = render(0x00)
            on_white = render(0xFF)
            out = bytearray(cx * cy * 4)
            visible = False
            for i in range(0, cx * cy * 4, 4):
                # bg is neutral grey, so any channel gives the coverage; use blue.
                a = 255 - (on_white[i] - on_black[i])
                a = 0 if a < 0 else 255 if a > 255 else a
                if a == 0:
                    continue
                visible = True
                # on_black holds premultiplied colour; un-premultiply to straight.
                out[i] = min(255, on_black[i] * 255 // a)
                out[i + 1] = min(255, on_black[i + 1] * 255 // a)
                out[i + 2] = min(255, on_black[i + 2] * 255 // a)
                out[i + 3] = a
            if not visible:
                return None
            return QImage(bytes(out), cx, cy, QImage.Format_ARGB32).copy()
        except Exception:
            return None

    @staticmethod
    def _capture_fullscreen_win32():
        """Capture fullscreen using Win32 API for better DPI handling."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleBitmap.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi32.SelectObject.restype = wintypes.HANDLE
        gdi32.BitBlt.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
            wintypes.DWORD,
        ]
        gdi32.BitBlt.restype = wintypes.BOOL
        gdi32.GetDIBits.argtypes = [
            wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
            ctypes.c_void_p, ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT,
        ]
        gdi32.GetDIBits.restype = ctypes.c_int
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL

        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79

        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        if (w < 1 or h < 1 or w > MAX_IMAGE_DIMENSION
                or h > MAX_IMAGE_DIMENSION or w * h > MAX_IMAGE_PIXELS):
            raise ValueError(f"Virtual desktop size is unsafe: {w}x{h}")

        hdc_screen = user32.GetDC(None)
        if not hdc_screen:
            raise OSError("GetDC failed")
        hdc_mem = None
        hbmp = None
        old_bmp = None
        bitmap_selected = False
        try:
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            if not hdc_mem:
                raise OSError("CreateCompatibleDC failed")
            hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
            if not hbmp:
                raise OSError("CreateCompatibleBitmap failed")
            old_bmp = gdi32.SelectObject(hdc_mem, hbmp)
            if not old_bmp or old_bmp == ctypes.c_void_p(-1).value:
                raise OSError("SelectObject failed")
            bitmap_selected = True

            # CAPTUREBLT includes layered/transparent windows (tooltips, some
            # overlays) that plain SRCCOPY misses; without it they capture black.
            SRCCOPY = 0x00CC0020
            CAPTUREBLT = 0x40000000
            if not gdi32.BitBlt(
                    hdc_mem, 0, 0, w, h, hdc_screen, x, y,
                    SRCCOPY | CAPTUREBLT):
                raise OSError("BitBlt failed")

            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0

            buf_size = w * h * 4
            buf = ctypes.create_string_buffer(buf_size)
            # GetDIBits requires the bitmap NOT to be selected into a DC.
            if not gdi32.SelectObject(hdc_mem, old_bmp):
                raise OSError("Could not deselect capture bitmap")
            bitmap_selected = False
            scan_lines = gdi32.GetDIBits(
                hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
            if scan_lines != h:
                raise OSError(
                    f"GetDIBits returned {scan_lines} of {h} scan lines")

            # Screen blits carry undefined alpha bytes (layered windows can leave
            # alpha < 255); RGB32 ignores them instead of saving transparent holes.
            img = QImage(buf, w, h, w * 4, QImage.Format_RGB32)
            pixmap = QPixmap.fromImage(img.copy())
            if pixmap.isNull():
                raise OSError("Qt could not create the captured image")
            return pixmap
        finally:
            if bitmap_selected and hdc_mem and old_bmp:
                gdi32.SelectObject(hdc_mem, old_bmp)
            if hbmp:
                gdi32.DeleteObject(hbmp)
            if hdc_mem:
                gdi32.DeleteDC(hdc_mem)
            user32.ReleaseDC(None, hdc_screen)

    @staticmethod
    def capture_active_window():
        """Capture the currently active/foreground window."""
        if sys.platform == 'win32':
            try:
                return CaptureManager._capture_window_win32()
            except Exception:
                log.warning("Win32 window capture failed; falling back to full-screen grab",
                            exc_info=True)
        screen = QApplication.primaryScreen()
        if screen is None:
            return None
        return screen.grabWindow(0)

    @staticmethod
    def _capture_window_win32():
        """Capture the foreground window using Win32 API."""
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return CaptureManager.capture_fullscreen()

        rect = wintypes.RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        result = dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if result != 0:
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

        x, y = rect.left, rect.top
        w = rect.right - rect.left
        h = rect.bottom - rect.top

        if w <= 0 or h <= 0:
            return CaptureManager.capture_fullscreen()

        return CaptureManager.capture_rect(QRect(x, y, w, h))

    @staticmethod
    def capture_monitor(monitor_index=0):
        """Capture a specific monitor.

        Grabs via the monitor's own QScreen: grabbing another screen's
        area through the primary screen with logical coordinates returns
        the wrong region under mixed/high-DPI scaling.
        """
        screens = QApplication.screens()
        if 0 <= monitor_index < len(screens):
            return screens[monitor_index].grabWindow(0)
        return CaptureManager.capture_fullscreen()

    @staticmethod
    def crop_image(pixmap, rect):
        """Crop a QPixmap to the given QRect."""
        if pixmap is None or rect is None:
            return None
        img_rect = pixmap.rect()
        crop_rect = rect.intersected(img_rect)
        if crop_rect.width() < 1 or crop_rect.height() < 1:
            return None
        return pixmap.copy(crop_rect)

    @staticmethod
    def get_cursor_position():
        """Get the current cursor position."""
        return QCursor.pos()

    @staticmethod
    def get_window_list():
        """Get list of open windows (Windows only)."""
        windows = []
        if sys.platform == 'win32':
            try:
                import ctypes
                from ctypes import wintypes

                user32 = ctypes.windll.user32

                EnumWindowsProc = ctypes.WINFUNCTYPE(
                    ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
                )
                user32.EnumWindows.argtypes = [
                    EnumWindowsProc, wintypes.LPARAM]
                user32.EnumWindows.restype = wintypes.BOOL
                user32.IsWindowVisible.argtypes = [wintypes.HWND]
                user32.IsWindowVisible.restype = wintypes.BOOL
                user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
                user32.GetWindowTextLengthW.restype = ctypes.c_int
                user32.GetWindowTextW.argtypes = [
                    wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
                user32.GetWindowTextW.restype = ctypes.c_int

                def callback(hwnd, lparam):
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            title = buf.value
                            if title:
                                windows.append((hwnd, title))
                    return True

                # Store callback reference to prevent GC during enumeration
                cb = EnumWindowsProc(callback)
                user32.EnumWindows(cb, 0)
            except Exception:
                pass

        return windows
