import sys
import types

import pytest

import ocr


def test_ocr_file_reports_missing_engines(monkeypatch, tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"placeholder")
    monkeypatch.setattr(ocr.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "pytesseract", None)

    with pytest.raises(RuntimeError) as exc_info:
        ocr.ocr_file(str(image_path))

    message = str(exc_info.value)
    assert "Windows OCR: Not on Windows" in message
    assert "Tesseract OCR: pytesseract not installed" in message


def test_is_ocr_available_detects_tesseract(monkeypatch):
    monkeypatch.setattr(ocr.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "pytesseract", types.ModuleType("pytesseract"))

    assert ocr.is_ocr_available() is True


def test_windows_ocr_empty_output_is_valid_result(monkeypatch, tmp_path):
    """A clean exit with no text means 'no text found', not an engine
    failure (regression: it surfaced an install-Tesseract error dialog)."""

    class FakeResult:
        returncode = 0
        stdout = "\n"
        stderr = ""

    monkeypatch.setattr(ocr.subprocess, "run", lambda *a, **kw: FakeResult())

    assert ocr._ocr_windows(str(tmp_path / "img.png")) == ""


def test_windows_ocr_error_marker_raises(monkeypatch, tmp_path):
    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "OCR_ERROR: No OCR engine available for your language settings."

    monkeypatch.setattr(ocr.subprocess, "run", lambda *a, **kw: FakeResult())

    with pytest.raises(RuntimeError, match="No OCR engine available"):
        ocr._ocr_windows(str(tmp_path / "img.png"))
