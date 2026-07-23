"""Tests for the optional AI (rembg) model-cache disclosure helpers and the
honest-naming guarantees for the local heuristic tools (R-28).

The editor imports PyQt at module load, so these use the offscreen qapp
fixture but never build the full ImageEditor — they exercise the pure
module-level cache helpers and read the menu-builder source for label honesty.
"""


def _editor(qapp):
    import editor
    return editor


def test_cache_dir_honours_u2net_home(qapp, monkeypatch, tmp_path):
    ed = _editor(qapp)
    monkeypatch.setenv("U2NET_HOME", str(tmp_path))
    assert ed.rembg_cache_dir() == str(tmp_path)


def test_cache_dir_default_is_dot_u2net(qapp, monkeypatch):
    ed = _editor(qapp)
    monkeypatch.delenv("U2NET_HOME", raising=False)
    d = ed.rembg_cache_dir()
    assert d.endswith(".u2net")


def test_cache_info_empty_when_absent(qapp, monkeypatch, tmp_path):
    ed = _editor(qapp)
    monkeypatch.setenv("U2NET_HOME", str(tmp_path / "missing"))
    present, path, size, files = ed.rembg_cache_info()
    assert present is False
    assert size == 0
    assert files == []
    assert ed.rembg_model_present() is False


def test_cache_info_and_clear(qapp, monkeypatch, tmp_path):
    ed = _editor(qapp)
    monkeypatch.setenv("U2NET_HOME", str(tmp_path))
    # Two model files plus an unrelated file that must be ignored.
    (tmp_path / "u2net.onnx").write_bytes(b"x" * 2048)
    (tmp_path / "silueta.onnx").write_bytes(b"y" * 1024)
    (tmp_path / "notes.txt").write_text("ignore me")

    present, path, size, files = ed.rembg_cache_info()
    assert present is True
    assert size == 3072
    assert files == ["silueta.onnx", "u2net.onnx"]
    assert ed.rembg_model_present() is True

    removed = ed.clear_rembg_cache()
    assert removed == 2
    assert ed.rembg_model_present() is False
    # Non-model file survives.
    assert (tmp_path / "notes.txt").exists()


def test_human_size_units(qapp):
    ed = _editor(qapp)
    assert ed._human_size(0) == "0 B"
    assert ed._human_size(1023) == "1023 B"
    assert ed._human_size(1024).endswith("KB")
    assert ed._human_size(170 * 1024 * 1024).startswith("170")
    assert ed._human_size(170 * 1024 * 1024).endswith("MB")


def test_heuristic_tools_named_honestly(qapp):
    """The Enhance menu and command palette must not label the local
    heuristics as 'AI' / 'Smart' / real object detection."""
    import inspect
    from editor import ImageEditor

    src = inspect.getsource(ImageEditor)
    # Dishonest legacy labels are gone.
    assert "Smart Upscale" not in src
    assert "Detect Objects" not in src
    assert "AI Object Detection" not in src
    assert "Generate Depth Map" not in src
    # Honest replacements are present.
    assert "Lanczos" in src
    assert "heuristic" in src
    # Only the genuinely-trained tool keeps an AI-model label.
    assert "Remove Background (AI model)" in src
