"""Atomic editor recovery-journal discovery and lifecycle helpers."""

import io
import os
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

from logger import log
from safe_io import (
    MAX_RECOVERY_NAME_LENGTH,
    MAX_RECOVERY_PREVIEW_BYTES,
    RECOVERY_PREVIEW_MEMBER,
    load_image,
    validate_project_archive,
)


RECOVERY_IDLE_MS = 5_000
RECOVERY_MAX_INTERVAL_MS = 60_000
RECOVERY_PREVIEW_SIZE = (480, 320)


@dataclass(frozen=True)
class RecoveryEntry:
    path: str
    document_name: str
    saved_at: str
    preview_png: bytes


def _config_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "SwiftShot")


def recovery_directory(config_dir=None):
    return os.path.join(config_dir or _config_dir(), "Recovery")


def new_recovery_path(config_dir=None):
    directory = recovery_directory(config_dir)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{uuid.uuid4().hex}.swiftshot")


def safe_document_name(value):
    name = str(value or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in (".", ".."):
        name = "Untitled capture"
    return name[:MAX_RECOVERY_NAME_LENGTH]


def recovery_metadata(document_name, saved_at=None):
    stamp = saved_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "magic": "SWIFTSHOT_RECOVERY",
        "version": 1,
        "document_name": safe_document_name(document_name),
        "saved_at": stamp,
    }


def encode_preview(image):
    """Return a small metadata-free PNG suitable for the startup prompt."""
    preview = image.convert("RGBA").copy()
    preview.thumbnail(RECOVERY_PREVIEW_SIZE)
    buffer = io.BytesIO()
    preview.save(buffer, "PNG", optimize=True)
    payload = buffer.getvalue()
    if len(payload) > MAX_RECOVERY_PREVIEW_BYTES:
        raise ValueError("Recovery preview exceeds its byte limit")
    return payload


def _normalized_preview(archive):
    payload = archive.read(RECOVERY_PREVIEW_MEMBER)
    image = load_image(
        payload,
        allowed_formats={"PNG"},
        max_bytes=MAX_RECOVERY_PREVIEW_BYTES,
    )
    if (image.width > RECOVERY_PREVIEW_SIZE[0] or
            image.height > RECOVERY_PREVIEW_SIZE[1]):
        raise ValueError("Recovery preview dimensions are invalid")
    return encode_preview(image)


def quarantine_recovery(path, config_dir=None):
    """Move a corrupt journal aside, returning its quarantine path or None."""
    directory = os.path.join(recovery_directory(config_dir), "Quarantine")
    try:
        os.makedirs(directory, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = os.path.join(
            directory,
            f"{os.path.basename(path)}.{stamp}.{uuid.uuid4().hex[:8]}.corrupt",
        )
        os.replace(path, target)
        return target
    except OSError:
        log.warning("Could not quarantine corrupt recovery journal: %s", path,
                    exc_info=True)
        return None


def scan_recovery_journals(config_dir=None):
    """Return valid entries and quarantined paths; corrupt data never escapes."""
    directory = recovery_directory(config_dir)
    if not os.path.isdir(directory):
        return [], []
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        log.warning("Could not inspect recovery directory: %s", directory,
                    exc_info=True)
        return [], []
    entries = []
    quarantined = []
    for name in names:
        path = os.path.join(directory, name)
        if not name.endswith(".swiftshot") or not os.path.isfile(path):
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                metadata, _names = validate_project_archive(archive, path)
                recovery = metadata.get("recovery")
                if recovery is None:
                    raise ValueError("Project is not a recovery journal")
                preview_png = _normalized_preview(archive)
            entries.append(RecoveryEntry(
                path=path,
                document_name=recovery["document_name"],
                saved_at=recovery["saved_at"],
                preview_png=preview_png,
            ))
        except Exception:
            log.warning("Recovery journal is corrupt: %s", path, exc_info=True)
            quarantined_path = quarantine_recovery(path, config_dir)
            if quarantined_path:
                quarantined.append(quarantined_path)
    entries.sort(key=lambda entry: entry.saved_at, reverse=True)
    return entries, quarantined


def discard_recovery(path):
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        log.warning("Could not remove recovery journal: %s", path, exc_info=True)
        return False
