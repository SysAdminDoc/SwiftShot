"""Coverage for previously-untested modules: the editor compositor
(get_composite blend/opacity/mask) and pin_window scaling (R-04)."""

import pytest
from PIL import Image
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtWidgets import QApplication


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
    ed.invalidate_composite()
    return ed


def test_get_composite_caches_and_invalidates(qapp):
    import editor
    base = editor.Layer("base", 4, 4)
    base.image = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    top = editor.Layer("top", 4, 4)
    top.image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    top.visible = False

    ed = _editor_with([base, top])
    try:
        c1 = ed.get_composite()
        assert ed.get_composite() is c1          # repeated call → cache hit
        # A change without invalidating must not leak (still cached)...
        top.visible = True
        assert ed.get_composite() is c1
        # ...but invalidating recomputes and reflects the change.
        ed.invalidate_composite()
        c2 = ed.get_composite()
        assert c2 is not c1
        assert c2.getpixel((0, 0))[:3] == (255, 0, 0)   # red layer now visible

        # A history op (save_state fires on_change → _mark_dirty → invalidate)
        # must also drop the cache so a subsequent pixel edit is reflected.
        ed.history.save_state(ed.layers, ed.active_layer_index, "Edit")
        base.image.putpixel((0, 0), (0, 0, 255, 255))
        top.visible = False
        ed.invalidate_composite()   # visibility change (panel path)
        c3 = ed.get_composite()
        assert c3.getpixel((0, 0))[:3] == (0, 0, 255)   # blue base now shows
    finally:
        ed._dirty = False       # skip the unsaved-changes prompt on close
        ed.close()


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


def test_pin_window_clamps_render_size_to_memory_budget(
        qapp, fresh_config, monkeypatch):
    import pin_window

    monkeypatch.setattr(pin_window, "MAX_PIN_RENDER_PIXELS", 10_000)
    pixmap = _solid_pixmap(200, 200, (10, 20, 30, 255))
    pin = pin_window.PinWindow(pixmap)
    try:
        assert pin._pixmap.width() * pin._pixmap.height() <= 10_000
        pin._set_scale(5.0)
        assert pin._scale == pin._max_scale
        assert pin._pixmap.width() * pin._pixmap.height() <= 10_000
    finally:
        pin.close()


def test_ocr_dialog_reports_clipboard_state_after_edits(qapp):
    from ocr_dialog import OcrResultDialog

    dialog = OcrResultDialog("original text")
    try:
        assert QApplication.clipboard().text() == "original text"
        assert "automatically" in dialog.status_label.text()

        dialog.text_edit.setPlainText("edited text")
        assert "has not been copied" in dialog.status_label.text()
        dialog._copy()

        assert QApplication.clipboard().text() == "edited text"
        assert "current text" in dialog.status_label.text()
    finally:
        dialog.close()


def test_editor_state_json_is_bounded_and_atomic(tmp_path, monkeypatch):
    import editor
    import utils

    path = tmp_path / "recent.json"
    editor._save_editor_json(str(path), {"recent": ["C:/one.png"]})
    assert editor._load_editor_json(str(path)) == {"recent": ["C:/one.png"]}

    path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        utils.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )
    with pytest.raises(OSError):
        editor._save_editor_json(str(path), {"recent": []})
    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".recent.json.*.tmp")) == []

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (editor.EDITOR_STATE_MAX_BYTES + 1))
    with pytest.raises(ValueError, match="safety limit"):
        editor._load_editor_json(str(oversized))


def test_invalid_editor_ui_scale_falls_back_and_valid_values_are_clamped(
        qapp, monkeypatch):
    import editor

    monkeypatch.setattr(editor, "_dpi", lambda: 96.0)
    monkeypatch.setattr(editor, "_screen_w", lambda: 1920)

    assert editor.init_ui_scale(force="not-a-number") == 1.0
    assert editor.init_ui_scale(force=100) == 3.0
    assert editor.init_ui_scale(force=0.1) == 0.75


def test_standalone_editor_image_loader_uses_bounded_decoder(qapp, tmp_path):
    import editor

    valid = tmp_path / "valid.png"
    _solid_pixmap(12, 8, (1, 2, 3, 255)).save(str(valid), "PNG")
    loaded = editor.load_pixmap_safely(str(valid))
    assert loaded.width() == 12 and loaded.height() == 8

    invalid = tmp_path / "invalid.png"
    invalid.write_bytes(b"not an image")
    with pytest.raises(ValueError):
        editor.load_pixmap_safely(str(invalid))
