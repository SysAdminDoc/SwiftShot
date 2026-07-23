"""Keyboard-complete exact-size / aspect-locked region capture (R-22).

Exercises the pure geometry helpers directly and the selection-mutation
helpers via a lightweight stub (no full RegionSelector window needed).
"""

from PyQt5.QtCore import QPoint


def _cls():
    from overlay import RegionSelector
    return RegionSelector


# ── _fit_to_ratio ──────────────────────────────────────────────────────────

def test_fit_to_ratio_16_9(qapp):
    RS = _cls()
    assert RS._fit_to_ratio(1600, 500, 16 / 9) == (1600, 900)


def test_fit_to_ratio_square(qapp):
    RS = _cls()
    assert RS._fit_to_ratio(300, 50, 1.0) == (300, 300)


def test_fit_to_ratio_free_passthrough(qapp):
    RS = _cls()
    assert RS._fit_to_ratio(123, 45, None) == (123, 45)
    assert RS._fit_to_ratio(123, 45, 0) == (123, 45)


# ── _clamp_rect ────────────────────────────────────────────────────────────

def test_clamp_rect_shrinks_to_bounds(qapp):
    RS = _cls()
    # Origin (90,90), size 50x50 on a 100x100 surface -> width/height clamp.
    assert RS._clamp_rect(90, 90, 50, 50, 100, 100) == (90, 90, 10, 10)


def test_clamp_rect_negative_origin(qapp):
    RS = _cls()
    assert RS._clamp_rect(-20, -20, 30, 30, 100, 100) == (0, 0, 30, 30)


def test_clamp_rect_minimum_one_pixel(qapp):
    RS = _cls()
    x, y, w, h = RS._clamp_rect(99, 99, 1, 1, 100, 100)
    assert w >= 1 and h >= 1


# ── _translate_rect ────────────────────────────────────────────────────────

def test_translate_rect_moves_without_resize(qapp):
    RS = _cls()
    assert RS._translate_rect(10, 10, 20, 20, 5, -5, 100, 100) == (15, 5, 20, 20)


def test_translate_rect_stops_at_edge(qapp):
    RS = _cls()
    # Pushing right past the edge parks it flush, size unchanged.
    assert RS._translate_rect(80, 80, 20, 20, 50, 50, 100, 100) == (80, 80, 20, 20)


# ── _parse_dimensions ──────────────────────────────────────────────────────

def test_parse_dimensions_variants(qapp):
    RS = _cls()
    assert RS._parse_dimensions("1920x1080") == (1920, 1080)
    assert RS._parse_dimensions("800 600") == (800, 600)
    assert RS._parse_dimensions(" 640 , 480 ") == (640, 480)
    assert RS._parse_dimensions("1024×768") == (1024, 768)


def test_parse_dimensions_rejects_garbage(qapp):
    RS = _cls()
    assert RS._parse_dimensions("not a size") is None
    assert RS._parse_dimensions("0x100") is None
    assert RS._parse_dimensions("") is None
    assert RS._parse_dimensions(None) is None


# ── selection-mutation helpers via a stub ──────────────────────────────────

def _stub(qapp, w=200, h=100):
    RS = _cls()

    class _S:
        ASPECT_PRESETS = RS.ASPECT_PRESETS
        MODE_RECTANGLE = RS.MODE_RECTANGLE
        _fit_to_ratio = staticmethod(RS._fit_to_ratio)
        _clamp_rect = staticmethod(RS._clamp_rect)
        _current_rect = RS._current_rect
        _set_selection_rect = RS._set_selection_rect
        _cycle_aspect = RS._cycle_aspect

        def width(self): return w
        def height(self): return h
        def update(self): self._updated = True
        def setAccessibleDescription(self, _t): self._desc = _t

    s = _S()
    s.mode = RS.MODE_RECTANGLE
    s._aspect_index = 0
    s.aspect_ratio = None
    s.selecting = False
    s.start_pos = QPoint(0, 0)
    s.end_pos = QPoint(0, 0)
    s.current_pos = QPoint(0, 0)
    return s


def test_set_selection_rect_clamps_and_sets_points(qapp):
    s = _stub(qapp)
    s._set_selection_rect(180, 90, 50, 50)   # overflow the 200x100 surface
    assert s.selecting is True
    r = s._current_rect()
    assert r.right() <= 200 and r.bottom() <= 100
    assert r.x() == 180 and r.y() == 90


def test_cycle_aspect_locks_ratio_and_refits(qapp):
    s = _stub(qapp)
    s._set_selection_rect(0, 0, 80, 40)      # start free-form (fits 200x100)
    # Advance to the first non-free preset (1:1).
    s._cycle_aspect()
    assert s.aspect_ratio == 1.0
    r = s._current_rect()
    assert r.width() == r.height() == 80     # square enforced, within bounds


def test_cycle_aspect_wraps_back_to_free(qapp):
    s = _stub(qapp)
    for _ in range(len(s.ASPECT_PRESETS)):
        s._cycle_aspect()
    assert s.aspect_ratio is None            # full cycle returns to Free
