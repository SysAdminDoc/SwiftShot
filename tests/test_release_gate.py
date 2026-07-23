"""Deterministic release + package gate assertions (R-27): hash-pinned lock,
SBOM generation, version consistency, and winget schema 1.12.0."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
if str(PACKAGING) not in sys.path:
    sys.path.insert(0, str(PACKAGING))


# ── hash-locked requirements ────────────────────────────────────────────────

def test_requirements_lock_is_hash_pinned():
    import gen_sbom
    comps = gen_sbom.parse_lock((ROOT / "requirements.lock").read_text(encoding="utf-8"))
    assert {c["name"] for c in comps} == {
        "PyQt5", "PyQt5-Qt5", "PyQt5-sip", "Pillow", "numpy"}
    for c in comps:
        assert re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", c["version"]), c
        assert c["sha256"] and re.fullmatch(r"[0-9a-f]{64}", c["sha256"]), c


# ── SBOM ────────────────────────────────────────────────────────────────────

def test_sbom_build_is_valid_cyclonedx():
    import gen_sbom
    comps = gen_sbom.parse_lock((ROOT / "requirements.lock").read_text(encoding="utf-8"))
    sbom = gen_sbom.build_sbom(comps, "9.9.9")
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.5"
    assert sbom["metadata"]["component"]["version"] == "9.9.9"
    assert len(sbom["components"]) == 5
    for comp in sbom["components"]:
        assert comp["purl"].startswith("pkg:pypi/")
        assert comp["hashes"][0]["alg"] == "SHA-256"
        assert re.fullmatch(r"[0-9a-f]{64}", comp["hashes"][0]["content"])


def test_sbom_is_deterministic():
    import gen_sbom
    comps = gen_sbom.parse_lock((ROOT / "requirements.lock").read_text(encoding="utf-8"))
    a = json.dumps(gen_sbom.build_sbom(comps, "1.0.0"), indent=2, sort_keys=True)
    b = json.dumps(gen_sbom.build_sbom(comps, "1.0.0"), indent=2, sort_keys=True)
    assert a == b


def test_sbom_generator_writes_file(tmp_path):
    import gen_sbom
    out = tmp_path / "sbom.json"
    rc = gen_sbom.main(["-o", str(out)])
    assert rc == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["metadata"]["component"]["name"] == "SwiftShot"
    assert len(doc["components"]) == 5


# ── version consistency ─────────────────────────────────────────────────────

def test_all_versions_match():
    import check_versions
    mismatches, expected = check_versions.find_mismatches()
    assert mismatches == {}, mismatches
    # config, three winget files, scoop, README badge.
    assert len(check_versions.collect_versions()) == 6


# ── winget schema ───────────────────────────────────────────────────────────

def test_winget_manifests_on_schema_1_12():
    for f in (PACKAGING / "winget").glob("*.yaml"):
        text = f.read_text(encoding="utf-8")
        assert "ManifestVersion: 1.12.0" in text, f.name
        assert "winget-manifest." in text and "1.12.0.schema.json" in text, f.name
