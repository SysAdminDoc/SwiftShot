"""
SwiftShot Capture Module
Handles all screenshot capture operations: fullscreen, window, region.
Uses native Windows APIs where available, falls back to Qt for cross-platform.
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QScreen, QImage
from PyQt5.QtCore import QRect, Qt


class CaptureManager:
    """Static methods for capturing screenshots."""
    
    @staticmethod
    def capture_fullscreen():
        """Capture the entire virtual desktop (all monitors)."""
        try:
            if sys.platform == 'win32':
                return CaptureManager._capture_fullscreen_win32()
        except Exception:
            pass
        
        # Qt fallback (works cross-platform)
        screen = QApplication.primaryScreen()
        if screen is None:
            return None
        
        # Capture the virtual desktop (all screens)
        desktop = QApplication.desktop()
        if desktop:
            geometry = desktop.geometry()
            return screen.grabWindow(0, geometry.x(), geometry.y(),
                                      geometry.width(), geometry.height())
        
        return screen.grabWindow(0)
    
    @staticmethod
    def _capture_fullscreen_win32():
        """Capture fullscreen using Win32 API for better DPI handling."""
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        
        # Get virtual screen dimensions (all monitors)
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79
        
        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        
        # Create device contexts
        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        old_bmp = gdi32.SelectObject(hdc_mem, hbmp)
        
        # BitBlt the screen
        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, SRCCOPY)
        
        # Convert HBITMAP to QPixmap
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
        
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # Top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB
        
        buf_size = w * h * 4
        buf = ctypes.create_string_buffer(buf_size)
        
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
        
        # Create QImage from buffer
        img = QImage(buf, w, h, w * 4, QImage.Format_ARGB32)
        pixmap = QPixmap.fromImage(img.copy())  # .copy() to detach from buffer
        
        # Cleanup
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
        
        # Qt fallback
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
        
        # Try to get extended frame bounds (accounts for DWM shadows)
        rect = wintypes.RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        result = dwmapi.DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect),
            ctypes.sizeof(rect)
        )
        
        if result != 0:
            # Fallback to GetWindowRect
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
        
        x, y = rect.left, rect.top
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        
        if w <= 0 or h <= 0:
            return CaptureManager.capture_fullscreen()
        
        # Capture that region of the screen
        screen = QApplication.primaryScreen()
        if screen:
            return screen.grabWindow(0, x, y, w, h)
        
        return None
    
    @staticmethod
    def capture_monitor(monitor_index=0):
        """Capture a specific monitor."""
        screens = QApplication.screens()
        if monitor_index < len(screens):
            screen = screens[monitor_index]
            geometry = screen.geometry()
            primary = QApplication.primaryScreen()
            return primary.grabWindow(
                0, geometry.x(), geometry.y(),
                geometry.width(), geometry.height()
            )
        return CaptureManager.capture_fullscreen()
    
    @staticmethod
    def crop_image(pixmap, rect):
        """Crop a QPixmap to the given QRect."""
        if pixmap is None or rect is None:
            return None
        
        # Ensure rect is within bounds
        img_rect = pixmap.rect()
        crop_rect = rect.intersected(img_rect)
        
        if crop_rect.width() < 1 or crop_rect.height() < 1:
            return None
        
        return pixmap.copy(crop_rect)
    
    @staticmethod
    def get_cursor_position():
        """Get the current cursor position."""
        from PyQt5.QtGui import QCursor
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
                
                user32.EnumWindows(EnumWindowsProc(callback), 0)
            except Exception:
                pass
        
        return windows
