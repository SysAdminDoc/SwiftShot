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
