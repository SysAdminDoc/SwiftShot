"""SwiftShot diagnostics bundle.

Collects logs, configuration, and a versions manifest into a single zip the
user can attach to a bug report. Entirely local — no network, no telemetry.
"""

import os
import re
import sys
import glob
import json
import zipfile
import platform
import sqlite3
from datetime import datetime


# Keys whose values are stripped defensively before the config is bundled.
# SwiftShot's config has no secrets today, but this future-proofs the bundle.
_SECRET_KEY_RE = re.compile(r"(token|secret|password|passwd|api[_-]?key)", re.I)


def _config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "SwiftShot")


def _app_version():
    try:
        from config import Config
        return Config.APP_VERSION
    except Exception:
        return "unknown"


def _wgc_available():
    """Whether a Windows Graphics Capture backend package is importable."""
    for mod in ("windows_capture", "winrt.windows.graphics.capture"):
        try:
            __import__(mod)
            return True
        except Exception:
            continue
    return False


def collect_versions():
    """Return a dict of runtime versions for the manifest."""
    info = {
        "swiftshot": _app_version(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "frozen": bool(getattr(sys, "frozen", False)),
        "windows_graphics_capture": _wgc_available(),
    }
    try:
        from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        info["qt"] = QT_VERSION_STR
        info["pyqt5"] = PYQT_VERSION_STR
    except Exception:
        pass
    try:
        import PIL
        info["pillow"] = PIL.__version__
    except Exception:
        pass
    try:
        import numpy
        info["numpy"] = numpy.__version__
    except Exception:
        pass
    return info


def _redact_config(text):
    """Return the config text with any secret-looking value blanked out.

    Falls back to the raw text if it isn't valid JSON (still useful for a bug
    report) — but that path can't contain secrets in practice."""
    try:
        data = json.loads(text)
    except Exception:
        return text
    if isinstance(data, dict):
        for key in list(data):
            if _SECRET_KEY_RE.search(str(key)):
                data[key] = "***redacted***"
    return json.dumps(data, indent=2)


def build_diagnostics_zip(dest_path=None, config_dir=None):
    """Write a diagnostics zip and return its path.

    Bundles: swiftshot.log (+ rotated backups), crash.log, swiftshot.json and
    the editor's config.json (secrets stripped), and versions.json.
    """
    cfg_dir = config_dir or _config_dir()
    if dest_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(cfg_dir, f"swiftshot-diagnostics-{stamp}.zip")

    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Rotating logs (swiftshot.log, .log.1, .log.2, ...) and the crash log.
        for logf in sorted(glob.glob(os.path.join(cfg_dir, "swiftshot.log*"))):
            try:
                zf.write(logf, os.path.basename(logf))
            except OSError:
                pass
        crash = os.path.join(cfg_dir, "crash.log")
        if os.path.exists(crash):
            try:
                zf.write(crash, "crash.log")
            except OSError:
                pass
        # Config files (redacted).
        for name in ("swiftshot.json", "config.json"):
            p = os.path.join(cfg_dir, name)
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        zf.writestr(name, _redact_config(f.read()))
                except OSError:
                    pass
        zf.writestr("versions.json", json.dumps(collect_versions(), indent=2))
    return dest_path
