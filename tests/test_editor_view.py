"""Rotated-view interaction correctness (AB-07): pan and zoom-to-cursor must
work when the canvas view is rotated."""

from PyQt5.QtCore import QPointF


def _canvas(qapp, angle):
    import editor
    ed = editor.ImageEditor()
    c = ed.canvas
    c.resize(400, 300)
    c.canvas_angle = angle
    c.zoom = 1.5
    c.pan_offset = QPointF(40, 20)
    return ed, c


def test_zoom_to_cursor_stable_under_rotation(qapp):
    ed, c = _canvas(qapp, 30.0)
    try:
        cp = QPointF(140, 110)
        p_img = c.canvas_to_image(cp)         # image point under the cursor
        old_zoom = c.zoom
        c.zoom = old_zoom * 1.15
        dz = old_zoom - c.zoom
        c.pan_offset = QPointF(c.pan_offset.x() + dz * p_img.x(),
                               c.pan_offset.y() + dz * p_img.y())
        mapped = c.image_to_canvas(p_img)      # should still be under the cursor
        assert abs(mapped.x() - cp.x()) < 1.0
        assert abs(mapped.y() - cp.y()) < 1.0
    finally:
        ed.close()


def test_pan_follows_cursor_under_rotation(qapp):
    ed, c = _canvas(qapp, 30.0)
    try:
        mouse0 = QPointF(120, 100)
        p_img = c.canvas_to_image(mouse0)
        c._pan_mouse0 = QPointF(mouse0)
        c._pan_offset0 = QPointF(c.pan_offset)
        mouse1 = QPointF(170, 135)             # drag
        c.pan_offset = c._pan_offset0 + c._unrotate_delta(mouse1 - mouse0)
        mapped = c.image_to_canvas(p_img)      # content followed the cursor
        assert abs(mapped.x() - mouse1.x()) < 1.0
        assert abs(mapped.y() - mouse1.y()) < 1.0
    finally:
        ed.close()
