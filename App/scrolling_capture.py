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
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QProgressBar
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QTimer, QRect

from logger import log
from utils import exclude_window_from_capture


MAX_SCROLL_RAW_PIXELS = 75_000_000
MAX_SCROLL_RESULT_PIXELS = 100_000_000
MAX_SCROLL_RESULT_HEIGHT = 32_768


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
        self._raw_pixels = 0
        self._truncated_for_safety = False
        self._generation = 0
        self._awaiting_target = False

        # Styling comes from the app-wide theme stylesheet.
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

    def reject(self):
        # Cancel/Escape must stop the capture loop — a pending singleShot
        # kept _capture_frame firing (and auto-scrolling the user's window)
        # long after the dialog was dismissed.
        self._invalidate_capture()
        super().reject()

    def closeEvent(self, event):
        self._invalidate_capture()
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        exclude_window_from_capture(self)

    def _invalidate_capture(self):
        """Invalidate every callback queued by the current capture run."""
        self._generation += 1
        self._awaiting_target = False
        self._capturing = False

    def _capture_callback_is_current(self, generation, require_capturing=False):
        if generation != self._generation or not self.isVisible():
            return False
        if require_capturing and not self._capturing:
            return False
        return True

    def _dodge_target(self):
        """Move this always-on-top dialog out of the capture rect — otherwise
        it can obscure the target for the user. Display affinity is the
        capture-exclusion fallback when no non-overlapping corner exists."""
        if not self.frameGeometry().intersects(self._target_rect):
            return
        screen = QApplication.screenAt(self._target_rect.center())
        if screen:
            geo = screen.availableGeometry()
            fg = self.frameGeometry()
            corners = [
                (geo.left(), geo.top()),
                (geo.right() - fg.width(), geo.top()),
                (geo.left(), geo.bottom() - fg.height()),
                (geo.right() - fg.width(), geo.bottom() - fg.height()),
            ]
            for x, y in corners:
                if not QRect(x, y, fg.width(), fg.height()).intersects(self._target_rect):
                    self.move(x, y)
                    return
        # Display affinity keeps the dialog out of the captured pixels even
        # when no non-overlapping corner is available. Staying visible also
        # gives delayed callbacks a reliable lifecycle guard.

    def _begin_capture(self):
        if sys.platform != 'win32':
            self.status_label.setText("Scrolling capture is only supported on Windows.")
            return

        self._invalidate_capture()
        self._awaiting_target = True
        generation = self._generation
        self.status_label.setText("Click on the window to capture in 3 seconds...")
        self.start_btn.setEnabled(False)
        QTimer.singleShot(3000, lambda: self._identify_window(generation))

    def _identify_window(self, generation=None):
        generation = self._generation if generation is None else generation
        if (not self._capture_callback_is_current(generation)
                or not self._awaiting_target):
            return
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.argtypes = []
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL

        # Get foreground window
        self._target_hwnd = user32.GetForegroundWindow()
        if not self._target_hwnd:
            self._awaiting_target = False
            self.status_label.setText("Could not identify target window.")
            self.start_btn.setEnabled(True)
            log.warning("Scrolling capture: no foreground window found")
            return

        # If no other window was clicked, the foreground window is this
        # dialog -- scrolling and capturing ourselves is never intended.
        if self._target_hwnd == int(self.winId()):
            self._awaiting_target = False
            self.status_label.setText(
                "That was this dialog. Click 'Start', then click the window "
                "you want to capture.")
            self._target_hwnd = None
            self.start_btn.setEnabled(True)
            return

        # Get window rect
        rect = wintypes.RECT()
        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
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
            self._awaiting_target = False
            self.status_label.setText("Invalid window size detected.")
            self.start_btn.setEnabled(True)
            return

        self.status_label.setText("Capturing... scrolling down")
        self.stop_btn.setEnabled(True)
        self.progress.setVisible(True)
        self._awaiting_target = False
        self._capturing = True
        self._frames = []
        self._raw_pixels = 0
        self._truncated_for_safety = False
        self._scroll_count = 0
        self._dodge_target()

        # Focus the target window
        user32.SetForegroundWindow(self._target_hwnd)
        QTimer.singleShot(200, lambda: self._capture_frame(generation))

    def _capture_frame(self, generation=None):
        generation = self._generation if generation is None else generation
        if not self._capture_callback_is_current(
                generation, require_capturing=True):
            return

        # Capture the current visible area
        from capture import CaptureManager
        frame = CaptureManager.capture_rect(self._target_rect)
        if frame is None or frame.isNull():
            self._finish(generation)
            return

        frame_pixels = frame.width() * frame.height()
        if self._raw_pixels + frame_pixels > MAX_SCROLL_RAW_PIXELS:
            if not self._frames:
                self._invalidate_capture()
                self.stop_btn.setEnabled(False)
                self.start_btn.setEnabled(True)
                self.status_label.setText(
                    "The selected window is too large for a safe scrolling "
                    "capture. Resize it and try again.")
                log.warning("Scrolling capture rejected an oversized frame")
                return
            self._truncated_for_safety = True
            log.info("Scrolling capture reached the in-memory frame limit")
            self._finish(generation)
            return

        self._frames.append(frame)
        self._raw_pixels += frame_pixels
        self._scroll_count += 1
        self.progress.setValue(self._scroll_count)

        # Check if we've reached the limit
        if self._scroll_count >= self._max_scrolls:
            self._finish(generation)
            return

        # Check if content stopped changing (compare last two frames)
        if len(self._frames) >= 2:
            if self._frames_are_identical(self._frames[-1], self._frames[-2]):
                self._finish(generation)
                return

        # Scroll down and capture next frame
        self._scroll_window(generation)
        QTimer.singleShot(400, lambda: self._capture_frame(generation))

    def _scroll_window(self, generation=None):
        """Send scroll-down to the target window."""
        generation = self._generation if generation is None else generation
        if not self._capture_callback_is_current(
                generation, require_capturing=True):
            return
        if sys.platform != 'win32':
            return
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        WM_MOUSEWHEEL = 0x020A
        WHEEL_DELTA = 120

        # Calculate center of the window client area
        cx = self._target_rect.x() + self._target_rect.width() // 2
        cy = self._target_rect.y() + self._target_rect.height() // 2

        # MAKELPARAM/HIWORD must pack each coordinate as a signed 16-bit word.
        # On a multi-monitor desktop cx/cy can be negative (monitor left of or
        # above the primary); masking each to 0xFFFF keeps the sign bits from
        # bleeding across the word boundary and corrupting the target point.
        wparam = ((-3 * WHEEL_DELTA) & 0xFFFF) << 16   # HIWORD = wheel delta
        lparam = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)  # MAKELPARAM(x, y)

        user32.PostMessageW(wintypes.HWND(self._target_hwnd), WM_MOUSEWHEEL,
                            wintypes.WPARAM(wparam), wintypes.LPARAM(lparam))

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

    def _finish(self, generation=None):
        generation = self._generation if generation is None else generation
        if generation != self._generation:
            return
        self._invalidate_capture()
        completion_generation = self._generation
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
        if (completion_generation != self._generation
                or not self.isVisible()):
            return
        log.info(f"Scrolling capture: stitching {len(self._frames)} frames")

        self._result_pixmap = self._stitch_frames()
        if (completion_generation != self._generation
                or not self.isVisible()):
            return
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
        self._finish(self._generation)

    def _static_bottom_height(self):
        """Height of a bottom band that stays identical between consecutive
        frames — a fixed footer or sticky scrollbar that would otherwise be
        stitched into the output once per frame (ShareX 17's auto-ignore-edge).
        Returns 0 unless a clear static band is found."""
        if len(self._frames) < 2:
            return 0
        runs = []
        for a, b in zip(self._frames, self._frames[1:]):
            ia, ib = a.toImage(), b.toImage()
            h = min(ia.height(), ib.height())
            w = min(ia.width(), ib.width())
            if h == 0 or w == 0:
                return 0
            run = 0
            for dy in range(1, h + 1):
                y = h - dy
                same = all(ia.pixel(sx, y) == ib.pixel(sx, y)
                           for sx in range(0, w, max(1, w // 10)))
                if not same:
                    break
                run = dy
            runs.append(run)
        static = min(runs) if runs else 0
        if static < 8:                       # ignore trivial/no footer
            return 0
        return min(static, self._frames[0].height() // 3)   # never eat real content

    def _stitch_frames(self):
        """Stitch frames together by detecting overlap."""
        if not self._frames:
            return None

        # Trim a detected static footer from every frame but the last, so a
        # fixed footer/scrollbar appears once instead of being repeated.
        static_h = self._static_bottom_height()
        frames = list(self._frames)
        if static_h > 0:
            frames = [
                (f.copy(0, 0, f.width(), f.height() - static_h)
                 if i < len(frames) - 1 else f)
                for i, f in enumerate(frames)
            ]

        base = frames[0]
        w = base.width()

        # Simple stitching: find overlap between consecutive frames
        # by comparing bottom of frame N with top of frame N+1
        result_height = base.height()
        offsets = [0]
        max_height = min(
            MAX_SCROLL_RESULT_HEIGHT,
            MAX_SCROLL_RESULT_PIXELS // max(1, w),
        )
        if result_height > max_height:
            return None

        for i in range(1, len(frames)):
            overlap = self._find_overlap(frames[i - 1], frames[i])
            new_content = frames[i].height() - overlap
            if new_content <= 5:
                # No new content, stop here
                break
            if result_height + new_content > max_height:
                self._truncated_for_safety = True
                log.info("Scrolling output reached the decoded-image limit")
                break
            offsets.append(result_height - overlap)
            result_height += new_content

        # Create the stitched image
        result = QPixmap(w, result_height)
        result.fill(QColor(0, 0, 0))

        painter = QPainter(result)
        for i, offset in enumerate(offsets):
            if i >= len(frames):
                break
            painter.drawPixmap(0, offset, frames[i])
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

        # Keep the SMALLEST strongly-matching overlap, not the largest. On
        # pages with repeating or uniform rows many overlap values score well;
        # picking the largest over-trims real (non-duplicated) content. We
        # update only on a strictly better score, so ties keep the earlier
        # (smaller) overlap.
        best_overlap = 0
        best_score = 0.0
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

            if samples > 0:
                score = matches / samples
                if score > 0.85 and score > best_score:
                    best_score = score
                    best_overlap = overlap

        return best_overlap

    def get_result(self):
        return self._result_pixmap

    def was_truncated(self):
        return self._truncated_for_safety
