import json
from pathlib import Path


def test_config_save_and_reload_round_trip(fresh_config):
    cfg = fresh_config.Config()
    cfg.OUTPUT_FILE_FORMAT = "jpg"
    cfg.OUTPUT_JPEG_QUALITY = 72
    cfg.THEME = "light"
    cfg.BEAUTIFY_PRESET = "presentation"
    cfg.CAPTURE_HISTORY_AUTO_OCR = True
    cfg.save()

    reloaded = fresh_config.Config()

    assert reloaded.OUTPUT_FILE_FORMAT == "jpg"
    assert reloaded.OUTPUT_JPEG_QUALITY == 72
    assert reloaded.THEME == "light"
    assert reloaded.BEAUTIFY_PRESET == "presentation"
    assert reloaded.CAPTURE_HISTORY_AUTO_OCR is True


def test_config_preserves_unknown_newer_keys_on_save(fresh_config):
    """An older build must not erase keys written by a newer build when it
    saves — otherwise a downgrade/upgrade round-trip silently resets them."""
    cfg = fresh_config.Config()
    # Simulate a config file that already contains a key this build doesn't know.
    path = Path(cfg._config_file)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data["FUTURE_FEATURE_ENABLED"] = True
    path.write_text(json.dumps(data), encoding="utf-8")

    reloaded = fresh_config.Config()          # loads, stashes the unknown key
    reloaded.THEME = "light"
    reloaded.save()                            # must not drop the unknown key

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved.get("FUTURE_FEATURE_ENABLED") is True
    assert saved.get("THEME") == "light"


def test_after_capture_actions_normalize_and_sync_legacy_value(fresh_config):
    cfg = fresh_config.Config()
    cfg.AFTER_CAPTURE_ACTION = "clipboard"
    cfg.AFTER_CAPTURE_ACTIONS = ["save", "save", "invalid", "editor"]

    assert cfg.get_after_capture_actions() == ["save", "editor"]
    assert cfg.AFTER_CAPTURE_ACTION == "save"

    cfg.AFTER_CAPTURE_ACTIONS = []
    cfg.AFTER_CAPTURE_ACTION = "clipboard"
    assert cfg.get_after_capture_actions() == ["clipboard"]


def test_import_legacy_after_capture_action_populates_workflow(fresh_config, tmp_path):
    cfg = fresh_config.Config()
    cfg.AFTER_CAPTURE_ACTIONS = ["editor"]
    legacy_path = tmp_path / "legacy-settings.json"
    legacy_path.write_text(
        json.dumps({"AFTER_CAPTURE_ACTION": "clipboard"}),
        encoding="utf-8",
    )

    assert cfg.import_settings(str(legacy_path))
    assert cfg.get_after_capture_actions() == ["clipboard"]


def test_config_reset_preserves_state_and_restores_defaults(fresh_config):
    cfg = fresh_config.Config()
    cfg.OUTPUT_FILE_FORMAT = "jpg"
    cfg.LAST_SAVE_DIR = "C:/captures"
    cfg.reset_to_defaults()

    assert cfg.OUTPUT_FILE_FORMAT == fresh_config.Config.OUTPUT_FILE_FORMAT
    assert cfg.LAST_SAVE_DIR == "C:/captures"


def test_config_export_import_excludes_state_keys(fresh_config, tmp_path):
    cfg = fresh_config.Config()
    cfg.OUTPUT_JPEG_QUALITY = 61
    cfg.LAST_REGION = "1,2,3,4"
    export_path = tmp_path / "settings.json"

    assert cfg.export_settings(str(export_path))

    cfg.OUTPUT_JPEG_QUALITY = 90
    cfg.LAST_REGION = ""

    assert cfg.import_settings(str(export_path))
    assert cfg.OUTPUT_JPEG_QUALITY == 61
    assert cfg.LAST_REGION == ""


def test_get_filename_increments_existing_file(fresh_config, tmp_path):
    cfg = fresh_config.Config()
    cfg.OUTPUT_FILE_PATH = str(tmp_path)
    cfg.OUTPUT_FILE_FORMAT = "png"
    cfg.OUTPUT_FILENAME_PATTERN = "SwiftShot_test"
    cfg.OUTPUT_FILE_INCREMENT = True
    (tmp_path / "SwiftShot_test.png").write_text("existing", encoding="utf-8")

    assert Path(cfg.get_filename()).name == "SwiftShot_test_1.png"


def test_get_filename_renders_rich_variables_and_counter(fresh_config, tmp_path):
    cfg = fresh_config.Config()
    cfg.OUTPUT_FILE_PATH = str(tmp_path)
    cfg.OUTPUT_FILE_FORMAT = "webp"
    cfg.OUTPUT_FILENAME_PATTERN = "{app}_{title}_{w}x{h}_{user}_{counter}"
    cfg.OUTPUT_FILE_INCREMENT = True

    first = Path(cfg.get_filename(
        app_name="Code",
        window_title="Bug:one/two",
        user_name="matt",
        width=1280,
        height=720,
    )).name
    assert first == "Code_Bug_one_two_1280x720_matt_001.webp"

    (tmp_path / first).write_text("existing", encoding="utf-8")
    second = Path(cfg.get_filename(
        app_name="Code",
        window_title="Bug:one/two",
        user_name="matt",
        width=1280,
        height=720,
    )).name
    assert second == "Code_Bug_one_two_1280x720_matt_002.webp"


def test_preview_filename_uses_template_help_variables(fresh_config):
    cfg = fresh_config.Config()

    preview = cfg.preview_filename(
        pattern="{app}_{title}_{w}x{h}_{counter}",
        file_format="webp",
        app_name="notepad",
        window_title="Release notes",
        width=1920,
        height=1080,
    )

    assert preview == "notepad_Release notes_1920x1080_001.webp"


def test_import_rejects_wrong_types_and_bad_enums(fresh_config, tmp_path):
    """Malformed settings files must not corrupt runtime settings
    (regression: a string JPEG quality later crashed saves)."""
    cfg = fresh_config.Config()
    bad_path = tmp_path / "bad-settings.json"
    bad_path.write_text(json.dumps({
        "OUTPUT_JPEG_QUALITY": "ninety",
        "CAPTURE_TIMER_SECONDS": True,
        "SHOW_NOTIFICATIONS": "yes",
        "OUTPUT_FILE_FORMAT": "exe",
        "THEME": "hotdog-stand",
        "AFTER_CAPTURE_ACTIONS": "editor",
    }), encoding="utf-8")

    assert cfg.import_settings(str(bad_path))

    assert cfg.OUTPUT_JPEG_QUALITY == fresh_config.Config.OUTPUT_JPEG_QUALITY
    assert cfg.CAPTURE_TIMER_SECONDS == fresh_config.Config.CAPTURE_TIMER_SECONDS
    assert cfg.SHOW_NOTIFICATIONS == fresh_config.Config.SHOW_NOTIFICATIONS
    assert cfg.OUTPUT_FILE_FORMAT == fresh_config.Config.OUTPUT_FILE_FORMAT
    assert cfg.THEME == fresh_config.Config.THEME


def test_recent_colors_reset_after_mutation(fresh_config):
    """add_recent_color used to mutate the class-level default list, which
    made Reset to Defaults unable to clear recent colors (regression)."""
    cfg = fresh_config.Config()
    cfg.add_recent_color("#ABCDEF")
    cfg.add_recent_color("#123456")
    assert cfg.EDITOR_RECENT_COLORS == ["#123456".lower(), "#abcdef"]
    assert fresh_config.Config.EDITOR_RECENT_COLORS == []

    cfg.reset_to_defaults()
    assert cfg.EDITOR_RECENT_COLORS == []


def test_corrupt_config_backed_up_and_defaults_used(fresh_config, tmp_path):
    cfg = fresh_config.Config()
    Path(cfg._config_file).write_text("{not json", encoding="utf-8")

    reloaded = fresh_config.Config()

    assert reloaded.OUTPUT_FILE_FORMAT == fresh_config.Config.OUTPUT_FILE_FORMAT
    assert Path(cfg._config_file + ".corrupt").exists()


def test_version_info_uses_config_version(fresh_config, monkeypatch):
    app_dir = Path(__file__).resolve().parents[1] / "App"
    monkeypatch.chdir(app_dir)

    namespace = {
        "__file__": str(app_dir / "version_info.txt"),
        "VSVersionInfo": lambda **kwargs: kwargs,
        "FixedFileInfo": lambda **kwargs: kwargs,
        "StringFileInfo": lambda value: value,
        "StringTable": lambda name, values: (name, values),
        "StringStruct": lambda name, value: (name, value),
        "VarFileInfo": lambda value: value,
        "VarStruct": lambda name, value: (name, value),
    }

    exec((app_dir / "version_info.txt").read_text(encoding="utf-8"), namespace)

    assert namespace["_VERSION"] == fresh_config.Config.APP_VERSION
    assert namespace["_VERSION4"] == f"{fresh_config.Config.APP_VERSION}.0"
