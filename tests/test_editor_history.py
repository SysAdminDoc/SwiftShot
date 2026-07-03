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
