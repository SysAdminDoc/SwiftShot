"""Regression tests for whole-image geometry ops transforming layer masks and
recursing into groups (AB-03 / AB-04).

Regression: crop/resize/rotate/flip only touched ``layer.image`` and left
``layer.mask`` at the old size, so ``get_composite`` raised 'images do not
match' on the next repaint — the editor became unusable after cropping a masked
document. Groups (whose ``image`` setter is a no-op) kept stale children and
size entirely.
"""

from PIL import Image


def _geo(qapp):
    """Bind the geometry helper to a stub — it only uses self for recursion."""
    from editor import ImageEditor

    class _S:
        _apply_geometry_to_layer = ImageEditor._apply_geometry_to_layer

    return _S()


def test_blend_handles_size_mismatch_without_crashing(qapp):
    """A pasted layer keeps its own dimensions; a non-Normal blend used to
    raise 'images do not match' in ImageChops and crash get_composite."""
    from editor import ImageEditor

    class _S:
        _blend = ImageEditor._blend

    base = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
    for mode in ("Multiply", "Screen", "Overlay", "Difference", "Normal"):
        top = Image.new("RGBA", (20, 15), (255, 255, 255, 255))
        out = _S()._blend(base.copy(), top, mode)
        assert out.size == (10, 10)      # never raises, stays canvas-sized


def test_crop_transforms_layer_mask(qapp):
    from editor import Layer

    layer = Layer("L", 20, 20)
    layer.mask = Image.new("L", (20, 20), 200)

    _geo(qapp)._apply_geometry_to_layer(layer, lambda img: img.crop((0, 0, 10, 10)))

    assert layer.image.size == (10, 10)
    assert layer.mask is not None
    assert layer.mask.size == (10, 10)          # mask followed the image


def test_resize_keeps_image_and_mask_same_size(qapp):
    from editor import Layer

    layer = Layer("L", 20, 20)
    layer.mask = Image.new("L", (20, 20), 128)

    _geo(qapp)._apply_geometry_to_layer(layer, lambda img: img.resize((40, 30)))

    assert layer.image.size == layer.mask.size == (40, 30)


def test_geometry_recurses_into_group_children_and_size(qapp):
    from editor import Layer, LayerGroup

    group = LayerGroup("G", 20, 20)
    child = Layer("Child", 20, 20)
    child.mask = Image.new("L", (20, 20), 90)
    group.children.append(child)
    group.mask = Image.new("L", (20, 20), 255)

    _geo(qapp)._apply_geometry_to_layer(group, lambda img: img.crop((0, 0, 8, 12)))

    assert (group._w, group._h) == (8, 12)      # group tracked the new size
    assert group.children[0].image.size == (8, 12)
    assert group.children[0].mask.size == (8, 12)
    assert group.mask.size == (8, 12)
    # get_composite reads group.image (composites children) — must not raise
    assert group.image.size == (8, 12)


def test_empty_group_size_updates_via_probe(qapp):
    from editor import LayerGroup

    group = LayerGroup("G", 20, 20)     # no children

    _geo(qapp)._apply_geometry_to_layer(group, lambda img: img.resize((5, 6)))

    assert (group._w, group._h) == (5, 6)


def test_pil_to_qimage_is_detached_and_correct_size(qapp):
    """Shared helper must return a QImage that owns its buffer (survives the
    source bytes being dropped) with the right dimensions (R-06)."""
    from editor import pil_to_qimage

    src = Image.new("RGBA", (7, 5), (10, 20, 30, 255))
    qimg = pil_to_qimage(src)
    del src
    assert (qimg.width(), qimg.height()) == (7, 5)
    assert not qimg.isNull()


def test_group_composite_does_not_square_child_alpha(qapp):
    """A 50%-opacity child used to render at 25% because the group composited
    via paste(img, mask=img), multiplying alpha by itself (AB-05)."""
    from editor import Layer, LayerGroup

    group = LayerGroup("G", 4, 4)
    child = Layer("C", 4, 4)
    child.image = Image.new("RGBA", (4, 4), (255, 0, 0, 128))   # 50% alpha
    group.children.append(child)

    composited = group.image
    assert composited.getpixel((0, 0))[3] == 128       # not ~64

