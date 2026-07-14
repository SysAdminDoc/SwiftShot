"""Bounded, fail-closed image and SwiftShot project loading."""

import io
import json
import os
import warnings
import zipfile
from datetime import datetime

from PIL import Image


ALLOWED_IMAGE_FORMATS = frozenset({
    "PNG", "JPEG", "WEBP", "BMP", "TIFF", "GIF", "AVIF",
})
MAX_IMAGE_FILE_BYTES = 512 * 1024 * 1024
MAX_IMAGE_PIXELS = 100_000_000
MAX_IMAGE_DIMENSION = 32_768
MAX_IMAGE_FRAMES = 256

MAX_PROJECT_FILE_BYTES = 1024 * 1024 * 1024
MAX_PROJECT_MEMBER_BYTES = 256 * 1024 * 1024
MAX_PROJECT_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_PROJECT_JSON_BYTES = 2 * 1024 * 1024
MAX_PROJECT_MEMBERS = 1024
MAX_PROJECT_LAYERS = 256
MAX_PROJECT_DEPTH = 16
MAX_PROJECT_DECODED_PIXELS = 250_000_000
MAX_LAYER_NAME_LENGTH = 512
MAX_LAYER_EFFECTS = 64
MAX_RECOVERY_PREVIEW_BYTES = 2 * 1024 * 1024
MAX_RECOVERY_NAME_LENGTH = 255
RECOVERY_PREVIEW_MEMBER = "recovery-preview.png"

_EFFECT_SCHEMAS = {
    "drop_shadow": {
        "ints": {"blur": (0, 60), "opacity": (0, 255),
                 "angle": (0, 360), "distance": (0, 100)},
        "colors": {"color"},
    },
    "outer_glow": {
        "ints": {"blur": (0, 60), "opacity": (0, 255),
                 "spread": (0, 30)},
        "colors": {"color"},
    },
    "inner_glow": {
        "ints": {"blur": (0, 60), "opacity": (0, 255)},
        "colors": {"color"},
    },
    "bevel_emboss": {
        "ints": {"depth": (1, 20), "size": (1, 30),
                 "opacity": (0, 255), "angle": (0, 360)},
        "colors": {"highlight_color", "shadow_color"},
    },
    "color_overlay": {
        "ints": {"opacity": (0, 255)},
        "colors": {"color"},
    },
    "gradient_overlay": {
        "ints": {"opacity": (0, 255), "angle": (0, 360)},
        "colors": {"color1", "color2"},
    },
    "stroke": {
        "ints": {"size": (1, 50), "opacity": (0, 255)},
        "colors": {"color"},
        "enums": {"position": {"outside", "inside", "center"}},
    },
}


class SafeImageError(ValueError):
    pass


class ProjectValidationError(ValueError):
    pass


class UnsupportedProjectVersion(ProjectValidationError):
    pass


class DecodeBudget:
    def __init__(self, limit=None):
        self.limit = MAX_PROJECT_DECODED_PIXELS if limit is None else int(limit)
        self.pixels = 0

    def add(self, width, height):
        self.pixels += width * height
        if self.pixels > self.limit:
            raise SafeImageError(
                f"Decoded project pixels exceed the {self.limit:,} pixel limit"
            )


def _validate_dimensions(width, height):
    if not isinstance(width, int) or not isinstance(height, int):
        raise SafeImageError("Image dimensions are invalid")
    if width < 1 or height < 1:
        raise SafeImageError("Image dimensions must be positive")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise SafeImageError(
            f"Image dimensions exceed {MAX_IMAGE_DIMENSION:,} pixels per side"
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise SafeImageError(
            f"Image exceeds the {MAX_IMAGE_PIXELS:,} decoded pixel limit"
        )


def load_image(source, mode="RGBA", allowed_formats=None, max_bytes=None,
               budget=None):
    """Decode one bounded image frame and return a detached Pillow image."""
    allowed = {str(name).upper() for name in
               (allowed_formats or ALLOWED_IMAGE_FORMATS)}
    byte_limit = MAX_IMAGE_FILE_BYTES if max_bytes is None else int(max_bytes)
    stream = None
    should_close = False
    if isinstance(source, (str, os.PathLike)):
        path = os.path.abspath(os.fspath(source))
        try:
            size = os.path.getsize(path)
        except OSError as error:
            raise SafeImageError(f"Could not inspect image: {error}") from error
        if size > byte_limit:
            raise SafeImageError(
                f"Image file exceeds the {byte_limit:,} byte limit"
            )
        stream = open(path, "rb")
        should_close = True
    elif isinstance(source, (bytes, bytearray, memoryview)):
        payload = bytes(source)
        if len(payload) > byte_limit:
            raise SafeImageError(
                f"Image payload exceeds the {byte_limit:,} byte limit"
            )
        stream = io.BytesIO(payload)
        should_close = True
    else:
        raise TypeError("Image source must be a path or byte payload")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                format_name = (image.format or "").upper()
                if format_name not in allowed:
                    raise SafeImageError(
                        f"Unsupported image format: {format_name or 'unknown'}"
                    )
                width, height = image.size
                _validate_dimensions(width, height)
                frames = int(getattr(image, "n_frames", 1) or 1)
                if frames > MAX_IMAGE_FRAMES:
                    raise SafeImageError(
                        f"Image has {frames:,} frames; limit is {MAX_IMAGE_FRAMES:,}"
                    )
                if budget is not None:
                    budget.add(width, height)
                image.seek(0)
                decoded = image.convert(mode)
                decoded.load()
                return decoded
    except (SafeImageError, Image.DecompressionBombError):
        raise
    except Exception as error:
        raise SafeImageError(f"Could not decode image: {error}") from error
    finally:
        if should_close:
            stream.close()


def _project_error(message):
    raise ProjectValidationError(message)


def _require_int(value, label, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int):
        _project_error(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        _project_error(f"{label} must be between {minimum} and {maximum}")
    return value


def _validate_effect(effect, label):
    kind = effect.get("type")
    schema = _EFFECT_SCHEMAS.get(kind)
    if schema is None:
        _project_error(f"{label}.type is invalid")
    if "enabled" in effect and type(effect["enabled"]) is not bool:
        _project_error(f"{label}.enabled must be true or false")

    int_fields = schema.get("ints", {})
    color_fields = schema.get("colors", set())
    enum_fields = schema.get("enums", {})
    allowed = {"type", "enabled", *int_fields, *color_fields, *enum_fields}
    unexpected = set(effect) - allowed
    if unexpected:
        _project_error(
            f"{label} contains unexpected field {sorted(unexpected)[0]}")

    for key, (minimum, maximum) in int_fields.items():
        if key in effect:
            _require_int(effect[key], f"{label}.{key}", minimum, maximum)
    for key in color_fields:
        if key not in effect:
            continue
        color = effect[key]
        if (not isinstance(color, list) or len(color) != 3 or
                any(type(channel) is not int or not 0 <= channel <= 255
                    for channel in color)):
            _project_error(f"{label}.{key} must be three RGB integers")
    for key, choices in enum_fields.items():
        if key in effect and effect[key] not in choices:
            _project_error(f"{label}.{key} is invalid")


def _validate_layer_common(layer, label):
    if not isinstance(layer, dict):
        _project_error(f"{label} must be an object")
    name = layer.get("name", "Layer")
    if not isinstance(name, str) or len(name) > MAX_LAYER_NAME_LENGTH:
        _project_error(f"{label}.name is invalid")
    for key in ("visible", "locked", "mask_enabled", "has_mask", "is_group"):
        if key in layer and not isinstance(layer[key], bool):
            _project_error(f"{label}.{key} must be true or false")
    if "opacity" in layer:
        _require_int(layer["opacity"], f"{label}.opacity", 0, 255)
    if "blend_mode" in layer:
        blend_mode = layer["blend_mode"]
        if not isinstance(blend_mode, str) or len(blend_mode) > 64:
            _project_error(f"{label}.blend_mode is invalid")
    effects = layer.get("effects", [])
    if not isinstance(effects, list) or len(effects) > MAX_LAYER_EFFECTS:
        _project_error(f"{label}.effects is invalid")
    if any(not isinstance(effect, dict) for effect in effects):
        _project_error(f"{label}.effects entries must be objects")
    for index, effect in enumerate(effects):
        _validate_effect(effect, f"{label}.effects[{index}]")


def _validate_group_size(layer, label):
    if "group_size" not in layer:
        return
    size = layer["group_size"]
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        _project_error(f"{label}.group_size must contain width and height")
    try:
        _validate_dimensions(size[0], size[1])
    except SafeImageError as error:
        _project_error(f"{label}.group_size is invalid: {error}")


def _require_member(names, member_name, label):
    if member_name not in names:
        _project_error(f"{label} is missing {member_name}")


def _validate_v3_layer(layer, key, names, allowed_members, counter, depth):
    label = f"layer {key}"
    if depth > MAX_PROJECT_DEPTH:
        _project_error(f"Layer nesting exceeds {MAX_PROJECT_DEPTH}")
    _validate_layer_common(layer, label)
    counter[0] += 1
    if counter[0] > MAX_PROJECT_LAYERS:
        _project_error(f"Project exceeds {MAX_PROJECT_LAYERS} layers")

    is_group = layer.get("is_group", False)
    image_name = f"{key}.png"
    allowed_members.add(image_name)
    if not is_group:
        _require_member(names, image_name, label)
    if layer.get("has_mask", False):
        mask_name = f"{key}.mask.png"
        allowed_members.add(mask_name)
        _require_member(names, mask_name, label)

    children = layer.get("children", [])
    if is_group:
        _validate_group_size(layer, label)
        if not isinstance(children, list):
            _project_error(f"{label}.children must be a list")
        for index, child in enumerate(children):
            _validate_v3_layer(
                child, f"{key}_child_{index}", names, allowed_members,
                counter, depth + 1,
            )
    elif children:
        _project_error(f"{label} is not a group but contains children")


def _validate_legacy_layers(layers, names, allowed_members):
    counter = len(layers)
    if counter > MAX_PROJECT_LAYERS:
        _project_error(f"Project exceeds {MAX_PROJECT_LAYERS} layers")
    for index, layer in enumerate(layers):
        label = f"layer {index}"
        _validate_layer_common(layer, label)
        is_group = layer.get("is_group", False)
        image_name = f"layer_{index}.png"
        allowed_members.add(image_name)
        if not is_group:
            _require_member(names, image_name, label)
        if layer.get("has_mask", False):
            mask_name = f"mask_{index}.png"
            allowed_members.add(mask_name)
            _require_member(names, mask_name, label)
        child_count = _require_int(
            layer.get("group_child_count", 0),
            f"{label}.group_child_count", 0, MAX_PROJECT_LAYERS,
        )
        if not is_group and child_count:
            _project_error(f"{label} is not a group but declares children")
        counter += child_count
        if counter > MAX_PROJECT_LAYERS:
            _project_error(f"Project exceeds {MAX_PROJECT_LAYERS} layers")
        for child_index in range(child_count):
            child_name = f"layer_{index}_child_{child_index}.png"
            allowed_members.add(child_name)
            _require_member(names, child_name, label)


def _validate_recovery_metadata(meta, names, infos_by_name, allowed_members):
    """Validate optional crash-recovery metadata and its bounded preview."""
    recovery = meta.get("recovery")
    if recovery is None:
        return
    if not isinstance(recovery, dict) or set(recovery) != {
            "magic", "version", "document_name", "saved_at"}:
        _project_error("Recovery metadata is invalid")
    if (recovery["magic"] != "SWIFTSHOT_RECOVERY" or
            type(recovery["version"]) is not int or recovery["version"] != 1):
        _project_error("Recovery metadata version is invalid")
    name = recovery["document_name"]
    if (not isinstance(name, str) or not name or
            len(name) > MAX_RECOVERY_NAME_LENGTH or
            name in (".", "..") or "/" in name or "\\" in name):
        _project_error("Recovery document name is invalid")
    saved_at = recovery["saved_at"]
    if not isinstance(saved_at, str) or len(saved_at) > 40:
        _project_error("Recovery timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp must contain a timezone")
    except ValueError as error:
        raise ProjectValidationError("Recovery timestamp is invalid") from error
    _require_member(names, RECOVERY_PREVIEW_MEMBER, "recovery metadata")
    preview_info = infos_by_name[RECOVERY_PREVIEW_MEMBER]
    if preview_info.file_size > MAX_RECOVERY_PREVIEW_BYTES:
        _project_error(
            f"Recovery preview exceeds {MAX_RECOVERY_PREVIEW_BYTES:,} bytes"
        )
    allowed_members.add(RECOVERY_PREVIEW_MEMBER)


def validate_project_archive(zf, archive_path=None):
    """Validate archive resources and schema before any editor state changes."""
    if archive_path is not None:
        size = os.path.getsize(os.fspath(archive_path))
        if size > MAX_PROJECT_FILE_BYTES:
            _project_error(
                f"Project file exceeds the {MAX_PROJECT_FILE_BYTES:,} byte limit"
            )

    infos = zf.infolist()
    if len(infos) > MAX_PROJECT_MEMBERS:
        _project_error(f"Project exceeds {MAX_PROJECT_MEMBERS} archive members")
    names = [info.filename for info in infos]
    folded_names = [name.casefold() for name in names]
    if len(set(folded_names)) != len(folded_names):
        _project_error("Project archive contains duplicate member names")

    expanded = 0
    allowed_compression = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
    for info in infos:
        name = info.filename
        if (not name or info.is_dir() or "\\" in name or name.startswith("/") or
                any(part in ("", ".", "..") for part in name.split("/"))):
            _project_error(f"Unsafe project archive member: {name!r}")
        if info.flag_bits & 0x1:
            _project_error(f"Encrypted project member is not supported: {name}")
        if info.compress_type not in allowed_compression:
            _project_error(f"Unsupported ZIP compression for {name}")
        if info.file_size > MAX_PROJECT_MEMBER_BYTES:
            _project_error(
                f"Project member {name} exceeds {MAX_PROJECT_MEMBER_BYTES:,} bytes"
            )
        expanded += info.file_size
        if expanded > MAX_PROJECT_EXPANDED_BYTES:
            _project_error(
                f"Project expands beyond {MAX_PROJECT_EXPANDED_BYTES:,} bytes"
            )

    names_set = set(names)
    infos_by_name = {info.filename: info for info in infos}
    if "project.json" not in names_set:
        _project_error("Project is missing project.json")
    json_info = zf.getinfo("project.json")
    if json_info.file_size > MAX_PROJECT_JSON_BYTES:
        _project_error(
            f"project.json exceeds {MAX_PROJECT_JSON_BYTES:,} bytes"
        )
    bad_member = zf.testzip()
    if bad_member:
        _project_error(f"Project archive CRC failed: {bad_member}")
    try:
        meta = json.loads(zf.read(json_info).decode("utf-8"))
    except Exception as error:
        raise ProjectValidationError(f"Invalid project.json: {error}") from error
    if not isinstance(meta, dict) or meta.get("magic") != "SWIFTSHOT_PROJECT":
        _project_error("Not a valid SwiftShot project")
    version = meta.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int):
        _project_error("Project version must be an integer")
    if version > 3:
        raise UnsupportedProjectVersion(
            f"Project version {version} is newer than supported version 3"
        )
    if version < 1:
        _project_error(f"Unsupported project version: {version}")
    meta["version"] = version
    layers = meta.get("layers")
    if not isinstance(layers, list) or not layers:
        _project_error("Project must contain at least one layer")
    if len(layers) > MAX_PROJECT_LAYERS:
        _project_error(f"Project exceeds {MAX_PROJECT_LAYERS} layers")
    active_index = meta.get("active_index", 0)
    _require_int(active_index, "active_index", 0, len(layers) - 1)

    allowed_members = {"project.json"}
    _validate_recovery_metadata(
        meta, names_set, infos_by_name, allowed_members
    )
    if version >= 3:
        counter = [0]
        for index, layer in enumerate(layers):
            _validate_v3_layer(
                layer, f"layer_{index}", names_set, allowed_members, counter, 1
            )
    else:
        _validate_legacy_layers(layers, names_set, allowed_members)
    unexpected = names_set - allowed_members
    if unexpected:
        _project_error(
            f"Project archive contains unexpected member: {sorted(unexpected)[0]}"
        )
    return meta, names_set


def load_project_image(zf, member_name, mode="RGBA", budget=None):
    try:
        info = zf.getinfo(member_name)
    except KeyError as error:
        raise ProjectValidationError(
            f"Project is missing {member_name}"
        ) from error
    try:
        payload = zf.read(info)
        return load_image(
            payload,
            mode=mode,
            allowed_formats={"PNG"},
            max_bytes=MAX_PROJECT_MEMBER_BYTES,
            budget=budget,
        )
    except SafeImageError as error:
        raise ProjectValidationError(
            f"Invalid project image {member_name}: {error}"
        ) from error
