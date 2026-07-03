"""
SwiftShot Capture Module
Handles all screenshot capture operations: fullscreen, window, region.
Uses native Windows APIs where available, falls back to Qt for cross-platform.
Includes mouse pointer overlay and camera sound support.
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QImage, QPainter, QCursor
from PyQt5.QtCore import QPoint

from utils import virtual_geometry
from config import config
from logger import log


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
            screen = QApplication.primaryScreen()
            if screen is None:
                return None
            geometry = virtual_geometry()
            pixmap = screen.grabWindow(0, geometry.x(), geometry.y(),
                                       geometry.width(), geometry.height())

        if pixmap and config.CAPTURE_MOUSE_POINTER:
            pixmap = CaptureManager._draw_cursor(pixmap)

        # Camera sound is played by the app when a capture completes,
        # not here: this method also grabs overlay backdrops.
        return pixmap

    @staticmethod
    def _draw_cursor(pixmap):
        """Draw the mouse cursor onto the screenshot."""
        if sys.platform != 'win32':
            return pixmap

        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            class CURSORINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.DWORD),
                    ('flags', wintypes.DWORD),
                    ('hCursor', wintypes.HANDLE),
                    ('ptScreenPos', wintypes.POINT),
                ]

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

            ii = ICONINFO()
            if user32.GetIconInfo(ci.hCursor, ctypes.byref(ii)):
                cursor_x -= ii.xHotspot
                cursor_y -= ii.yHotspot
                if ii.hbmMask:
                    ctypes.windll.gdi32.DeleteObject(ii.hbmMask)
                if ii.hbmColor:
                    ctypes.windll.gdi32.DeleteObject(ii.hbmColor)

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
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

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
                hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
                bits = ctypes.c_void_p()
                hbmp = gdi32.CreateDIBSection(
                    hdc_screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
                try:
                    old = gdi32.SelectObject(hdc_mem, hbmp)
                    ctypes.memset(bits, fill_byte, cx * cy * 4)
                    user32.DrawIconEx(hdc_mem, 0, 0, hcursor, cx, cy, 0, None, DI_NORMAL)
                    gdi32.GdiFlush()
                    data = bytes((ctypes.c_ubyte * (cx * cy * 4)).from_address(bits.value))
                    gdi32.SelectObject(hdc_mem, old)
                    return data
                finally:
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

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79

        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)

        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf_size = w * h * 4
        buf = ctypes.create_string_buffer(buf_size)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

        img = QImage(buf, w, h, w * 4, QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(img.copy())

        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

        return pixmap

    @staticmethod
    def capture_active_window():
        """Capture the currently active/foreground window."""
        if sys.platform == 'win32':
            try:
                return CaptureManager._capture_window_win32()
            except Exception:
                pass
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

        screen = QApplication.primaryScreen()
        if screen:
            return screen.grabWindow(0, x, y, w, h)
        return None

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
