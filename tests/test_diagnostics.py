"""Tests for the diagnostics bundle (diagnostics.py)."""

import json
import zipfile


def test_build_diagnostics_zip_contains_logs_config_versions(qapp, tmp_path):
    import diagnostics

    cfg_dir = tmp_path / "SwiftShot"
    cfg_dir.mkdir()
    (cfg_dir / "swiftshot.log").write_text("log line\n", encoding="utf-8")
    (cfg_dir / "swiftshot.log.1").write_text("older log\n", encoding="utf-8")
    (cfg_dir / "crash.log").write_text("traceback\n", encoding="utf-8")
    (cfg_dir / "swiftshot.json").write_text(
        json.dumps({"THEME": "dark", "API_TOKEN": "hunter2"}), encoding="utf-8")

    dest = tmp_path / "bundle.zip"
    out = diagnostics.build_diagnostics_zip(
        dest_path=str(dest), config_dir=str(cfg_dir))

    assert out == str(dest)
    with zipfile.ZipFile(dest) as zf:
        names = set(zf.namelist())
        assert {"swiftshot.log", "swiftshot.log.1", "crash.log",
                "swiftshot.json", "versions.json"} <= names
        # Secret-looking keys are redacted; ordinary settings survive.
        cfg = json.loads(zf.read("swiftshot.json"))
        assert cfg["THEME"] == "dark"
        assert cfg["API_TOKEN"] == "***redacted***"
        versions = json.loads(zf.read("versions.json"))
        assert versions["swiftshot"]
        assert "sqlite" in versions and "python" in versions


def test_build_diagnostics_zip_handles_empty_config_dir(qapp, tmp_path):
    import diagnostics

    cfg_dir = tmp_path / "empty"
    cfg_dir.mkdir()
    dest = tmp_path / "bundle.zip"
    diagnostics.build_diagnostics_zip(dest_path=str(dest), config_dir=str(cfg_dir))

    with zipfile.ZipFile(dest) as zf:
        # Even with no logs/config, the versions manifest is always present.
        assert "versions.json" in zf.namelist()


def test_cli_diagnostics_writes_bundle(qapp, tmp_path):
    import cli

    dest = tmp_path / "diag.zip"
    code = cli.run(["--diagnostics", "--out", str(dest)])
    assert code == 0
    assert dest.exists()
    with zipfile.ZipFile(dest) as zf:
        assert "versions.json" in zf.namelist()
