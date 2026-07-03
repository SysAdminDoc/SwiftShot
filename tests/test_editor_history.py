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


class _AlignEditor:
    """Minimal editor stand-in for exercising AlignPanel._align."""

    def __init__(self, layer):
        from editor import HistoryManager

        self.layers = [layer]
        self.active_layer_index = 0
        self.history = HistoryManager()
        self.saves = []
        self.history.save_state = lambda *a, **k: self.saves.append(a)

        class _Canvas:
            def update(self_inner): pass
        self.canvas = _Canvas()

    def active_layer(self):
        return self.layers[0]


def _content_bbox_after_align(action):
    from editor import AlignPanel, Layer
    from PIL import ImageDraw

    layer = Layer("L", 100, 100)
    # Put a 10x10 opaque red blob in the top-left quadrant.
    ImageDraw.Draw(layer.image).rectangle((10, 10, 19, 19), fill=(255, 0, 0, 255))
    editor = _AlignEditor(layer)
    panel = AlignPanel(editor)
    panel._align(action)
    return editor, editor.layers[0].image.getbbox()


def test_align_moves_content_not_the_canvas_bitmap(qapp):
    """Align used to be a no-op (layers are canvas-sized) that still pushed
    an undo entry. It must move the content bbox to the canvas edge/center."""
    editor, bbox = _content_bbox_after_align("right")
    assert bbox is not None
    assert bbox[2] == 100          # content right edge now at canvas right
    assert bbox[0] == 90           # 10px-wide blob flush right
    assert len(editor.saves) == 1  # a real move recorded one undo entry

    editor2, bbox2 = _content_bbox_after_align("bottom")
    assert bbox2[3] == 100
    assert bbox2[1] == 90


def test_align_already_aligned_pushes_no_undo(qapp):
    editor, _ = _content_bbox_after_align("left")
    # Blob already starts at x=10; align-left moves it to x=0 (a real move),
    # so aligning left AGAIN must be a no-op with no new undo entry.
    before = len(editor.saves)
    from editor import AlignPanel
    AlignPanel(editor)._align("left")
    assert len(editor.saves) == before


def test_expand_canvas_grows_groups_and_selection_mask(qapp):
    """Off-canvas stroke expansion skipped LayerGroups (image setter is a
    no-op) and left the selection mask at the old size, so later composite/
    paste ops misaligned or raised (regression)."""
    from editor import CanvasWidget, Layer, LayerGroup
    from PIL import Image

    base = Layer("Base", 100, 100)
    group = LayerGroup("G", 100, 100)
    group.children.append(Layer("Child", 100, 100))

    class Ed:
        current_tool = "brush"
        off_canvas_paint = True
        brush_size = 10

        def active_layer(self_inner):
            return base

    ed = Ed()
    ed.layers = [base, group]
    ed.active_layer_index = 0

    canvas = CanvasWidget(ed)
    canvas.set_selection_mask(Image.new("L", (100, 100), 255))

    canvas._expand_canvas_for_stroke(130, 40)   # paint well past the right edge

    new_w, new_h = base.image.size
    assert new_w > 100                                   # base grew
    assert (group._w, group._h) == (new_w, new_h)        # group dims grew
    assert group.children[0].image.size == (new_w, new_h)  # child grew
    assert group.image.size == (new_w, new_h)            # composites cleanly
    assert canvas.selection_mask.size == (new_w, new_h)  # selection resized


def test_soft_brush_stamp_has_radial_falloff(qapp):
    """Vectorized soft-brush stamp must keep the radial alpha falloff:
    opaque at the centre, transparent at the corner."""
    canvas = _make_canvas()
    canvas.editor.brush_hardness = 0          # fully soft
    stamp = canvas._make_brush_stamp(20, (255, 0, 0, 255))

    assert stamp.getpixel((10, 10))[3] == 255   # centre opaque
    assert stamp.getpixel((0, 0))[3] == 0       # corner (outside disc) clear
    mid = stamp.getpixel((14, 10))[3]
    assert 0 < mid < 255                        # falloff in between


def test_retouch_dodge_brightens_center(qapp):
    """Vectorized dodge must still brighten pixels under the brush."""
    from editor import CanvasWidget, Layer
    from PIL import ImageDraw

    layer = Layer("L", 40, 40)
    ImageDraw.Draw(layer.image).rectangle((0, 0, 39, 39), fill=(100, 100, 100, 255))

    class Ed:
        current_tool = "dodge"
        brush_size = 20
        retouch_exposure = 100

        def active_layer(self_inner):
            return layer

    ed = Ed()
    ed.layers = [layer]
    ed.active_layer_index = 0
    canvas = CanvasWidget(ed)
    canvas.last_pos = None

    before = layer.image.getpixel((20, 20))[0]
    canvas._draw_retouch("dodge", 20, 20)
    after = layer.image.getpixel((20, 20))[0]
    assert after > before
    # A pixel far outside the brush disc is untouched.
    assert layer.image.getpixel((0, 0))[0] == 100


def test_clone_stamp_near_border_paints_no_holes(qapp):
    """Cloning from a source near the image edge used to sample crop() padding
    (transparent black), punching holes at the destination (regression)."""
    from editor import CanvasWidget, Layer
    from PIL import ImageDraw

    layer = Layer("L", 40, 40)
    ImageDraw.Draw(layer.image).rectangle((0, 0, 39, 39), fill=(50, 100, 150, 255))

    class Ed:
        clone_source = (2, 2)   # top-left corner — source box runs off-image
        brush_size = 10

        def active_layer(self_inner):
            return layer

    ed = Ed()
    ed.layers = [layer]
    ed.active_layer_index = 0
    canvas = CanvasWidget(ed)
    canvas.last_pos = None

    canvas._draw_clone_stamp(20, 20)
    for py in range(15, 26):
        for px in range(15, 26):
            assert layer.image.getpixel((px, py))[3] == 255   # no transparent holes


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
