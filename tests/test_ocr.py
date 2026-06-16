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
