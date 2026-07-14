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


def test_editor_theme_rebinds_palette_and_stylesheet(qapp):
    """The editor used to be permanently dark: class C bound the dark set at
    import. apply_editor_theme('light') must repaint it (regression)."""
    import editor
    from theme import DARK_COLORS, LIGHT_COLORS

    try:
        editor.apply_editor_theme("light")
        assert editor.C.BG1 == LIGHT_COLORS["BG1"]
        assert editor.C.TEXT_PRI == LIGHT_COLORS["TEXT_PRI"]
        sheet = editor.build_ss()
        assert LIGHT_COLORS["BG1"] in sheet
        assert DARK_COLORS["BG1"] not in sheet
        assert "#1a1a1a" not in sheet          # slider handle border tokenized
    finally:
        editor.apply_editor_theme("dark")
    assert editor.C.BG1 == DARK_COLORS["BG1"]


def test_dark_and_light_theme_roles_meet_wcag_text_contrast():
    from theme import DARK_COLORS, LIGHT_COLORS

    for colors in (DARK_COLORS, LIGHT_COLORS):
        for background in ("BG1", "BG2"):
            assert _contrast_ratio(colors["TEXT_PRI"], colors[background]) >= 4.5
            assert _contrast_ratio(colors["TEXT_SEC"], colors[background]) >= 4.5
            assert _contrast_ratio(colors["TEXT_MUT"], colors[background]) >= 4.5
            assert _contrast_ratio(colors["BORDER"], colors[background]) >= 3.0
        assert _contrast_ratio(colors["ACCENT"], colors["BG1"]) >= 4.5


def test_light_stylesheet_borders_use_border_token():
    """Control borders must use the BORDER token in the light theme
    (regression: they mapped to a near-invisible pale hover color)."""
    from theme import LIGHT_COLORS, LIGHT_STYLESHEET

    assert f"solid {LIGHT_COLORS['BORDER']}" in LIGHT_STYLESHEET
    assert "solid #dbeafe" not in LIGHT_STYLESHEET


def test_apply_theme_sets_palette_and_stylesheet(qapp):
    from PyQt5.QtGui import QPalette, QColor
    from theme import DARK_COLORS, LIGHT_COLORS, apply_theme, stylesheet_for_theme

    apply_theme(qapp, "light")
    assert qapp.palette().color(QPalette.Window) == QColor(LIGHT_COLORS["BG1"])
    assert LIGHT_COLORS["BG1"] in stylesheet_for_theme("light")

    apply_theme(qapp, "dark")
    assert qapp.palette().color(QPalette.Window) == QColor(DARK_COLORS["BG1"])


def test_high_contrast_uses_native_system_palette(qapp, monkeypatch):
    from PyQt5.QtGui import QPalette
    import theme

    expected = qapp.style().standardPalette()
    monkeypatch.setattr(theme, "is_high_contrast_enabled", lambda: True)
    try:
        theme.apply_theme(qapp, "dark")
        assert qapp.styleSheet() == ""
        assert theme.stylesheet_for_theme("dark") == ""
        assert qapp.palette().color(QPalette.Window) == expected.color(QPalette.Window)
        colors = theme.colors_for_theme("dark")
        assert colors["TEXT_PRI"] == expected.color(QPalette.WindowText).name()
        assert colors["ACCENT"] == expected.color(QPalette.Highlight).name()
    finally:
        monkeypatch.setattr(theme, "is_high_contrast_enabled", lambda: False)
        theme.apply_theme(qapp, "dark")


def test_editor_high_contrast_does_not_override_native_styles(qapp, monkeypatch):
    from PyQt5.QtGui import QPalette
    import editor
    import theme

    monkeypatch.setattr(theme, "is_high_contrast_enabled", lambda: True)
    try:
        theme.apply_theme(qapp, "dark")
        editor.apply_editor_theme("dark")
        assert editor.build_ss() == ""
        assert editor.C.TEXT_PRI == qapp.palette().color(QPalette.WindowText).name()
        assert editor.C.ACCENT == qapp.palette().color(QPalette.Highlight).name()
    finally:
        monkeypatch.setattr(theme, "is_high_contrast_enabled", lambda: False)
        theme.apply_theme(qapp, "dark")
        editor.apply_editor_theme("dark")
