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
