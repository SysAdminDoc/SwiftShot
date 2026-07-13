"""Coverage for previously-untested modules: the editor compositor
(get_composite blend/opacity/mask) and pin_window scaling (R-04)."""

from PIL import Image
from PyQt5.QtGui import QColor, QImage, QPixmap


def _solid_pixmap(w, h, color):
    img = QImage(w, h, QImage.Format_RGBA8888)
    img.fill(QColor(*color))
    return QPixmap.fromImage(img)


# ── Editor compositor ──────────────────────────────────────────────────────

def _editor_with(layers):
    import editor
    ed = editor.ImageEditor()
    ed.layers = layers
    ed.active_layer_index = len(layers) - 1
    return ed


def test_get_composite_blends_layer_opacity(qapp):
    import editor
    base = editor.Layer("base", 4, 4)
    base.image = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    top = editor.Layer("top", 4, 4)
    top.image = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
    top.opacity = 128

    ed = _editor_with([base, top])
    try:
        px = ed.get_composite().getpixel((0, 0))
        assert 100 < px[0] < 156      # ~50% white over black
    finally:
        ed.close()


def test_get_composite_skips_hidden_layer(qapp):
    import editor
    base = editor.Layer("base", 4, 4)
    base.image = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    top = editor.Layer("top", 4, 4)
    top.image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    top.visible = False

    ed = _editor_with([base, top])
    try:
        px = ed.get_composite().getpixel((0, 0))
        assert px[:3] == (0, 0, 0)     # hidden red layer contributes nothing
    finally:
        ed.close()


def test_get_composite_applies_layer_mask(qapp):
    import editor
    base = editor.Layer("base", 4, 4)
    base.image = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    top = editor.Layer("top", 4, 4)
    top.image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    top.mask = Image.new("L", (4, 4), 0)      # fully hidden by mask

    ed = _editor_with([base, top])
    try:
        px = ed.get_composite().getpixel((0, 0))
        assert px[:3] == (0, 0, 0)
    finally:
        ed.close()


# ── Image diff ─────────────────────────────────────────────────────────────

def test_compute_image_diff_identical_is_zero(qapp):
    from editor import compute_image_diff
    a = Image.new("RGBA", (10, 10), (20, 40, 60, 255))
    overlay, pct = compute_image_diff(a, a.copy())
    assert pct == 0.0
    assert overlay.size == (10, 10)


def test_compute_image_diff_highlights_changed_region(qapp):
    from editor import compute_image_diff
    a = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
    b = a.copy()
    for y in range(0, 5):          # change the top half
        for x in range(10):
            b.putpixel((x, y), (255, 255, 255, 255))

    overlay, pct = compute_image_diff(a, b)
    assert abs(pct - 50.0) < 1.0                     # ~half changed
    r, g, bl, al = overlay.getpixel((0, 0))          # changed → red tint
    assert r > 100 and r > g and r > bl and al == 255
    assert overlay.getpixel((0, 9)) == (0, 0, 0, 255)     # unchanged → original


def test_compute_image_diff_resizes_mismatched(qapp):
    from editor import compute_image_diff
    a = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
    b = Image.new("RGBA", (5, 5), (0, 0, 0, 255))
    overlay, pct = compute_image_diff(a, b)          # must not raise
    assert overlay.size == (10, 10)
    assert pct == 0.0


# ── Pin window ─────────────────────────────────────────────────────────────

def test_pin_window_holds_pixmap_and_opacity(qapp, fresh_config):
    from pin_window import PinWindow

    pin = PinWindow(_solid_pixmap(60, 40, (10, 20, 30, 255)))
    try:
        assert 0.0 < pin._opacity <= 1.0
        assert pin._original_pixmap.width() == 60
    finally:
        pin.close()


def test_pin_window_scale_resizes(qapp, fresh_config):
    from pin_window import PinWindow

    pin = PinWindow(_solid_pixmap(60, 40, (10, 20, 30, 255)))
    try:
        pin._scale = 2.0
        pin._update_size()
        # scaled pixmap is ~2x (KeepAspectRatio), widget adds a 4px margin
        assert pin._pixmap.width() == 120
        assert pin.width() == pin._pixmap.width() + 4
    finally:
        pin.close()
