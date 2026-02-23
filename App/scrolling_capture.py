"""
SwiftShot Scrolling Capture
Captures an entire scrollable window by auto-scrolling and stitching
multiple screenshots together.

Strategy:
1. User clicks the target window
2. Capture initial visible area
3. Simulate scroll-down, capture again
4. Detect overlap between consecutive frames
5. Stitch together
6. Stop when no new content appears
"""

import sys
import time
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QProgressBar
from PyQt5.QtGui import QPixmap, QPainter, QImage, QColor, QFont
from PyQt5.QtCore import Qt, QTimer, QRect

from config import config
from logger import log


class ScrollingCaptureDialog(QDialog):
    """Dialog that orchestrates the scrolling capture."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scrolling Capture - SwiftShot")
        self.setMinimumSize(400, 200)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self._frames = []
        self._capturing = False
        self._target_hwnd = None
        self._target_rect = QRect()
        self._max_scrolls = 50
        self._scroll_count = 0
        self._result_pixmap = None

        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; }
            QLabel { color: #cdd6f4; background: transparent; }
            QPushButton {
                background-color: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 8px 20px; font-size: 10pt;
            }
            QPushButton:hover { background-color: #45475a; border-color: #89b4fa; }
            QProgressBar {
                background-color: #313244; border: 1px solid #45475a;
                border-radius: 4px; text-align: center; color: #cdd6f4;
            }
            QProgressBar::chunk {
                background-color: #89b4fa; border-radius: 3px;
            }
        """)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("Click 'Start' then click the window you want to capture.\n"
                                   "The tool will auto-scroll and stitch the full page.")
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, self._max_scrolls)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Capture")
        self.start_btn.clicked.connect(self._begin_capture)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop_capture)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _begin_capture(self):
        if sys.platform != 'win32':
            self.status_label.setText("Scrolling capture is only supported on Windows.")
            return

        self.status_label.setText("Click on the window to capture in 3 seconds...")
        self.start_btn.setEnabled(False)
        QTimer.singleShot(3000, self._identify_window)

    def _identify_window(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # Get foreground window
        self._target_hwnd = user32.GetForegroundWindow()
        if not self._target_hwnd:
            self.status_label.setText("Could not identify target window.")
            self.start_btn.setEnabled(True)
            log.warning("Scrolling capture: no foreground window found")
            return

        # Get window rect
        rect = wintypes.RECT()
        dwmapi = ctypes.windll.dwmapi
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        r = dwmapi.DwmGetWindowAttribute(
            self._target_hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(rect), ctypes.sizeof(rect)
        )
        if r != 0:
            user32.GetWindowRect(self._target_hwnd, ctypes.byref(rect))

        self._target_rect = QRect(
            rect.left, rect.top,
            rect.right - rect.left, rect.bottom - rect.top
        )

        if self._target_rect.width() < 10 or self._target_rect.height() < 10:
            self.status_label.setText("Invalid window size detected.")
            self.start_btn.setEnabled(True)
            return

        self.status_label.setText("Capturing... scrolling down")
        self.stop_btn.setEnabled(True)
        self.progress.setVisible(True)
        self._capturing = True
        self._frames = []
        self._scroll_count = 0

        # Focus the target window
        user32.SetForegroundWindow(self._target_hwnd)
        QTimer.singleShot(200, self._capture_frame)

    def _capture_frame(self):
        if not self._capturing:
            return

        # Capture the current visible area
        screen = QApplication.primaryScreen()
        if screen is None:
            self._finish()
            return

        frame = screen.grabWindow(
            0,
            self._target_rect.x(), self._target_rect.y(),
            self._target_rect.width(), self._target_rect.height()
        )

        if frame.isNull():
            self._finish()
            return

        self._frames.append(frame)
        self._scroll_count += 1
        self.progress.setValue(self._scroll_count)

        # Check if we've reached the limit
        if self._scroll_count >= self._max_scrolls:
            self._finish()
            return

        # Check if content stopped changing (compare last two frames)
        if len(self._frames) >= 2:
            if self._frames_are_identical(self._frames[-1], self._frames[-2]):
                self._finish()
                return

        # Scroll down and capture next frame
        self._scroll_window()
        QTimer.singleShot(400, self._capture_frame)

    def _scroll_window(self):
        """Send scroll-down to the target window."""
        if sys.platform != 'win32':
            return
        import ctypes
        user32 = ctypes.windll.user32

        WM_MOUSEWHEEL = 0x020A
        WHEEL_DELTA = 120

        # Calculate center of the window client area
        cx = self._target_rect.x() + self._target_rect.width() // 2
        cy = self._target_rect.y() + self._target_rect.height() // 2

        # Scroll down = negative delta
        wparam = (-3 * WHEEL_DELTA) << 16  # 3 notches down
        lparam = (cy << 16) | (cx & 0xFFFF)

        user32.PostMessageW(self._target_hwnd, WM_MOUSEWHEEL, wparam, lparam)

    def _frames_are_identical(self, f1, f2):
        """Quick check if two frames are identical (sample pixel comparison)."""
        img1 = f1.toImage()
        img2 = f2.toImage()

        if img1.size() != img2.size():
            return False

        w, h = img1.width(), img1.height()
        # Sample 20 points
        sample_count = 0
        match_count = 0
        for sy in range(0, h, max(1, h // 5)):
            for sx in range(0, w, max(1, w // 4)):
                sample_count += 1
                if img1.pixel(sx, sy) == img2.pixel(sx, sy):
                    match_count += 1

        if sample_count == 0:
            return True
        return (match_count / sample_count) > 0.98

    def _finish(self):
        self._capturing = False
        self.stop_btn.setEnabled(False)

        if len(self._frames) < 1:
            self.status_label.setText("No frames captured.")
            self.start_btn.setEnabled(True)
            return

        if len(self._frames) == 1:
            self._result_pixmap = self._frames[0]
            self.status_label.setText("Only one frame captured (window may not scroll).")
            self.accept()
            return

        self.status_label.setText(f"Stitching {len(self._frames)} frames...")
        QApplication.processEvents()
        log.info(f"Scrolling capture: stitching {len(self._frames)} frames")

        self._result_pixmap = self._stitch_frames()
        if self._result_pixmap:
            self.status_label.setText(
                f"Done! Stitched {len(self._frames)} frames into "
                f"{self._result_pixmap.width()}x{self._result_pixmap.height()} image."
            )
            self.accept()
        else:
            self.status_label.setText("Stitching failed.")
            self.start_btn.setEnabled(True)

    def _stop_capture(self):
        self._capturing = False
        self._finish()

    def _stitch_frames(self):
        """Stitch frames together by detecting overlap."""
        if not self._frames:
            return None

        base = self._frames[0]
        w = base.width()

        # Simple stitching: find overlap between consecutive frames
        # by comparing bottom of frame N with top of frame N+1
        result_height = base.height()
        offsets = [0]

        for i in range(1, len(self._frames)):
            overlap = self._find_overlap(self._frames[i - 1], self._frames[i])
            new_content = self._frames[i].height() - overlap
            if new_content <= 5:
                # No new content, stop here
                break
            offsets.append(result_height - overlap)
            result_height += new_content

        # Create the stitched image
        result = QPixmap(w, result_height)
        result.fill(QColor(0, 0, 0))

        painter = QPainter(result)
        for i, offset in enumerate(offsets):
            if i >= len(self._frames):
                break
            painter.drawPixmap(0, offset, self._frames[i])
        painter.end()

        return result

    def _find_overlap(self, top_frame, bottom_frame):
        """Find the vertical overlap between two frames by comparing pixel rows."""
        top_img = top_frame.toImage()
        bottom_img = bottom_frame.toImage()

        h = top_img.height()
        w = top_img.width()

        # Compare bottom rows of top_frame with top rows of bottom_frame
        max_check = min(h // 2, 300)  # Don't check more than half the frame

        best_overlap = 0
        for overlap in range(20, max_check, 2):
            matches = 0
            samples = 0
            for sx in range(0, w, max(1, w // 10)):
                samples += 1
                top_y = h - overlap
                if top_img.pixel(sx, top_y) == bottom_img.pixel(sx, 0):
                    matches += 1
                mid_y = overlap // 2
                if (h - overlap + mid_y) < h and mid_y < bottom_img.height():
                    samples += 1
                    if top_img.pixel(sx, h - overlap + mid_y) == bottom_img.pixel(sx, mid_y):
                        matches += 1

            if samples > 0 and (matches / samples) > 0.85:
                best_overlap = overlap

        return best_overlap

    def get_result(self):
        return self._result_pixmap
