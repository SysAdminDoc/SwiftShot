"""Verify SwiftShot's version string is consistent everywhere (R-27).

Compares ``App/config.py``'s ``APP_VERSION`` against the winget manifests, the
Scoop manifest, and the README version badge. Exits non-zero and lists every
mismatch. Importable (``collect_versions``) so tests can assert the same.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def app_version():
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']',
                  (ROOT / "App" / "config.py").read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("Could not find APP_VERSION in App/config.py")
    return m.group(1)


def _winget_versions():
    out = {}
    wdir = ROOT / "packaging" / "winget"
    for f in sorted(wdir.glob("*.yaml")):
        m = re.search(r"^PackageVersion:\s*(.+?)\s*$",
                      f.read_text(encoding="utf-8"), re.M)
        if m:
            out[f"winget/{f.name}"] = m.group(1)
    return out


def _scoop_version():
    p = ROOT / "packaging" / "scoop" / "swiftshot.json"
    return {"scoop/swiftshot.json": json.loads(p.read_text(encoding="utf-8"))["version"]}


def _readme_badge_version():
    txt = (ROOT / "README.md").read_text(encoding="utf-8")
    # shields.io version badge: Version-X.Y.Z-<color>
    m = re.search(r"[Vv]ersion-([0-9][^-\s)]*)-", txt)
    return {"README.md badge": m.group(1)} if m else {}


def collect_versions():
    """Return {source: version} for every place a version string lives."""
    found = {"App/config.py": app_version()}
    found.update(_winget_versions())
    found.update(_scoop_version())
    found.update(_readme_badge_version())
    return found


def find_mismatches():
    versions = collect_versions()
    expected = versions["App/config.py"]
    return {src: v for src, v in versions.items() if v != expected}, expected


def main():
    mismatches, expected = find_mismatches()
    if mismatches:
        print(f"Version mismatch (expected {expected} from App/config.py):",
              file=sys.stderr)
        for src, v in mismatches.items():
            print(f"  {src}: {v}", file=sys.stderr)
        return 1
    print(f"All version strings match: {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
