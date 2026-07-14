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


def test_apply_frame_noop_when_all_disabled(qapp):
    """apply_frame must be a no-op (identity) unless a frame effect is enabled,
    so it is safe to call unconditionally in the capture funnel."""
    import config
    cfg = config.config
    cfg.BORDER_ENABLED = cfg.SHADOW_ENABLED = cfg.ROUNDED_CORNERS_ENABLED = False

    pixmap = QPixmap(10, 10)
    pixmap.fill(QColor(255, 0, 0))
    assert utils.apply_frame(pixmap) is pixmap


def test_apply_frame_border_preserves_size(qapp):
    """A border is stroked inside the capture, so dimensions are unchanged."""
    import config
    cfg = config.config
    cfg.ROUNDED_CORNERS_ENABLED = cfg.SHADOW_ENABLED = False
    cfg.BORDER_ENABLED = True
    cfg.BORDER_WIDTH = 3
    try:
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(255, 255, 255))
        out = utils.apply_frame(pixmap)
        assert (out.width(), out.height()) == (20, 20)
        # A border must have changed the edge pixels.
        assert utils.pixel_color_at(out, 0, 0) != (255, 255, 255)
    finally:
        cfg.BORDER_ENABLED = False


def test_apply_frame_shadow_pads_canvas(qapp):
    """A drop shadow expands the canvas to make room for the blur."""
    import config
    cfg = config.config
    cfg.ROUNDED_CORNERS_ENABLED = cfg.BORDER_ENABLED = False
    cfg.SHADOW_ENABLED = True
    cfg.SHADOW_RADIUS = 10
    try:
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor(255, 255, 255))
        out = utils.apply_frame(pixmap)
        assert out.width() > 20 and out.height() > 20
    finally:
        cfg.SHADOW_ENABLED = False


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


class _AffinityWidget:
    def winId(self):
        return 1234


class _AffinityApi:
    def __init__(self, accepted):
        self.accepted = list(accepted)
        self.calls = []

    def SetWindowDisplayAffinity(self, hwnd, affinity):
        self.calls.append((hwnd, affinity))
        return self.accepted.pop(0)


def test_display_affinity_prefers_capture_exclusion(monkeypatch):
    monkeypatch.setattr(utils.sys, "platform", "win32")
    api = _AffinityApi([True])

    result = utils.exclude_window_from_capture(_AffinityWidget(), api)

    assert result == utils.WDA_EXCLUDEFROMCAPTURE
    assert api.calls == [(1234, utils.WDA_EXCLUDEFROMCAPTURE)]


def test_display_affinity_falls_back_for_older_windows(monkeypatch):
    monkeypatch.setattr(utils.sys, "platform", "win32")
    api = _AffinityApi([False, True])

    result = utils.exclude_window_from_capture(_AffinityWidget(), api)

    assert result == utils.WDA_MONITOR
    assert api.calls == [
        (1234, utils.WDA_EXCLUDEFROMCAPTURE),
        (1234, utils.WDA_MONITOR),
    ]


def test_display_affinity_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr(utils.sys, "platform", "linux")
    api = _AffinityApi([True])

    assert utils.exclude_window_from_capture(_AffinityWidget(), api) == utils.WDA_NONE
    assert api.calls == []
