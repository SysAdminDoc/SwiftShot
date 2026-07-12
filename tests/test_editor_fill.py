"""Regression test for the vectorized flood fill (AB-29). The old per-pixel
BFS froze the UI on large areas; the rewrite must still fill exactly the
contiguous colour-matched region."""

import numpy as np
from PIL import Image
from PyQt5.QtGui import QColor


def _canvas(qapp, layer, tol=0, opacity=255, fg=(255, 0, 0)):
    from editor import CanvasWidget

    class _Editor:
        def __init__(self):
            self.fg_color = QColor(*fg)
            self.magic_wand_tolerance = tol
            self.brush_opacity = opacity

        def active_layer(self):
            return layer

    class _Canvas:
        _flood_fill = CanvasWidget._flood_fill

        def __init__(self):
            self.editor = _Editor()

    return _Canvas()


def test_flood_fill_fills_whole_solid_layer(qapp):
    from editor import Layer

    layer = Layer("L", 4, 4)
    layer.image = Image.new("RGBA", (4, 4), (0, 0, 0, 255))

    _canvas(qapp, layer)._flood_fill(0, 0)

    arr = np.array(layer.image)
    assert (arr == (255, 0, 0, 255)).all()


def test_content_aware_fill_diffuses_background_into_hole(qapp):
    """Diffusion inpaint should fill a selected hole with the surrounding
    uniform colour (fast, vectorized — AB-29)."""
    from editor import CanvasWidget, Layer

    layer = Layer("L", 24, 24)
    layer.image = Image.new("RGBA", (24, 24), (30, 120, 200, 255))

    class _Editor:
        brush_size = 8

        def active_layer(self):
            return layer

        def _status(self, *a):
            pass

    class _Canvas:
        _content_aware_fill = CanvasWidget._content_aware_fill

        def __init__(self):
            self.editor = _Editor()
            self.selection_mask = Image.new("L", (24, 24), 0)
            # a small central hole to inpaint
            for y in range(9, 15):
                for x in range(9, 15):
                    self.selection_mask.putpixel((x, y), 255)

        def update(self):
            pass

        def set_selection_mask(self, m):
            self.selection_mask = m

        class _H:
            @staticmethod
            def save_state(*a):
                pass
        history = _H()
        # editor.history is used, not canvas.history — patch on editor below

    c = _Canvas()
    c.editor.history = _Canvas._H()
    c.editor.layers = [layer]
    c.editor.active_layer_index = 0
    c._content_aware_fill()

    arr = np.array(layer.image)
    # centre of the former hole should be close to the surrounding colour
    r, g, b, a = arr[12, 12]
    assert abs(int(r) - 30) < 25 and abs(int(g) - 120) < 25 and abs(int(b) - 200) < 25
    assert a == 255


def test_flood_fill_stops_at_color_boundary(qapp):
    from editor import Layer

    layer = Layer("L", 4, 2)
    img = Image.new("RGBA", (4, 2), (0, 0, 0, 255))
    # right half is a different colour → fill from the left must not cross
    for y in range(2):
        for x in range(2, 4):
            img.putpixel((x, y), (255, 255, 255, 255))
    layer.image = img

    _canvas(qapp, layer)._flood_fill(0, 0)

    arr = np.array(layer.image)
    assert (arr[:, 0:2] == (255, 0, 0, 255)).all()      # left filled
    assert (arr[:, 2:4] == (255, 255, 255, 255)).all()  # right untouched
