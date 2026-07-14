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


def test_tesseract_decoder_is_closed(monkeypatch, tmp_path):
    image = object()

    class Decoder:
        entered = False
        exited = False

        def __enter__(self):
            self.entered = True
            return image

        def __exit__(self, *_args):
            self.exited = True

    decoder = Decoder()
    fake_tesseract = types.ModuleType("pytesseract")
    fake_tesseract.image_to_string = lambda value: (
        " extracted text " if value is image else "wrong image")
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tesseract)

    # _ocr_tesseract imports PIL.Image inside the function, so patch the
    # actual module object rather than an implementation-local alias.
    from PIL import Image
    monkeypatch.setattr(Image, "open", lambda *_args: decoder)

    assert ocr._ocr_tesseract(str(tmp_path / "image.png")) == "extracted text"
    assert decoder.entered is True
    assert decoder.exited is True


@pytest.mark.parametrize("entrypoint", [ocr.ocr_pixmap, ocr.ocr_words_pixmap])
def test_ocr_rejects_failed_temp_image_encoding(entrypoint):
    class _BadPixmap:
        @staticmethod
        def save(*_args):
            return False

    with pytest.raises(OSError, match="could not encode"):
        entrypoint(_BadPixmap())
