def test_editor_palette_uses_shared_theme_roles(qapp):
    from editor import C, build_ss, init_ui_scale
    from theme import EDITOR_COLORS

    init_ui_scale(1)

    for role, color in EDITOR_COLORS.items():
        assert getattr(C, role) == color

    stylesheet = build_ss()
    for role in ("BG0", "BG1", "BG2", "TEXT_PRI", "ACCENT", "BORDER"):
        assert EDITOR_COLORS[role] in stylesheet


def _relative_luminance(hex_color):
    color = hex_color.lstrip("#")
    channels = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        channel / 12.92 if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground, background):
    fg = _relative_luminance(foreground)
    bg = _relative_luminance(background)
    lighter, darker = max(fg, bg), min(fg, bg)
    return (lighter + 0.05) / (darker + 0.05)


def test_dark_and_light_theme_roles_meet_wcag_text_contrast():
    from theme import DARK_COLORS, LIGHT_COLORS

    for colors in (DARK_COLORS, LIGHT_COLORS):
        for background in ("BG1", "BG2"):
            assert _contrast_ratio(colors["TEXT_PRI"], colors[background]) >= 4.5
            assert _contrast_ratio(colors["TEXT_SEC"], colors[background]) >= 4.5
        assert _contrast_ratio(colors["ACCENT"], colors["BG1"]) >= 4.5


def test_apply_theme_sets_palette_and_stylesheet(qapp):
    from PyQt5.QtGui import QPalette, QColor
    from theme import DARK_COLORS, LIGHT_COLORS, apply_theme, stylesheet_for_theme

    apply_theme(qapp, "light")
    assert qapp.palette().color(QPalette.Window) == QColor(LIGHT_COLORS["BG1"])
    assert LIGHT_COLORS["BG1"] in stylesheet_for_theme("light")

    apply_theme(qapp, "dark")
    assert qapp.palette().color(QPalette.Window) == QColor(DARK_COLORS["BG1"])
