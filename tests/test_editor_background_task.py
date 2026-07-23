"""Background task runner: pure compute, cancellation, worker signalling, and
single-flight coalescing (R-23)."""

import threading

import pytest
from PIL import Image
from PyQt5.QtCore import QThread
from PyQt5.QtTest import QTest


# ── pure compute functions ─────────────────────────────────────────────────

def test_compute_lanczos_upscale_scales(qapp):
    from editor import compute_lanczos_upscale
    out = compute_lanczos_upscale(Image.new("RGBA", (10, 8), (1, 2, 3, 255)), 2)
    assert out.size == (20, 16)


def test_compute_lanczos_upscale_4x(qapp):
    from editor import compute_lanczos_upscale
    out = compute_lanczos_upscale(Image.new("RGBA", (5, 5), (9, 9, 9, 255)), 4)
    assert out.size == (20, 20)


def test_compute_upscale_honours_cancel(qapp):
    from editor import compute_lanczos_upscale, TaskCancelled
    ev = threading.Event(); ev.set()
    with pytest.raises(TaskCancelled):
        compute_lanczos_upscale(Image.new("RGBA", (8, 8)), 4, None, ev)


def test_compute_depth_map_matches_size(qapp):
    from editor import compute_depth_map
    src = Image.new("RGBA", (24, 16), (120, 60, 30, 255))
    out = compute_depth_map(src)
    assert out.size == (24, 16)
    assert out.mode == "RGBA"


def test_compute_busy_regions_returns_layer_and_count(qapp):
    from editor import compute_busy_regions
    import numpy as np
    # High-variance noise -> at least one busy region.
    arr = (np.random.RandomState(0).rand(60, 60, 4) * 255).astype("uint8")
    arr[:, :, 3] = 255
    src = Image.fromarray(arr, "RGBA")
    layer_img, count = compute_busy_regions(src)
    assert layer_img.size == (60, 60)
    assert count >= 1


def test_compute_busy_regions_flat_image_no_regions(qapp):
    from editor import compute_busy_regions
    # A flat image has zero variance -> no busy regions.
    _, count = compute_busy_regions(Image.new("RGBA", (60, 60), (10, 10, 10, 255)))
    assert count == 0


# ── BackgroundWorker signalling via a real thread ───────────────────────────

def _run_worker(compute, cancel):
    from editor import BackgroundWorker
    worker = BackgroundWorker(compute, cancel)
    thread = QThread()
    worker.moveToThread(thread)
    got = {"finished": [], "cancelled": [], "error": []}
    worker.finished.connect(lambda r: got["finished"].append(r))
    worker.cancelled.connect(lambda: got["cancelled"].append(True))
    worker.error.connect(lambda m: got["error"].append(m))
    thread.started.connect(worker.run)
    thread.start()
    for _ in range(100):
        QTest.qWait(10)
        if got["finished"] or got["cancelled"] or got["error"]:
            break
    thread.quit(); thread.wait(2000)
    return got


def test_worker_emits_finished(qapp):
    got = _run_worker(lambda progress, cancel: 7 * 6, threading.Event())
    assert got["finished"] == [42]
    assert got["cancelled"] == [] and got["error"] == []


def test_worker_emits_cancelled_when_event_set(qapp):
    ev = threading.Event(); ev.set()
    got = _run_worker(lambda progress, cancel: 1, ev)
    assert got["cancelled"] == [True]
    assert got["finished"] == []


def test_worker_emits_cancelled_on_taskcancelled(qapp):
    from editor import TaskCancelled

    def boom(progress, cancel):
        raise TaskCancelled()

    got = _run_worker(boom, threading.Event())
    assert got["cancelled"] == [True]
    assert got["error"] == []


def test_worker_emits_error(qapp):
    def boom(progress, cancel):
        raise ValueError("nope")

    got = _run_worker(boom, threading.Event())
    assert got["error"] == ["nope"]
    assert got["finished"] == []


# ── single-flight guard ─────────────────────────────────────────────────────

def test_run_background_coalesces_when_busy(qapp):
    from editor import ImageEditor

    class _S:
        _run_background = ImageEditor._run_background

    s = _S()
    s._task_busy = True
    s._active_task_label = "Upscale 2×"
    msgs = []
    s._status = lambda m: msgs.append(m)
    ran = []
    s._run_background("Depth Map", lambda p, c: ran.append(1), lambda r: None)

    assert ran == []                       # the second op never started
    assert msgs and "still running" in msgs[0]
