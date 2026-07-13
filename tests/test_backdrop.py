"""Tests for the padded backdrop step in the capture funnel."""

from PyQt5.QtGui import QColor, QImage, QPixmap


def _pixmap(w, h, color=(200, 30, 30, 255)):
    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(QColor(*color))
    return QPixmap.fromImage(img)


def test_backdrop_disabled_is_noop(qapp, fresh_config):
    import utils
    px = _pixmap(20, 10)
    out = utils.apply_backdrop(px)
    assert out.width() == 20 and out.height() == 10


def test_backdrop_solid_pads_and_fills(qapp, fresh_config):
    import utils
    fresh_config.config.BACKDROP_ENABLED = True
    fresh_config.config.BACKDROP_TYPE = "solid"
    fresh_config.config.BACKDROP_PADDING = 12
    fresh_config.config.BACKDROP_COLOR = "#1e1e2e"

    out = utils.apply_backdrop(_pixmap(20, 10))
    assert out.width() == 20 + 24 and out.height() == 10 + 24
    # a corner pixel is the backdrop colour
    corner = out.toImage().pixelColor(0, 0)
    assert (corner.red(), corner.green(), corner.blue()) == (0x1e, 0x1e, 0x2e)


def test_backdrop_gradient_pads(qapp, fresh_config):
    import utils
    fresh_config.config.BACKDROP_ENABLED = True
    fresh_config.config.BACKDROP_TYPE = "gradient"
    fresh_config.config.BACKDROP_PADDING = 8
    fresh_config.config.BACKDROP_COLOR = "#000000"
    fresh_config.config.BACKDROP_COLOR2 = "#ffffff"

    out = utils.apply_backdrop(_pixmap(16, 16))
    assert out.width() == 32 and out.height() == 32
    top = out.toImage().pixelColor(0, 0).red()
    bottom = out.toImage().pixelColor(0, 31).red()
    assert bottom > top          # gradient darkens→lightens top to bottom


def test_backdrop_window_frame_adds_titlebar(qapp, fresh_config):
    import utils
    fresh_config.config.BACKDROP_ENABLED = True
    fresh_config.config.BACKDROP_TYPE = "solid"
    fresh_config.config.BACKDROP_PADDING = 10
    fresh_config.config.BACKDROP_COLOR = "#1e1e2e"

    for style, bar_h in (("macos", 30), ("windows", 34)):
        fresh_config.config.BACKDROP_FRAME = style
        out = utils.apply_backdrop(_pixmap(40, 20))
        # width unchanged (+2*pad); height grows by the titlebar (+2*pad).
        assert out.width() == 40 + 20
        assert out.height() == 20 + bar_h + 20


def test_window_frame_helper_returns_taller_rgba(qapp):
    from PIL import Image
    from utils import _window_frame
    src = Image.new("RGBA", (30, 20), (10, 20, 30, 255))
    framed = _window_frame(src, "macos")
    assert framed.mode == "RGBA"
    assert framed.width == 30 and framed.height > 20   # titlebar added
    assert framed.getpixel((0, 0))[3] == 0             # rounded corner is clear
