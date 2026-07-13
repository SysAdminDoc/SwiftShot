"""SwiftShot headless CLI — scriptable capture without the tray GUI.

    swiftshot --region X,Y,W,H --out shot.png
    swiftshot --fullscreen --out shot.png
    swiftshot --monitor 1 --out shot.png
    swiftshot --region X,Y,W,H --ocr          # prints recognized text to stdout

Coordinates are virtual-desktop physical pixels (the process is per-monitor
DPI-aware). With no capture flags SwiftShot launches its tray application, so
existing shortcuts and the file-association path are unaffected.
"""

import os
import sys
import argparse

# Flags that mean "run headless"; anything else (bare image path, --minimized)
# falls through to the GUI.
_CLI_FLAGS = {"--region", "--fullscreen", "--monitor", "--ocr", "--out",
              "-h", "--help"}

# Holds the QApplication so its Python wrapper is not garbage-collected before
# process exit (a collected wrapper fast-fails the interpreter on teardown).
_qapp = None


def is_cli_invocation(argv):
    return any(a.split("=", 1)[0] in _CLI_FLAGS for a in argv)


def _build_parser():
    p = argparse.ArgumentParser(
        prog="swiftshot",
        description="SwiftShot scriptable capture. With no capture flags, "
                    "SwiftShot launches its tray application.")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--region", metavar="X,Y,W,H",
                     help="Capture a screen region (virtual-desktop pixels).")
    src.add_argument("--fullscreen", action="store_true",
                     help="Capture the entire virtual desktop.")
    src.add_argument("--monitor", type=int, metavar="N",
                     help="Capture monitor N (0-based).")
    p.add_argument("--out", metavar="FILE",
                   help="Write the capture to FILE (format from extension).")
    p.add_argument("--ocr", action="store_true",
                   help="Run OCR on the capture and print the text to stdout.")
    return p


def _parse_region(parser, spec):
    parts = spec.split(",")
    if len(parts) != 4:
        parser.error("--region must be X,Y,W,H")
    try:
        x, y, w, h = (int(v) for v in parts)
    except ValueError:
        parser.error("--region values must be integers")
    if w <= 0 or h <= 0:
        parser.error("--region width and height must be positive")
    return x, y, w, h


def _capture(args, parser):
    from capture import CaptureManager
    if args.fullscreen:
        return CaptureManager.capture_fullscreen()
    if args.monitor is not None:
        from PyQt5.QtWidgets import QApplication
        count = len(QApplication.screens())
        if not (0 <= args.monitor < count):
            parser.error(
                f"--monitor {args.monitor} is out of range "
                f"(found {count} monitor(s): valid 0-{count - 1})")
        return CaptureManager.capture_monitor(args.monitor)
    from PyQt5.QtCore import QRect
    x, y, w, h = _parse_region(parser, args.region)
    full = CaptureManager.capture_fullscreen()
    if full is None:
        return None
    return CaptureManager.crop_image(full, QRect(x, y, w, h))


def run(argv):
    """Handle a CLI capture command. Returns an exit code, or None to fall
    through to the GUI tray app when argv is not a CLI invocation."""
    if not is_cli_invocation(argv):
        return None

    parser = _build_parser()
    args = parser.parse_args(argv)

    if not (args.region or args.fullscreen or args.monitor is not None):
        parser.error("choose a capture source: --region, --fullscreen or --monitor")
    if not args.out and not args.ocr:
        parser.error("nothing to do: pass --out FILE and/or --ocr")

    from PyQt5.QtWidgets import QApplication
    # Keep the reference: a garbage-collected QApplication wrapper crashes the
    # interpreter (fast-fail 0xC0000409) during teardown on sys.exit.
    global _qapp
    _qapp = QApplication.instance() or QApplication(sys.argv[:1])

    pixmap = _capture(args, parser)
    if pixmap is None or pixmap.isNull():
        print("swiftshot: capture failed", file=sys.stderr)
        return 1

    exit_code = 0
    if args.out:
        from utils import save_pixmap
        ext = os.path.splitext(args.out)[1].lstrip(".").lower() or "png"
        if save_pixmap(pixmap, args.out, ext):
            print(args.out)
        else:
            print(f"swiftshot: could not write {args.out}", file=sys.stderr)
            exit_code = 1
    if args.ocr:
        try:
            from ocr import ocr_pixmap
            text = ocr_pixmap(pixmap)
            sys.stdout.write(text if text.endswith("\n") else text + "\n")
        except Exception as e:
            print(f"swiftshot: OCR failed: {e}", file=sys.stderr)
            exit_code = 1
    return exit_code
