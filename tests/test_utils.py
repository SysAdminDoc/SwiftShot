from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QColor, QPixmap

import utils


def test_clamp_bounds_values():
    assert utils.clamp(-1, 0, 10) == 0
    assert utils.clamp(5, 0, 10) == 5
    assert utils.clamp(11, 0, 10) == 10


def test_distance_between_points():
    assert utils.distance(QPoint(0, 0), QPoint(3, 4)) == 5


def test_color_helpers(qapp):
    pixmap = QPixmap(2, 2)
    pixmap.fill(QColor(12, 34, 56))

    assert utils.pixel_color_at(pixmap, 1, 1) == (12, 34, 56)
    assert utils.pixel_color_at(pixmap, -1, 1) == (0, 0, 0)
    assert utils.color_to_hex(12, 34, 56) == "#0C2238"
