"""Generate a CycloneDX 1.5 SBOM for SwiftShot from the hash-pinned lock file.

Part of the deterministic release gate (R-27). Pure/offline: it reads
``requirements.lock`` (name==version + sha256 hashes) and the app version from
``App/config.py``, and writes a CycloneDX JSON document. Deterministic — the
same inputs always produce byte-identical output (no timestamps).

Usage:
    py -3.12 packaging/gen_sbom.py            # writes dist/swiftshot.sbom.json
    py -3.12 packaging/gen_sbom.py -o out.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements.lock"
CONFIG = ROOT / "App" / "config.py"

_REQ_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)\s*\\?\s*$")
_HASH_RE = re.compile(r"--hash=sha256:([0-9a-fA-F]{64})")


def parse_lock(text):
    """Parse a pip lock into [{name, version, sha256}] preserving file order."""
    comps = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _REQ_RE.match(line)
        if m:
            current = {"name": m.group(1), "version": m.group(2), "sha256": None}
            comps.append(current)
            continue
        h = _HASH_RE.search(line)
        if h and current is not None and current["sha256"] is None:
            current["sha256"] = h.group(1).lower()
    return comps


def read_app_version():
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']',
                  CONFIG.read_text(encoding="utf-8"))
    return m.group(1) if m else "0.0.0"


def build_sbom(components, app_version):
    """Build a deterministic CycloneDX 1.5 document (no timestamps)."""
    comps = []
    for c in components:
        entry = {
            "type": "library",
            "name": c["name"],
            "version": c["version"],
            "purl": f"pkg:pypi/{c['name'].lower()}@{c['version']}",
        }
        if c.get("sha256"):
            entry["hashes"] = [{"alg": "SHA-256", "content": c["sha256"]}]
        comps.append(entry)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "SwiftShot",
                "version": app_version,
                "purl": f"pkg:github/SysAdminDoc/SwiftShot@v{app_version}",
                "licenses": [{"license": {"id": "GPL-3.0-only"}}],
            },
        },
        "components": comps,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate SwiftShot CycloneDX SBOM")
    ap.add_argument("-o", "--output", default=str(ROOT / "dist" / "swiftshot.sbom.json"))
    args = ap.parse_args(argv)

    components = parse_lock(LOCK.read_text(encoding="utf-8"))
    if not components:
        print("No components parsed from requirements.lock", file=sys.stderr)
        return 1
    missing = [c["name"] for c in components if not c["sha256"]]
    if missing:
        print(f"Lock entries missing hashes: {', '.join(missing)}", file=sys.stderr)
        return 1

    sbom = build_sbom(components, read_app_version())
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote SBOM with {len(components)} components -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
