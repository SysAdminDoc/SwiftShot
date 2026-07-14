import io
import json
import warnings
import zipfile

import pytest
from PIL import Image


def _image_bytes(format_name="PNG", size=(8, 8), frames=1):
    output = io.BytesIO()
    images = [Image.new("RGBA", size, (index, 2, 3, 255))
              for index in range(frames)]
    options = {}
    if frames > 1:
        options = {"save_all": True, "append_images": images[1:], "duration": 10}
    images[0].save(output, format_name, **options)
    return output.getvalue()


def _write_project(path, meta, members=None, compression=zipfile.ZIP_STORED):
    members = members or {}
    with zipfile.ZipFile(path, "w", compression) as zf:
        zf.writestr("project.json", json.dumps(meta))
        for name, payload in members.items():
            zf.writestr(name, payload)


def _flat_meta(version=3):
    return {
        "magic": "SWIFTSHOT_PROJECT",
        "version": version,
        "active_index": 0,
        "layers": [{
            "name": "Layer", "visible": True, "opacity": 255,
            "blend_mode": "Normal", "locked": False,
            "mask_enabled": True, "has_mask": False, "effects": [],
            "is_group": False,
        }],
    }


def test_load_image_accepts_supported_bounded_input(tmp_path):
    from safe_io import load_image

    path = tmp_path / "image.png"
    path.write_bytes(_image_bytes(size=(9, 7)))

    image = load_image(path)

    assert image.mode == "RGBA"
    assert image.size == (9, 7)


def test_load_image_rejects_pixel_and_frame_limits(monkeypatch):
    import safe_io

    monkeypatch.setattr(safe_io, "MAX_IMAGE_PIXELS", 32)
    with pytest.raises(safe_io.SafeImageError, match="decoded pixel"):
        safe_io.load_image(_image_bytes(size=(8, 8)))

    monkeypatch.setattr(safe_io, "MAX_IMAGE_PIXELS", 1000)
    monkeypatch.setattr(safe_io, "MAX_IMAGE_FRAMES", 1)
    with pytest.raises(safe_io.SafeImageError, match="2 frames"):
        safe_io.load_image(_image_bytes(format_name="GIF", frames=2))


def test_load_image_rejects_file_size_and_format(tmp_path, monkeypatch):
    import safe_io

    path = tmp_path / "image.png"
    path.write_bytes(_image_bytes())
    monkeypatch.setattr(safe_io, "MAX_IMAGE_FILE_BYTES", 10)
    with pytest.raises(safe_io.SafeImageError, match="byte limit"):
        safe_io.load_image(path)

    with pytest.raises(safe_io.SafeImageError, match="Unsupported image format"):
        safe_io.load_image(_image_bytes(format_name="GIF"), allowed_formats={"PNG"},
                           max_bytes=1024 * 1024)


def test_decode_budget_caps_aggregate_project_pixels():
    from safe_io import DecodeBudget, SafeImageError, load_image

    budget = DecodeBudget(limit=100)
    load_image(_image_bytes(size=(8, 8)), budget=budget)
    with pytest.raises(SafeImageError, match="Decoded project pixels"):
        load_image(_image_bytes(size=(8, 8)), budget=budget)


def test_valid_project_archive_passes_preflight(tmp_path):
    from safe_io import validate_project_archive

    path = tmp_path / "valid.swiftshot"
    _write_project(path, _flat_meta(), {"layer_0.png": _image_bytes()})

    with zipfile.ZipFile(path) as zf:
        meta, names = validate_project_archive(zf, path)

    assert meta["version"] == 3
    assert names == {"project.json", "layer_0.png"}


def test_future_project_version_is_rejected_before_layer_decode(tmp_path):
    from safe_io import UnsupportedProjectVersion, validate_project_archive

    path = tmp_path / "future.swiftshot"
    _write_project(path, _flat_meta(version=4))

    with zipfile.ZipFile(path) as zf, pytest.raises(
            UnsupportedProjectVersion, match="newer than supported version 3"):
        validate_project_archive(zf, path)


def test_project_rejects_duplicate_and_unexpected_members(tmp_path):
    from safe_io import ProjectValidationError, validate_project_archive

    duplicate = tmp_path / "duplicate.swiftshot"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(duplicate, "w") as zf:
            zf.writestr("project.json", json.dumps(_flat_meta()))
            zf.writestr("layer_0.png", _image_bytes())
            zf.writestr("layer_0.png", _image_bytes())
    with zipfile.ZipFile(duplicate) as zf, pytest.raises(
            ProjectValidationError, match="duplicate member"):
        validate_project_archive(zf, duplicate)

    unexpected = tmp_path / "unexpected.swiftshot"
    _write_project(unexpected, _flat_meta(), {
        "layer_0.png": _image_bytes(), "notes.txt": b"not part of the format",
    })
    with zipfile.ZipFile(unexpected) as zf, pytest.raises(
            ProjectValidationError, match="unexpected member"):
        validate_project_archive(zf, unexpected)


def test_project_rejects_member_size_and_layer_depth(tmp_path, monkeypatch):
    import safe_io

    oversized = tmp_path / "oversized.swiftshot"
    _write_project(oversized, _flat_meta(), {"layer_0.png": _image_bytes()})
    monkeypatch.setattr(safe_io, "MAX_PROJECT_MEMBER_BYTES", 10)
    with zipfile.ZipFile(oversized) as zf, pytest.raises(
            safe_io.ProjectValidationError, match="exceeds 10 bytes"):
        safe_io.validate_project_archive(zf, oversized)

    monkeypatch.setattr(safe_io, "MAX_PROJECT_MEMBER_BYTES", 1024 * 1024)
    monkeypatch.setattr(safe_io, "MAX_PROJECT_DEPTH", 1)
    nested_meta = _flat_meta()
    nested_meta["layers"] = [{
        "name": "Group", "is_group": True, "has_mask": False,
        "children": [dict(_flat_meta()["layers"][0])],
    }]
    nested = tmp_path / "nested.swiftshot"
    _write_project(nested, nested_meta, {
        "layer_0_child_0.png": _image_bytes(),
    })
    with zipfile.ZipFile(nested) as zf, pytest.raises(
            safe_io.ProjectValidationError, match="nesting exceeds"):
        safe_io.validate_project_archive(zf, nested)


def test_project_rejects_malformed_json_and_bad_crc(tmp_path):
    from safe_io import ProjectValidationError, validate_project_archive

    malformed = tmp_path / "malformed.swiftshot"
    with zipfile.ZipFile(malformed, "w") as zf:
        zf.writestr("project.json", "{not json")
    with zipfile.ZipFile(malformed) as zf, pytest.raises(
            ProjectValidationError, match="Invalid project.json"):
        validate_project_archive(zf, malformed)

    png = _image_bytes()
    corrupt = tmp_path / "corrupt.swiftshot"
    _write_project(corrupt, _flat_meta(), {"layer_0.png": png})
    raw = bytearray(corrupt.read_bytes())
    start = raw.find(png)
    assert start >= 0
    raw[start + len(png) // 2] ^= 0xFF
    corrupt.write_bytes(raw)
    with zipfile.ZipFile(corrupt) as zf, pytest.raises(
            (ProjectValidationError, zipfile.BadZipFile), match="CRC"):
        validate_project_archive(zf, corrupt)


def test_project_rejects_mask_dimension_mismatch(tmp_path, qapp, monkeypatch):
    from editor import ImageEditor, QMessageBox
    from PyQt5.QtGui import QColor, QPixmap

    meta = _flat_meta()
    meta["layers"][0]["has_mask"] = True
    path = tmp_path / "bad-mask.swiftshot"
    _write_project(path, meta, {
        "layer_0.png": _image_bytes(size=(8, 8)),
        "layer_0.mask.png": _image_bytes(size=(4, 4)),
    })
    pixmap = QPixmap(3, 3)
    pixmap.fill(QColor("red"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    editor = ImageEditor(pixmap)
    old_layer = editor.layers[0]
    old_title = editor.windowTitle()
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *args: None))
    try:
        assert editor._load_project_from(str(path)) is False
        assert editor.layers == [old_layer]
        assert editor.windowTitle() == old_title
    finally:
        editor.close()
