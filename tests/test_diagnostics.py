"""Privacy and content-contract tests for diagnostics bundles."""

import json
import zipfile


def _zip_text(dest):
    with zipfile.ZipFile(dest) as archive:
        return {
            name: archive.read(name).decode("utf-8")
            for name in archive.namelist()
        }


def test_bundle_uses_allowlist_and_consistent_path_aliases(
        qapp, tmp_path, monkeypatch):
    import diagnostics

    cfg_dir = tmp_path / "SwiftShot"
    cfg_dir.mkdir()
    private = r"C:\Users\Alice\Private\Tax Return 2026.png"
    other = r"C:\Users\Alice\Desktop\Client Secret.png"
    monkeypatch.setenv("USERNAME", "Alice")
    monkeypatch.setenv("USER", "Alice")
    (cfg_dir / "swiftshot.log").write_text(
        f'Opening image file in editor: "{private}"\n'
        f"Direct save failed: {private}\n"
        "Retry failed for Tax Return 2026.png\n"
        "API_TOKEN=hunter2\n"
        "Contact alice@example.test\n",
        encoding="utf-8",
    )
    (cfg_dir / "crash.log").write_text(
        'File "C:\\Users\\Alice\\repo\\SwiftShot\\App\\editor.py", line 42\n'
        "client_secret: swordfish\n",
        encoding="utf-8",
    )
    (cfg_dir / "swiftshot.json").write_text(json.dumps({
        "THEME": "dark",
        "CHECK_FOR_UPDATES": False,
        "CAPTURE_DELAY_MS": 250,
        "CAPTURE_WINDOW_HOTKEY": "leaked-hotkey@example.test",
        "AFTER_CAPTURE_ACTIONS": ["editor", "private-value"],
        "PIN_OPACITY": r"C:\Users\Alice\malicious-safe-key",
        "OUTPUT_FILE_PATH": r"C:\Users\Alice\Pictures",
        "OUTPUT_FILENAME_PATTERN": "Alice_{title}",
        "LAST_REGION": "10,20,640,480",
        "WINDOW_GEOMETRY": "private-window-geometry",
        "CAPTURE_HISTORY_DIR": r"C:\Users\Alice\SecretCaptures",
        "API_TOKEN": "hunter2",
        "FUTURE_SECRET": "swordfish",
    }), encoding="utf-8")
    (cfg_dir / "config.json").write_text(json.dumps({
        "ui_scale": 1.25,
        "window_geometry": "do-not-export",
        "password": "opensesame",
    }), encoding="utf-8")
    (cfg_dir / "recent.json").write_text(json.dumps({
        "recent": [private, private, other],
    }), encoding="utf-8")
    (cfg_dir / "history-health.json").write_text(json.dumps({
        "schema_version": 1,
        "status": "recovered",
        "checked_at": "2026-07-14T16:45:10.123456Z",
        "sqlite_version": "3.53.3",
        "quick_check": "failed",
        "quarantined_database": True,
        "recovered_file_count": 2,
        "database_path": r"C:\Users\Alice\SecretCaptures\history.sqlite3",
        "error_detail": "operator evidence must stay local",
    }), encoding="utf-8")

    dest = tmp_path / "bundle.zip"
    diagnostics.build_diagnostics_zip(
        dest_path=str(dest), config_dir=str(cfg_dir)
    )
    files = _zip_text(dest)

    assert {
        "logs/swiftshot.log",
        "logs/crash.log",
        "configuration.json",
        "history-health.json",
        "recent-files.json",
        "versions.json",
        "manifest.json",
    } <= files.keys()

    config = json.loads(files["configuration.json"])
    assert config["swiftshot.json"] == {
        "status": "ok",
        "settings": {
            "CAPTURE_DELAY_MS": 250,
            "CHECK_FOR_UPDATES": False,
            "THEME": "dark",
        },
        "invalid_fields": [
            "AFTER_CAPTURE_ACTIONS",
            "CAPTURE_WINDOW_HOTKEY",
            "PIN_OPACITY",
        ],
    }
    assert config["config.json"]["settings"] == {"ui_scale": 1.25}
    health = json.loads(files["history-health.json"])
    assert health == {
        "status": "ok",
        "settings": {
            "checked_at": "2026-07-14T16:45:10.123456Z",
            "quarantined_database": True,
            "quick_check": "failed",
            "recovered_file_count": 2,
            "schema_version": 1,
            "sqlite_version": "3.53.3",
            "status": "recovered",
        },
        "invalid_fields": [],
    }

    recent = json.loads(files["recent-files.json"])
    assert recent["items"][0] == recent["items"][1]
    assert recent["items"][0] != recent["items"][2]
    assert recent["items"][0] in files["logs/swiftshot.log"]
    assert files["logs/swiftshot.log"].count(recent["items"][0]) == 3

    entire_bundle = "\n".join(files.values()).casefold()
    for leaked in (
        "alice",
        "tax return",
        "client secret.png",
        "hunter2",
        "swordfish",
        "opensesame",
        "leaked-hotkey",
        "private-value",
        "malicious-safe-key",
        "operator evidence",
        "private-window-geometry",
        "10,20,640,480",
        "secretcaptures",
    ):
        assert leaked.casefold() not in entire_bundle
    assert "***redacted***" in entire_bundle


def test_malformed_files_never_enter_bundle_verbatim(qapp, tmp_path):
    import diagnostics

    cfg_dir = tmp_path / "SwiftShot"
    cfg_dir.mkdir()
    malformed = r'{"THEME": "dark", "password": "raw-secret", "path": "C:\Users\Alice'
    (cfg_dir / "swiftshot.json").write_text(malformed, encoding="utf-8")
    (cfg_dir / "recent.json").write_text(
        "raw-recent-secret C:\\Users\\Alice\\private.png", encoding="utf-8"
    )
    (cfg_dir / "history-health.json").write_text(
        '{"status":"raw-health-secret"', encoding="utf-8"
    )

    dest = tmp_path / "bundle.zip"
    diagnostics.build_diagnostics_zip(
        dest_path=str(dest), config_dir=str(cfg_dir)
    )
    files = _zip_text(dest)

    config = json.loads(files["configuration.json"])["swiftshot.json"]
    recent = json.loads(files["recent-files.json"])
    health = json.loads(files["history-health.json"])
    assert config["status"] == "malformed"
    assert config["settings"] == {}
    assert recent == {"status": "malformed", "items": []}
    assert health["status"] == "malformed"
    assert health["settings"] == {}
    combined = "\n".join(files.values())
    assert "raw-secret" not in combined
    assert "raw-recent-secret" not in combined
    assert "raw-health-secret" not in combined
    assert r"C:\Users\Alice" not in combined


def test_preview_names_included_and_excluded_categories(qapp, tmp_path):
    import diagnostics

    cfg_dir = tmp_path / "SwiftShot"
    cfg_dir.mkdir()
    (cfg_dir / "swiftshot.log").write_text("safe log", encoding="utf-8")
    (cfg_dir / "swiftshot.json").write_text("{}", encoding="utf-8")
    (cfg_dir / "recent.json").write_text('{"recent": []}', encoding="utf-8")
    (cfg_dir / "history-health.json").write_text("{}", encoding="utf-8")

    preview = diagnostics.diagnostics_preview(str(cfg_dir))
    copy = diagnostics.format_diagnostics_preview(preview)

    assert preview["included"] == [
        "Runtime and dependency versions",
        "Sanitized application/crash logs (1)",
        "Allowlisted non-path settings",
        "Pseudonymized recent-file entries",
        "Capture-history database health and recovery outcome",
    ]
    assert "Never included" in copy
    assert "Screenshots" in copy
    assert "Review the ZIP before sharing it" in copy


def test_empty_bundle_still_has_privacy_manifest(qapp, tmp_path):
    import diagnostics

    cfg_dir = tmp_path / "empty"
    cfg_dir.mkdir()
    dest = tmp_path / "bundle.zip"
    diagnostics.build_diagnostics_zip(dest_path=str(dest), config_dir=str(cfg_dir))

    files = _zip_text(dest)
    assert set(files) == {"versions.json", "manifest.json"}
    manifest = json.loads(files["manifest.json"])
    assert manifest["schema_version"] == 2
    assert "Screenshots" in " ".join(manifest["excluded"])


def test_cli_diagnostics_writes_sanitized_bundle(qapp, tmp_path):
    import cli

    dest = tmp_path / "diag.zip"
    code = cli.run(["--diagnostics", "--out", str(dest)])
    assert code == 0
    assert dest.exists()
    with zipfile.ZipFile(dest) as archive:
        assert {"versions.json", "manifest.json"} <= set(archive.namelist())


def test_oversized_json_is_not_loaded_or_copied_into_bundle(qapp, tmp_path):
    import diagnostics

    cfg_dir = tmp_path / "SwiftShot"
    cfg_dir.mkdir()
    secret = b"private-marker-should-not-appear"
    (cfg_dir / "swiftshot.json").write_bytes(
        b'{"THEME":"dark","padding":"'
        + b"x" * diagnostics.MAX_JSON_FILE_BYTES
        + secret
        + b'"}'
    )
    dest = tmp_path / "bundle.zip"

    diagnostics.build_diagnostics_zip(str(dest), str(cfg_dir))
    files = _zip_text(dest)

    record = json.loads(files["configuration.json"])["swiftshot.json"]
    assert record["status"] == "unreadable"
    assert "1 MiB safety limit" in record["error"]
    assert secret.decode() not in "\n".join(files.values())


def test_failed_diagnostics_publish_preserves_existing_bundle(
        qapp, tmp_path, monkeypatch):
    import diagnostics
    import utils

    cfg_dir = tmp_path / "SwiftShot"
    cfg_dir.mkdir()
    dest = tmp_path / "bundle.zip"
    dest.write_bytes(b"existing operator file")
    monkeypatch.setattr(
        utils.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    try:
        diagnostics.build_diagnostics_zip(str(dest), str(cfg_dir))
    except OSError:
        pass
    else:
        raise AssertionError("publish failure should be reported")

    assert dest.read_bytes() == b"existing operator file"
    assert list(tmp_path.glob(".bundle.zip.*.tmp")) == []
