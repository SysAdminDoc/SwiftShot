"""OCR language discovery, selection and remediation (R-30)."""

import sys
import types


def test_parse_lang_tags_dedupes_and_strips():
    import ocr
    out = ocr._parse_lang_tags("en-US\n  de-DE \nen-US\n\n")
    assert out == ["en-US", "de-DE"]


def test_parse_lang_tags_ignores_error_lines():
    import ocr
    assert ocr._parse_lang_tags("OCR_ERROR: boom\nfr-FR") == ["fr-FR"]


def test_parse_tesseract_langs_drops_header_and_osd():
    import ocr
    raw = "List of available languages (3):\neng\ndeu\nosd\n"
    assert ocr._parse_tesseract_langs(raw) == ["eng", "deu"]


def test_configured_language_defaults_auto(monkeypatch):
    import ocr
    # No config attribute -> "auto".
    fake = types.ModuleType("config")
    monkeypatch.setitem(sys.modules, "config", fake)
    assert ocr._configured_ocr_language() == "auto"


def test_configured_language_reads_config(monkeypatch):
    import ocr
    fake = types.ModuleType("config")
    fake.OCR_LANGUAGE = "de-DE"
    monkeypatch.setitem(sys.modules, "config", fake)
    assert ocr._configured_ocr_language() == "de-DE"


def test_language_status_prefers_selected_installed(monkeypatch):
    import ocr
    monkeypatch.setattr(ocr, "_configured_ocr_language", lambda: "de-DE")
    monkeypatch.setattr(ocr, "available_windows_ocr_languages",
                        lambda: ["en-US", "de-DE"])
    monkeypatch.setattr(ocr, "available_tesseract_languages", lambda: [])
    st = ocr.ocr_language_status()
    assert st["effective"] == "de-DE"
    assert st["windows"] == ["en-US", "de-DE"]


def test_language_status_falls_back_to_auto_first_installed(monkeypatch):
    import ocr
    monkeypatch.setattr(ocr, "_configured_ocr_language", lambda: "fr-FR")
    monkeypatch.setattr(ocr, "available_windows_ocr_languages", lambda: ["en-US"])
    monkeypatch.setattr(ocr, "available_tesseract_languages", lambda: [])
    st = ocr.ocr_language_status()
    assert st["effective"] == "auto (en-US)"   # requested not installed


def test_language_status_none_when_nothing_installed(monkeypatch):
    import ocr
    monkeypatch.setattr(ocr, "_configured_ocr_language", lambda: "auto")
    monkeypatch.setattr(ocr, "available_windows_ocr_languages", lambda: [])
    monkeypatch.setattr(ocr, "available_tesseract_languages", lambda: [])
    st = ocr.ocr_language_status()
    assert st["effective"] == "none"
    assert "language pack" in st["install_hint"]


def test_ocr_file_routes_tesseract_language(monkeypatch, tmp_path):
    import ocr
    monkeypatch.setattr(ocr, "_configured_ocr_language", lambda: "tesseract:deu")
    monkeypatch.setattr(ocr.sys, "platform", "win32")
    calls = {}

    def fake_tess(path, lang=None):
        calls["lang"] = lang
        return "guten tag"

    win_called = []
    monkeypatch.setattr(ocr, "_ocr_tesseract", fake_tess)
    monkeypatch.setattr(ocr, "_ocr_windows",
                        lambda *a, **k: win_called.append(True) or "")
    img = tmp_path / "x.png"
    img.write_bytes(b"")
    assert ocr.ocr_file(str(img)) == "guten tag"
    assert calls["lang"] == "deu"       # tesseract language threaded through
    assert win_called == []             # WinRT skipped for tesseract selection
