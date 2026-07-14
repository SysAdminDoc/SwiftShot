"""Coverage for capture-surface logic: overlay edge snapping and the window
picker's rectangle animator (R-04)."""

from PyQt5.QtCore import QPoint, QRectF
from pathlib import Path


# ── Overlay edge snapping ──────────────────────────────────────────────────

def _snapper(edges_v, edges_h, enabled=True):
    from overlay import RegionSelector

    class _S:
        SNAP_DISTANCE = RegionSelector.SNAP_DISTANCE
        _snap_point = RegionSelector._snap_point

    s = _S()
    s._snap_enabled = enabled
    s._snap_edges_v = edges_v
    s._snap_edges_h = edges_h
    s._snapped_x = None
    s._snapped_y = None
    return s


def test_snap_point_snaps_to_nearby_edges(qapp):
    s = _snapper(edges_v=[100], edges_h=[200])
    out = s._snap_point(QPoint(104, 197))   # within 8px of both edges
    assert out.x() == 100 and out.y() == 200


def test_snap_point_ignores_far_edges(qapp):
    s = _snapper(edges_v=[100], edges_h=[200])
    out = s._snap_point(QPoint(140, 150))   # too far
    assert out.x() == 140 and out.y() == 150


def test_snap_point_disabled_passthrough(qapp):
    s = _snapper(edges_v=[100], edges_h=[200], enabled=False)
    out = s._snap_point(QPoint(101, 201))
    assert out.x() == 101 and out.y() == 201


# ── Window picker animator ─────────────────────────────────────────────────

def test_quintic_ease_bounds_and_monotonic(qapp):
    from window_picker import RectAnimator
    f = RectAnimator._quintic_ease_out
    assert abs(f(0.0) - 0.0) < 1e-9
    assert abs(f(1.0) - 1.0) < 1e-9
    prev = -1.0
    for i in range(11):
        v = f(i / 10.0)
        assert v >= prev            # monotonically increasing
        prev = v


def test_animate_to_first_call_sets_current_without_animating(qapp):
    from window_picker import RectAnimator
    a = RectAnimator()
    a.animate_to(QRectF(10, 20, 30, 40))
    assert not a.active
    assert a.current_rect == QRectF(10, 20, 30, 40)


def test_tick_completes_to_target(qapp):
    from window_picker import RectAnimator
    a = RectAnimator(duration_ms=100)
    a.animate_to(QRectF(0, 0, 10, 10))       # seed current_rect
    a.animate_to(QRectF(100, 100, 50, 50))   # start animating
    assert a.active
    a.start_time -= 1.0                       # force elapsed > duration
    a.tick()
    assert not a.active
    assert a.current_rect == QRectF(100, 100, 50, 50)


def test_all_transient_capture_windows_opt_out_but_pins_do_not():
    root = Path(__file__).resolve().parents[1] / "App"
    transient_modules = (
        "overlay.py",
        "window_picker.py",
        "monitor_picker.py",
        "countdown_overlay.py",
        "capture_menu.py",
        "scrolling_capture.py",
    )

    for filename in transient_modules:
        source = (root / filename).read_text(encoding="utf-8")
        assert "exclude_window_from_capture" in source, filename

    pin_source = (root / "pin_window.py").read_text(encoding="utf-8")
    assert "exclude_window_from_capture" not in pin_source


def test_cancelled_countdown_rejects_stale_timer_tick(qapp):
    from countdown_overlay import CountdownOverlay

    overlay = CountdownOverlay(5000)
    completed = []
    overlay.countdown_finished.connect(lambda: completed.append(True))
    overlay.start()
    generation = overlay._active_generation
    remaining = overlay._remaining_ms

    overlay._cancel()
    overlay._tick(generation)

    assert completed == []
    assert overlay._remaining_ms == remaining
    assert not overlay._timer.isActive()
    assert not overlay.isVisible()
