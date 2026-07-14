"""Tests for scrolling-capture stitching, especially the static-footer
auto-ignore (R-05). Stitching is pure image math, so it is testable headless."""

from PyQt5.QtGui import QColor, QImage, QPixmap


def _frame(width, height, footer_h, content_offset):
    """A frame whose bottom `footer_h` rows are a constant footer and whose
    upper rows scroll with `content_offset`."""
    img = QImage(width, height, QImage.Format_RGB32)
    for y in range(height):
        if y >= height - footer_h:
            col = QColor(10, 10, 10)                 # static footer
        else:
            v = ((y + content_offset) * 7) % 256     # scrolling content
            col = QColor(v, (v * 2) % 256, (v * 3) % 256)
        for x in range(width):
            img.setPixelColor(x, y, col)
    return QPixmap.fromImage(img)


def _stub(frames):
    from scrolling_capture import ScrollingCaptureDialog

    class _S:
        _static_bottom_height = ScrollingCaptureDialog._static_bottom_height
        _find_overlap = ScrollingCaptureDialog._find_overlap
        _stitch_frames = ScrollingCaptureDialog._stitch_frames

    s = _S()
    s._frames = frames
    return s


def test_static_bottom_height_detects_fixed_footer(qapp):
    frames = [_frame(40, 100, 20, 0), _frame(40, 100, 20, 30),
              _frame(40, 100, 20, 60)]
    assert _stub(frames)._static_bottom_height() == 20


def test_no_static_footer_when_everything_scrolls(qapp):
    # No constant footer → nothing to trim.
    frames = [_frame(40, 100, 0, 0), _frame(40, 100, 0, 30)]
    assert _stub(frames)._static_bottom_height() == 0


def test_stitch_collapses_footer(qapp):
    frames = [_frame(40, 100, 20, 0), _frame(40, 100, 20, 30)]
    result = _stub(frames)._stitch_frames()
    assert result is not None
    # Taller than one frame (new content added) but far less than 2x (the
    # footer is not duplicated).
    assert 100 < result.height() < 200


def test_reject_invalidates_pending_window_identification(qapp, monkeypatch):
    import scrolling_capture

    dialog = scrolling_capture.ScrollingCaptureDialog()
    dialog.show()
    callbacks = []
    monkeypatch.setattr(scrolling_capture.sys, "platform", "win32")
    monkeypatch.setattr(
        scrolling_capture.QTimer,
        "singleShot",
        lambda _delay, callback: callbacks.append(callback),
    )

    dialog._begin_capture()
    generation = dialog._generation
    assert dialog._awaiting_target
    assert len(callbacks) == 1

    dialog.reject()
    callbacks[0]()

    assert dialog._generation > generation
    assert not dialog._awaiting_target
    assert not dialog._capturing
    assert dialog._target_hwnd is None


def test_stale_capture_frame_never_captures_or_scrolls(qapp, monkeypatch):
    import scrolling_capture

    dialog = scrolling_capture.ScrollingCaptureDialog()
    dialog.show()
    dialog._generation = 8
    dialog._capturing = True
    captures = []
    scrolls = []
    monkeypatch.setattr(
        scrolling_capture.QApplication,
        "primaryScreen",
        lambda: captures.append(True),
    )
    monkeypatch.setattr(dialog, "_scroll_window", lambda *_: scrolls.append(True))

    dialog._capture_frame(7)

    assert captures == []
    assert scrolls == []
    dialog.close()


def test_hidden_capture_dialog_blocks_current_callback(qapp, monkeypatch):
    import scrolling_capture

    dialog = scrolling_capture.ScrollingCaptureDialog()
    dialog.show()
    dialog._generation = 3
    dialog._capturing = True
    dialog.hide()
    captures = []
    monkeypatch.setattr(
        scrolling_capture.QApplication,
        "primaryScreen",
        lambda: captures.append(True),
    )

    dialog._capture_frame(3)

    assert captures == []


def test_cancel_during_finish_prevents_stitch_and_accept(qapp, monkeypatch):
    import scrolling_capture

    dialog = scrolling_capture.ScrollingCaptureDialog()
    dialog.show()
    dialog._generation = 4
    dialog._capturing = True
    dialog._frames = [_frame(20, 40, 0, 0), _frame(20, 40, 0, 10)]
    stitched = []
    monkeypatch.setattr(
        scrolling_capture.QApplication,
        "processEvents",
        dialog.reject,
    )
    monkeypatch.setattr(
        dialog,
        "_stitch_frames",
        lambda: stitched.append(True),
    )

    dialog._finish(4)

    assert stitched == []
    assert dialog.result() == dialog.Rejected


def test_capture_frame_uses_monitor_aware_global_rect(qapp, monkeypatch):
    import capture
    import scrolling_capture
    from PyQt5.QtCore import QRect

    dialog = scrolling_capture.ScrollingCaptureDialog()
    dialog.show()
    dialog._generation = 4
    dialog._capturing = True
    dialog._target_rect = QRect(-800, 50, 120, 90)
    frame = QPixmap(120, 90)
    frame.fill(QColor("navy"))
    captured = []
    callbacks = []
    monkeypatch.setattr(
        capture.CaptureManager,
        "capture_rect",
        lambda rect: captured.append(QRect(rect)) or frame,
    )
    monkeypatch.setattr(
        scrolling_capture.QTimer,
        "singleShot",
        lambda _delay, callback: callbacks.append(callback),
    )
    monkeypatch.setattr(dialog, "_scroll_window", lambda *_args: None)

    dialog._capture_frame(4)

    assert captured == [QRect(-800, 50, 120, 90)]
    assert dialog._frames == [frame]
    assert callbacks
    dialog.close()


def test_capture_frame_stops_before_exceeding_memory_budget(qapp, monkeypatch):
    import capture
    import scrolling_capture
    from PyQt5.QtCore import QRect

    dialog = scrolling_capture.ScrollingCaptureDialog()
    dialog.show()
    dialog._generation = 6
    dialog._capturing = True
    dialog._target_rect = QRect(0, 0, 10, 10)
    existing = QPixmap(10, 10)
    existing.fill(QColor("red"))
    dialog._frames = [existing]
    dialog._raw_pixels = 100
    next_frame = QPixmap(10, 10)
    next_frame.fill(QColor("blue"))
    finished = []
    monkeypatch.setattr(scrolling_capture, "MAX_SCROLL_RAW_PIXELS", 150)
    monkeypatch.setattr(
        capture.CaptureManager, "capture_rect", lambda _rect: next_frame)
    monkeypatch.setattr(dialog, "_finish", lambda generation: finished.append(generation))

    dialog._capture_frame(6)

    assert dialog._frames == [existing]
    assert dialog.was_truncated()
    assert finished == [6]
    dialog.close()
