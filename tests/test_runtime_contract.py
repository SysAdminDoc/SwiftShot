import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "App"


def test_python_312_is_the_only_supported_runtime():
    import runtime_contract

    assert runtime_contract.python_version_error((3, 12, 0)) is None
    assert runtime_contract.python_version_error((3, 12, 99)) is None
    assert runtime_contract.python_version_error((3, 11, 9)) is not None
    assert runtime_contract.python_version_error((3, 13, 0)) is not None


def test_incompatible_python_prints_one_actionable_line():
    import runtime_contract

    stream = io.StringIO()
    supported = runtime_contract.require_supported_python((3, 11, 9), stream)
    lines = stream.getvalue().splitlines()

    assert supported is False
    assert lines == [
        "SwiftShot requires Python 3.12.x; found Python 3.11.9. "
        "Install Python 3.12, then run: py -3.12 App\\main.py"
    ]


def test_entrypoints_share_one_dpi_policy():
    main_source = (APP / "main.py").read_text(encoding="utf-8")
    editor_source = (APP / "editor.py").read_text(encoding="utf-8")

    assert "configure_dpi_policy" in main_source
    assert "configure_dpi_policy" in editor_source
    assert "AA_EnableHighDpiScaling" not in main_source
    assert "AA_EnableHighDpiScaling" not in editor_source


def test_build_and_docs_use_python_312_and_real_root_paths():
    build = (APP / "Build-SwiftShot.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "py -3.12" in build
    assert "sys.version_info[:2] == (3, 12)" in build
    assert "Python 3.8" not in build
    assert "py -3.12 App\\main.py" in readme
    assert ".\\App\\Build-SwiftShot.ps1" in readme
    assert "Python 3.8" not in readme
    assert "GitHub Releases API" in readme
    assert "downloads a model on first use" in readme


def test_runtime_contract_is_in_release_manifests():
    build = (APP / "Build-SwiftShot.ps1").read_text(encoding="utf-8")
    spec = (APP / "SwiftShot.spec").read_text(encoding="utf-8")

    assert '"runtime_contract.py"' in build
    assert '"runtime_contract"' in build
    assert "'runtime_contract'" in spec
