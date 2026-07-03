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


def test_beautification_preset_expands_pixmap(qapp):
    pixmap = QPixmap(20, 10)
    pixmap.fill(QColor(200, 40, 80))

    beautified = utils.apply_beautification_preset(pixmap, "presentation")

    assert beautified.width() > pixmap.width()
    assert beautified.height() > pixmap.height()


def test_save_pixmap_gif_uses_pillow(qapp, tmp_path):
    """Qt has no GIF encoder -- 'gif' output must round-trip via Pillow
    (regression: it silently saved nothing)."""
    from PIL import Image

    pixmap = QPixmap(8, 8)
    pixmap.fill(QColor(10, 200, 30))
    path = tmp_path / "shot.gif"

    assert utils.save_pixmap(pixmap, str(path), "gif") is True
    with Image.open(path) as img:
        assert img.format == "GIF"
        assert img.size == (8, 8)


def test_save_pixmap_failure_returns_false(qapp, tmp_path):
    pixmap = QPixmap(4, 4)
    pixmap.fill(QColor(0, 0, 0))
    missing_dir = tmp_path / "does-not-exist" / "shot.png"

    assert utils.save_pixmap(pixmap, str(missing_dir), "png") is False


def test_apply_freehand_mask_masks_outside_polygon(qapp):
    """Freehand capture must be masked to the drawn shape (regression:
    it silently degraded to the bounding rectangle)."""
    from PyQt5.QtCore import QRect

    pixmap = QPixmap(20, 20)
    pixmap.fill(QColor(255, 0, 0))
    rect = QRect(0, 0, 20, 20)
    # Triangle covering the lower-left half
    points = [QPoint(0, 0), QPoint(0, 19), QPoint(19, 19)]

    masked = utils.apply_freehand_mask(pixmap, points, rect)
    img = masked.toImage()

    # Inside the triangle: opaque red; far corner outside: transparent
    assert img.pixelColor(2, 17).alpha() == 255
    assert img.pixelColor(18, 1).alpha() == 0


def test_apply_freehand_mask_degenerate_points_returns_original(qapp):
    from PyQt5.QtCore import QRect

    pixmap = QPixmap(5, 5)
    pixmap.fill(QColor(1, 2, 3))
    result = utils.apply_freehand_mask(
        pixmap, [QPoint(0, 0), QPoint(1, 1)], QRect(0, 0, 5, 5))
    assert result is pixmap
