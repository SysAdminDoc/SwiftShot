def test_editor_palette_uses_shared_theme_roles(qapp):
    from editor import C, build_ss, init_ui_scale
    from theme import EDITOR_COLORS

    init_ui_scale(1)

    for role, color in EDITOR_COLORS.items():
        assert getattr(C, role) == color

    stylesheet = build_ss()
    for role in ("BG0", "BG1", "BG2", "TEXT_PRI", "ACCENT", "BORDER"):
        assert EDITOR_COLORS[role] in stylesheet
