import sys

import pytest
from PyQt5.QtCore import QRect
from PyQt5.QtGui import QColor, QPixmap

from capture import CaptureManager


def test_crop_image_returns_intersection(qapp):
    pixmap = QPixmap(100, 80)
    pixmap.fill(QColor("red"))

    cropped = CaptureManager.crop_image(pixmap, QRect(10, 20, 30, 40))

    assert cropped is not None
    assert cropped.width() == 30
    assert cropped.height() == 40


def test_crop_image_rejects_empty_intersection(qapp):
    pixmap = QPixmap(100, 80)
    pixmap.fill(QColor("red"))

    assert CaptureManager.crop_image(pixmap, QRect(200, 200, 10, 10)) is None
    assert CaptureManager.crop_image(None, QRect(0, 0, 10, 10)) is None


def test_capture_rect_composites_each_monitor_in_local_coordinates(
        qapp, monkeypatch):
    import capture

    class _Screen:
        def __init__(self, rect, color):
            self._rect = rect
            self._pixmap = QPixmap(rect.size())
            self._pixmap.fill(QColor(color))
            self.grabs = 0

        def geometry(self):
            return QRect(self._rect)

        def grabWindow(self, _window, x, y, width, height):
            self.grabs += 1
            return self._pixmap.copy(x, y, width, height)

    left = _Screen(QRect(-100, 0, 100, 80), "red")
    right = _Screen(QRect(0, 0, 100, 80), "blue")
    monkeypatch.setattr(capture.QApplication, "screens", lambda: [left, right])
    monkeypatch.setattr(
        capture, "virtual_geometry", lambda: QRect(-100, 0, 200, 80))

    result = CaptureManager.capture_rect(QRect(-20, 10, 40, 20))

    assert result.size().width() == 40
    assert result.size().height() == 20
    assert result.toImage().pixelColor(5, 5) == QColor("red")
    assert result.toImage().pixelColor(35, 5) == QColor("blue")
    assert left.grabs == right.grabs == 1


def test_capture_rect_scales_high_dpi_grab_to_logical_destination(
        qapp, monkeypatch):
    import capture

    class _HighDpiScreen:
        def geometry(self):
            return QRect(0, 0, 20, 10)

        def grabWindow(self, _window, _x, _y, width, height):
            pixmap = QPixmap(width * 2, height * 2)
            pixmap.fill(QColor("green"))
            return pixmap

    monkeypatch.setattr(capture.QApplication, "screens",
                        lambda: [_HighDpiScreen()])
    monkeypatch.setattr(capture, "virtual_geometry", lambda: QRect(0, 0, 20, 10))

    result = CaptureManager.capture_rect(QRect(5, 2, 10, 5))

    assert result.size().width() == 10
    assert result.size().height() == 5
    assert result.toImage().pixelColor(9, 4) == QColor("green")


def test_capture_rect_rejects_unsafe_dimensions_before_allocating(
        qapp, monkeypatch):
    import capture

    unsafe = QRect(0, 0, capture.MAX_IMAGE_DIMENSION + 1, 10)
    monkeypatch.setattr(capture, "virtual_geometry", lambda: QRect(unsafe))
    screens_called = []
    monkeypatch.setattr(
        capture.QApplication,
        "screens",
        lambda: screens_called.append(True) or [],
    )

    assert CaptureManager.capture_rect(unsafe) is None
    assert screens_called == []


def test_cursor_to_qimage_none_handle(qapp):
    assert CaptureManager._cursor_to_qimage(None) is None


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 cursor rendering")
@pytest.mark.parametrize("idc", [32512, 32513, 32649, 32646])  # arrow, ibeam, hand, sizeall
def test_cursor_to_qimage_renders_real_cursor_shapes(qapp, idc):
    """Real cursor shapes (incl. legacy no-alpha I-beam/resize) must render
    with opaque content, not fall back to the generic arrow."""
    import ctypes

    hcursor = ctypes.windll.user32.LoadCursorW(None, idc)
    img = CaptureManager._cursor_to_qimage(hcursor)

    assert img is not None and not img.isNull()
    assert any(
        img.pixelColor(x, y).alpha() > 200
        for y in range(img.height()) for x in range(img.width())
    )
