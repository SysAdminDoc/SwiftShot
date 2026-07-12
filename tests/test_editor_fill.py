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
