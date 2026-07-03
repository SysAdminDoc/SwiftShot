"""Regression tests for editor undo snapshots and numpy image helpers."""

import numpy as np
from PIL import Image


def _make_layer_with_mask_and_fx():
    from editor import Layer

    layer = Layer("Annotated", 10, 10)
    layer.mask = Image.new("L", (10, 10), 128)
    layer.mask_enabled = True
    layer.effects = [{"type": "drop_shadow", "blur": 8}]
    return layer


def test_history_snapshot_preserves_masks_effects_and_names(qapp):
    """Undo used to strip masks, effects and groups from layers
    (regression: one undo permanently corrupted masked documents)."""
    from editor import HistoryManager

    layer = _make_layer_with_mask_and_fx()
    mgr = HistoryManager()
    (state, idx) = mgr._snap([layer], 0)

    snap = state[0]
    assert snap.name == "Annotated"          # not "Annotated copy"
    assert snap.mask is not None
    assert snap.mask.getpixel((0, 0)) == 128
    assert snap.effects == [{"type": "drop_shadow", "blur": 8}]
    assert snap.mask is not layer.mask       # deep copy, not alias


def test_history_snapshot_preserves_group_children(qapp):
    from editor import HistoryManager, Layer, LayerGroup

    group = LayerGroup("Group", 10, 10)
    group.children.append(Layer("Child A", 10, 10))
    group.children.append(Layer("Child B", 10, 10))

    (state, _) = HistoryManager()._snap([group], 0)
    snap = state[0]

    assert isinstance(snap, LayerGroup)
    assert [c.name for c in snap.children] == ["Child A", "Child B"]


def test_history_on_change_fires_for_mutations(qapp):
    from editor import HistoryManager, Layer

    calls = []
    mgr = HistoryManager()
    mgr.on_change = lambda: calls.append(1)
    layers = [Layer("L", 4, 4)]

    mgr.save_state(layers, 0, "Edit")
    assert calls == [1]
    mgr.undo(layers, 0)
    assert calls == [1, 1]


def test_np_sobel_detects_vertical_edge(qapp):
    from editor import np_sobel

    arr = np.zeros((6, 6), dtype=np.float32)
    arr[:, 3:] = 255.0
    dx = np_sobel(arr, axis=1)
    dy = np_sobel(arr, axis=0)

    assert np.abs(dx[3, 2:4]).max() > 0     # strong horizontal derivative
    assert np.abs(dy).max() == 0            # no vertical change


class _StubEditor:
    layers = []
    current_tool = None


def _make_canvas():
    from editor import CanvasWidget

    canvas = CanvasWidget(_StubEditor())
    canvas.resize(400, 300)
    return canvas


def test_coordinate_mapping_round_trips_without_rotation(qapp):
    from PyQt5.QtCore import QPointF

    canvas = _make_canvas()
    canvas.zoom = 2.0
    canvas.pan_offset = QPointF(37, -12)
    p = QPointF(123.0, 45.0)

    back = canvas.canvas_to_image(canvas.image_to_canvas(p))
    assert abs(back.x() - p.x()) < 1e-6
    assert abs(back.y() - p.y()) < 1e-6


def test_coordinate_mapping_round_trips_under_view_rotation(qapp):
    """Rotate View used to break mouse-to-image mapping: canvas_to_image
    inverted only pan+zoom, so every click landed at the wrong image
    position once the view was rotated (regression)."""
    from PyQt5.QtCore import QPointF

    canvas = _make_canvas()
    canvas.zoom = 1.5
    canvas.pan_offset = QPointF(20, 40)
    canvas.canvas_angle = 37.0

    for p in (QPointF(0, 0), QPointF(100, 60), QPointF(250.5, 199.25)):
        canvas_pt = canvas.image_to_canvas(p)
        back = canvas.canvas_to_image(canvas_pt)
        assert abs(back.x() - p.x()) < 1e-3
        assert abs(back.y() - p.y()) < 1e-3

    # A rotated view must actually move the projected point off the
    # pan+zoom-only prediction (otherwise rotation is being ignored).
    naive = QPointF(100 * 1.5 + 20, 60 * 1.5 + 40)
    rotated = canvas.image_to_canvas(QPointF(100, 60))
    assert (abs(rotated.x() - naive.x()) + abs(rotated.y() - naive.y())) > 1.0


def test_stamp_over_composites_translucent_paint(qapp):
    """Semi-transparent paint must blend OVER the layer and keep it opaque,
    not replace pixels with a translucency hole (regression)."""
    from editor import CanvasWidget
    from PIL import Image

    dest = Image.new("RGBA", (4, 4), (0, 0, 255, 255))   # opaque blue
    stamp = Image.new("RGBA", (4, 4), (255, 0, 0, 128))  # 50% red

    CanvasWidget._stamp_over(dest, stamp, 0, 0)
    r, g, b, a = dest.getpixel((1, 1))

    assert a == 255                 # layer stays opaque (no hole punched)
    assert r > 100 and b > 100      # blended toward purple, not pure red
    assert g < 20


def test_stamp_over_out_of_bounds_is_noop(qapp):
    from editor import CanvasWidget
    from PIL import Image

    dest = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    stamp = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
    CanvasWidget._stamp_over(dest, stamp, 100, 100)   # fully outside
    assert dest.getpixel((0, 0)) == (0, 0, 0, 255)


def test_np_map_bilinear_identity_and_interpolation(qapp):
    from editor import np_map_bilinear

    chan = np.array([[0.0, 10.0], [20.0, 30.0]], dtype=np.float32)
    sy, sx = np.mgrid[0:2, 0:2].astype(np.float32)
    identity = np_map_bilinear(chan, sy, sx)
    assert np.allclose(identity, chan)

    mid = np_map_bilinear(
        chan, np.array([[0.5]], dtype=np.float32),
        np.array([[0.5]], dtype=np.float32))
    assert np.isclose(mid[0, 0], 15.0)
