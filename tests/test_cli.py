"""Tests for the scriptable CLI (cli.py). The capture path needs a real
screen, so these cover argument routing, region parsing, and the fall-through
to the GUI — the parts that are deterministic headless."""

import pytest
from argparse import Namespace
from PyQt5.QtCore import QRect


def test_non_cli_argv_falls_through_to_gui():
    import cli
    # Bare image path (file association) and the startup flag must NOT be
    # treated as CLI invocations.
    assert cli.run(["C:/some/image.png"]) is None
    assert cli.run(["--minimized"]) is None
    assert cli.run([]) is None


def test_is_cli_invocation_detects_flags():
    import cli
    assert cli.is_cli_invocation(["--fullscreen", "--out", "x.png"])
    assert cli.is_cli_invocation(["--region=0,0,10,10"])
    assert cli.is_cli_invocation(["--ocr"])
    assert not cli.is_cli_invocation(["--minimized"])
    assert not cli.is_cli_invocation(["photo.jpg"])


def test_region_requires_four_values():
    import cli
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        cli._parse_region(parser, "1,2,3")


def test_region_rejects_nonpositive_size():
    import cli
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        cli._parse_region(parser, "0,0,0,10")


def test_region_parses_valid_spec():
    import cli
    parser = cli._build_parser()
    assert cli._parse_region(parser, "5,6,7,8") == (5, 6, 7, 8)


def test_region_capture_preserves_negative_global_desktop_coordinates(
        qapp, monkeypatch):
    import capture
    import cli

    requested = []
    marker = object()
    monkeypatch.setattr(
        capture.CaptureManager,
        "capture_rect",
        lambda rect: requested.append(QRect(rect)) or marker,
    )
    args = Namespace(
        fullscreen=False,
        monitor=None,
        region="-1200,40,800,600",
    )

    assert cli._capture(args, cli._build_parser()) is marker
    assert requested == [QRect(-1200, 40, 800, 600)]


def test_cli_requires_something_to_do():
    import cli
    # A capture source with neither --out nor --ocr is an error.
    with pytest.raises(SystemExit):
        cli.run(["--fullscreen"])


def test_cli_requires_a_source():
    import cli
    with pytest.raises(SystemExit):
        cli.run(["--out", "x.png"])


def test_cli_rejects_out_of_range_monitor(qapp, tmp_path):
    import cli
    out = tmp_path / "shot.png"
    # A monitor index far beyond any real display must error, not silently
    # write a full-desktop image with a success exit.
    with pytest.raises(SystemExit):
        cli.run(["--monitor", "99", "--out", str(out)])
    assert not out.exists()
