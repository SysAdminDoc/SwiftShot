"""Round-trip tests for the .swiftshot project format (v3) and the legacy
v2 loader.

Regression: v2's loader derived a group's canvas size from the *previous*
layer (default 800x600), so a first-in-list or oversized group reloaded at
the wrong size, and group children lost their name/opacity/mask/blend
metadata entirely.
"""

import io
import json
import zipfile

from PIL import Image


def _serializer(qapp):
    """Bind the project-I/O methods to a stub — they only use self for
    recursion, so we avoid constructing the full ImageEditor UI."""
    from editor import ImageEditor

    class _S:
        _serialize_layer = ImageEditor._serialize_layer
        _deserialize_layer = ImageEditor._deserialize_layer
        _load_layers_v2 = ImageEditor._load_layers_v2
        _apply_layer_meta = staticmethod(ImageEditor._apply_layer_meta)

    return _S()


def _sample_layers():
    from editor import Layer, LayerGroup

    child_a = Layer("Sketch", image=Image.new("RGBA", (1200, 900), (255, 0, 0, 255)))
    child_a.opacity = 128
    child_a.blend_mode = "Multiply"
    child_a.mask = Image.new("L", (1200, 900), 64)
    child_b = Layer("Ink", image=Image.new("RGBA", (300, 200), (0, 255, 0, 255)))
    child_b.visible = False

    group = LayerGroup("Big Group", 1200, 900)   # first in list, > 800x600
    group.children = [child_a, child_b]
    group.opacity = 200
    group.mask = Image.new("L", (1200, 900), 255)
    group.effects = [{"type": "drop_shadow", "blur": 4}]

    flat = Layer("Backdrop", image=Image.new("RGBA", (1200, 900), (0, 0, 255, 255)))
    return [group, flat]


def _roundtrip(qapp, layers):
    s = _serializer(qapp)
    buf = io.BytesIO()
    meta = {"magic": "SWIFTSHOT_PROJECT", "version": 3, "active_index": 0, "layers": []}
    with zipfile.ZipFile(buf, "w") as zf:
        for i, layer in enumerate(layers):
            meta["layers"].append(s._serialize_layer(zf, layer, f"layer_{i}"))
        zf.writestr("project.json", json.dumps(meta))
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        names = set(zf.namelist())
        loaded_meta = json.loads(zf.read("project.json"))
        return [s._deserialize_layer(zf, lm, f"layer_{i}", names)
                for i, lm in enumerate(loaded_meta["layers"])]


def test_v3_first_in_list_group_keeps_size(qapp):
    from editor import LayerGroup

    loaded = _roundtrip(qapp, _sample_layers())
    group = loaded[0]
    assert isinstance(group, LayerGroup)
    assert (group._w, group._h) == (1200, 900)   # not the 800x600 default
    assert group.image.size == (1200, 900)


def test_v3_children_keep_metadata_and_masks(qapp):
    loaded = _roundtrip(qapp, _sample_layers())
    a, b = loaded[0].children
    assert a.name == "Sketch"
    assert a.opacity == 128
    assert a.blend_mode == "Multiply"
    assert a.mask is not None and a.mask.getpixel((0, 0)) == 64
    assert b.name == "Ink"
    assert b.visible is False


def test_v3_group_own_mask_and_effects_survive(qapp):
    loaded = _roundtrip(qapp, _sample_layers())
    group = loaded[0]
    assert group.opacity == 200
    assert group.mask is not None
    assert group.effects == [{"type": "drop_shadow", "blur": 4}]


def test_v3_nested_groups_roundtrip(qapp):
    from editor import Layer, LayerGroup

    inner = LayerGroup("Inner", 500, 400)
    inner.children = [Layer("Deep", image=Image.new("RGBA", (500, 400), (9, 9, 9, 255)))]
    outer = LayerGroup("Outer", 1000, 800)
    outer.children = [inner]

    loaded = _roundtrip(qapp, [outer])
    out = loaded[0]
    assert isinstance(out, LayerGroup)
    assert isinstance(out.children[0], LayerGroup)
    assert (out.children[0]._w, out.children[0]._h) == (500, 400)
    assert out.children[0].children[0].name == "Deep"


def test_legacy_v2_group_size_comes_from_composite(qapp):
    """A v2 file whose FIRST layer is a 1000x700 group must reload at
    1000x700, not the 800x600 fallback the old loader produced."""
    from editor import LayerGroup

    s = _serializer(qapp)
    buf = io.BytesIO()
    comp = Image.new("RGBA", (1000, 700), (10, 20, 30, 255))
    child = Image.new("RGBA", (1000, 700), (40, 50, 60, 255))
    gmask = Image.new("L", (1000, 700), 200)
    meta = {"magic": "SWIFTSHOT_PROJECT", "version": 2, "active_index": 0,
            "layers": [{"name": "G", "visible": True, "opacity": 255,
                        "blend_mode": "Normal", "locked": False,
                        "mask_enabled": True, "has_mask": True, "effects": [],
                        "is_group": True, "group_child_count": 1,
                        "group_collapsed": False}]}
    with zipfile.ZipFile(buf, "w") as zf:
        for name, img in (("layer_0.png", comp), ("layer_0_child_0.png", child)):
            b = io.BytesIO(); img.save(b, "PNG"); zf.writestr(name, b.getvalue())
        b = io.BytesIO(); gmask.save(b, "PNG"); zf.writestr("mask_0.png", b.getvalue())
        zf.writestr("project.json", json.dumps(meta))
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        layers = s._load_layers_v2(zf, json.loads(zf.read("project.json")), set(zf.namelist()))

    group = layers[0]
    assert isinstance(group, LayerGroup)
    assert (group._w, group._h) == (1000, 700)
    assert group.mask is not None and group.mask.getpixel((0, 0)) == 200
    assert len(group.children) == 1
