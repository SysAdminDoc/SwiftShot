"""Tests for scrolling-capture stitching, especially the static-footer
auto-ignore (R-05). Stitching is pure image math, so it is testable headless."""

from PyQt5.QtGui import QColor, QImage, QPixmap


def _frame(width, height, footer_h, content_offset):
    """A frame whose bottom `footer_h` rows are a constant footer and whose
    upper rows scroll with `content_offset`."""
    img = QImage(width, height, QImage.Format_RGB32)
    for y in range(height):
        if y >= height - footer_h:
            col = QColor(10, 10, 10)                 # static footer
        else:
            v = ((y + content_offset) * 7) % 256     # scrolling content
            col = QColor(v, (v * 2) % 256, (v * 3) % 256)
        for x in range(width):
            img.setPixelColor(x, y, col)
    return QPixmap.fromImage(img)


def _stub(frames):
    from scrolling_capture import ScrollingCaptureDialog

    class _S:
        _static_bottom_height = ScrollingCaptureDialog._static_bottom_height
        _find_overlap = ScrollingCaptureDialog._find_overlap
        _stitch_frames = ScrollingCaptureDialog._stitch_frames

    s = _S()
    s._frames = frames
    return s


def test_static_bottom_height_detects_fixed_footer(qapp):
    frames = [_frame(40, 100, 20, 0), _frame(40, 100, 20, 30),
              _frame(40, 100, 20, 60)]
    assert _stub(frames)._static_bottom_height() == 20


def test_no_static_footer_when_everything_scrolls(qapp):
    # No constant footer → nothing to trim.
    frames = [_frame(40, 100, 0, 0), _frame(40, 100, 0, 30)]
    assert _stub(frames)._static_bottom_height() == 0


def test_stitch_collapses_footer(qapp):
    frames = [_frame(40, 100, 20, 0), _frame(40, 100, 20, 30)]
    result = _stub(frames)._stitch_frames()
    assert result is not None
    # Taller than one frame (new content added) but far less than 2x (the
    # footer is not duplicated).
    assert 100 < result.height() < 200
