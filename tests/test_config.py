from pathlib import Path


def test_config_save_and_reload_round_trip(fresh_config):
    cfg = fresh_config.Config()
    cfg.OUTPUT_FILE_FORMAT = "jpg"
    cfg.OUTPUT_JPEG_QUALITY = 72
    cfg.save()

    reloaded = fresh_config.Config()

    assert reloaded.OUTPUT_FILE_FORMAT == "jpg"
    assert reloaded.OUTPUT_JPEG_QUALITY == 72


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
