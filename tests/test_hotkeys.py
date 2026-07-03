import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="hotkeys module is Windows-only"
)


def _parse(combo):
    from hotkeys import HotkeyManager

    return HotkeyManager()._parse_combo(combo)


def test_parse_combo_print_variants():
    from hotkeys import MOD_ALT, MOD_CTRL, MOD_SHIFT

    assert _parse("Print") == (0, 0x2C)
    assert _parse("Alt+Print") == (MOD_ALT, 0x2C)
    assert _parse("Ctrl+Print") == (MOD_CTRL, 0x2C)
    assert _parse("Shift+Print") == (MOD_SHIFT, 0x2C)


def test_parse_combo_supports_every_recorder_key_name():
    """Every key name the settings recorder can produce must resolve,
    or the recorded binding silently never fires (regression)."""
    from settings_dialog import HotkeyRecorderWidget

    recorder_names = set(HotkeyRecorderWidget._VK_NAMES.values())
    for name in recorder_names:
        mods, vk = _parse(f"Ctrl+{name}")
        assert vk is not None, f"recorder key name {name!r} not parseable"


def test_parse_combo_letters_and_digits():
    assert _parse("Ctrl+S")[1] == ord("S")
    assert _parse("Ctrl+5")[1] == ord("5")
    assert _parse("Ctrl+Shift+F5")[1] == 0x74


def test_parse_combo_unknown_key_returns_none():
    assert _parse("Ctrl+NotAKey")[1] is None
