"""Pixel-level proof tests for Solid Redact and burn-in Auto-Redact (R-25).

Blur/pixelate only scramble pixels; Solid Redact must overwrite the source so
the exported bytes carry no recoverable original. These exercise the pure
staticmethod helpers (no dialog), so they run headless under the offscreen
qapp fixture.
"""

from PIL import Image


def _ed(qapp):
    from editor import ImageEditor
    return ImageEditor


def _rect_mask(size, box):
    """L-mode selection mask: 255 inside *box* (x0,y0,x1,y1), 0 outside."""
    m = Image.new("L", size, 0)
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            m.putpixel((x, y), 255)
    return m


def test_composite_solid_removes_source_pixels(qapp):
    Ed = _ed(qapp)
    src = Image.new("RGBA", (10, 10), (200, 50, 50, 255))
    mask = _rect_mask((10, 10), (2, 2, 6, 6))
    out = Ed._composite_solid(src, mask, (0, 0, 0, 255))

    # Inside the mask: pure black, no trace of the original red.
    assert out.getpixel((3, 3)) == (0, 0, 0, 255)
    assert out.getpixel((5, 5)) == (0, 0, 0, 255)
    # Outside the mask: original preserved.
    assert out.getpixel((0, 0)) == (200, 50, 50, 255)
    assert out.getpixel((9, 9)) == (200, 50, 50, 255)
    # Source image is not mutated (op returns a copy).
    assert src.getpixel((3, 3)) == (200, 50, 50, 255)


def test_composite_solid_white_fill(qapp):
    Ed = _ed(qapp)
    src = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
    mask = _rect_mask((8, 8), (0, 0, 4, 4))
    out = Ed._composite_solid(src, mask, (255, 255, 255, 255))
    assert out.getpixel((1, 1)) == (255, 255, 255, 255)
    assert out.getpixel((6, 6)) == (10, 20, 30, 255)


def test_composite_solid_resizes_mismatched_mask(qapp):
    Ed = _ed(qapp)
    src = Image.new("RGBA", (20, 20), (100, 100, 100, 255))
    mask = _rect_mask((10, 10), (0, 0, 5, 5))  # half-resolution mask
    out = Ed._composite_solid(src, mask, (0, 0, 0, 255))
    # Upper-left quadrant redacted after nearest-neighbour upscale.
    assert out.getpixel((2, 2)) == (0, 0, 0, 255)
    assert out.getpixel((18, 18)) == (100, 100, 100, 255)


def test_redaction_boxes_layer_paints_opaque_black(qapp):
    Ed = _ed(qapp)
    boxes = [{"x": 1, "y": 1, "w": 3, "h": 3}]
    layer = Ed._redaction_boxes_layer((10, 10), boxes)
    assert layer.getpixel((2, 2)) == (0, 0, 0, 255)   # inside box: opaque black
    assert layer.getpixel((8, 8)) == (0, 0, 0, 0)     # elsewhere: transparent


def test_burn_in_flatten_hides_pixels_under_all_layers(qapp):
    """Burn-in redaction on a flattened composite must leave no secret pixels
    anywhere in the single resulting image."""
    Ed = _ed(qapp)
    base = Image.new("RGBA", (12, 12), (255, 0, 0, 255))    # "secret" red field
    boxes = [{"x": 0, "y": 0, "w": 12, "h": 12}]
    flat = Image.alpha_composite(base, Ed._redaction_boxes_layer(base.size, boxes))
    # Every pixel is black — the red is unrecoverable.
    colors = flat.getcolors()
    assert colors == [(144, (0, 0, 0, 255))]
