from pathlib import Path

import pytest


def _temps_for(target):
    return list(target.parent.glob(f".{target.name}.*.tmp"))


def test_atomic_replace_preserves_destination_on_write_failure(tmp_path):
    from utils import atomic_replace

    target = tmp_path / "capture.png"
    target.write_bytes(b"last-good")

    def fail_after_partial_write(temp_path):
        Path(temp_path).write_bytes(b"partial")
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        atomic_replace(target, fail_after_partial_write)

    assert target.read_bytes() == b"last-good"
    assert _temps_for(target) == []


def test_atomic_replace_validates_before_publish(tmp_path):
    from utils import atomic_replace

    target = tmp_path / "project.swiftshot"
    target.write_bytes(b"last-good")

    def write(temp_path):
        Path(temp_path).write_bytes(b"invalid")

    def reject(_temp_path):
        raise ValueError("verification failed")

    with pytest.raises(ValueError, match="verification failed"):
        atomic_replace(target, write, reject)

    assert target.read_bytes() == b"last-good"
    assert _temps_for(target) == []


def test_atomic_replace_publishes_verified_payload(tmp_path):
    from utils import atomic_replace

    target = tmp_path / "history.png"
    target.write_bytes(b"old")
    verified = []

    def write(temp_path):
        Path(temp_path).write_bytes(b"new")

    def verify(temp_path):
        assert Path(temp_path).read_bytes() == b"new"
        verified.append(True)

    atomic_replace(target, write, verify)

    assert verified == [True]
    assert target.read_bytes() == b"new"
    assert _temps_for(target) == []
