from PIL import Image, features
from PyQt5.QtGui import QColor, QImage, QPixmap


def _sample_pixmap(width=320, height=180):
    image = QImage(width, height, QImage.Format_RGBA8888)
    for y in range(height):
        for x in range(width):
            block = ((x // 32) + (y // 32)) % 2
            red = (x * 3 + y) % 256
            green = (x + y * 2) % 256
            blue = 72 if block else 176
            image.setPixelColor(x, y, QColor(red, green, blue, 255))
    return QPixmap.fromImage(image)


def test_output_format_choices_include_webp():
    from config import OUTPUT_FILE_FORMAT_CHOICES

    assert "webp" in OUTPUT_FILE_FORMAT_CHOICES


def test_settings_format_dropdown_includes_webp(qapp):
    from settings_dialog import SettingsDialog

    dialog = SettingsDialog()

    assert dialog.file_format.findText("webp") >= 0


def test_save_pixmap_writes_lossless_webp(qapp, tmp_path):
    from utils import save_pixmap

    assert features.check("webp")

    pixmap = _sample_pixmap()
    png_path = tmp_path / "capture.png"
    webp_path = tmp_path / "capture.webp"

    assert save_pixmap(pixmap, str(png_path), "png")
    assert save_pixmap(pixmap, str(webp_path), "webp")

    saved = Image.open(webp_path)
    assert saved.format == "WEBP"
    assert saved.size == (pixmap.width(), pixmap.height())
    assert webp_path.stat().st_size < png_path.stat().st_size


def test_save_pixmap_writes_avif_when_supported(qapp, tmp_path):
    import pytest
    from utils import save_pixmap

    if not features.check("avif"):
        pytest.skip("Pillow built without AVIF")

    from config import OUTPUT_FILE_FORMAT_CHOICES
    assert "avif" in OUTPUT_FILE_FORMAT_CHOICES

    pixmap = _sample_pixmap()
    avif_path = tmp_path / "capture.avif"
    assert save_pixmap(pixmap, str(avif_path), "avif")

    saved = Image.open(avif_path)
    assert saved.format == "AVIF"
    assert saved.size == (pixmap.width(), pixmap.height())
