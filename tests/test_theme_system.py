"""System-following theme resolution (R-32)."""


def test_theme_labels_include_system(qapp):
    import theme
    assert "system" in theme.THEME_LABELS
    assert set(theme.THEME_LABELS) >= {"system", "dark", "light"}


def test_effective_theme_direct_values(qapp):
    import theme
    assert theme.effective_theme("dark") == "dark"
    assert theme.effective_theme("light") == "light"
    # Unknown normalizes to dark.
    assert theme.effective_theme("chartreuse") == "dark"


def test_effective_theme_system_follows_light(qapp, monkeypatch):
    import theme
    monkeypatch.setattr(theme, "windows_prefers_light", lambda: True)
    assert theme.effective_theme("system") == "light"


def test_effective_theme_system_follows_dark(qapp, monkeypatch):
    import theme
    monkeypatch.setattr(theme, "windows_prefers_light", lambda: False)
    assert theme.effective_theme("system") == "dark"


def test_colors_and_stylesheet_resolve_system(qapp, monkeypatch):
    import theme
    monkeypatch.setattr(theme, "windows_prefers_light", lambda: True)
    monkeypatch.setattr(theme, "is_high_contrast_enabled", lambda: False)
    assert theme.colors_for_theme("system") is theme.LIGHT_COLORS
    assert theme.stylesheet_for_theme("system") == theme.LIGHT_STYLESHEET
    monkeypatch.setattr(theme, "windows_prefers_light", lambda: False)
    assert theme.colors_for_theme("system") is theme.DARK_COLORS


def test_config_persists_system_theme(fresh_config):
    cfg = fresh_config.config
    cfg.THEME = "system"
    cfg._normalize_enums()
    assert cfg.THEME == "system"      # accepted, not reset to default


def test_config_rejects_invalid_theme(fresh_config):
    cfg = fresh_config.config
    cfg.THEME = "neon"
    cfg._normalize_enums()
    assert cfg.THEME in ("dark", "light", "system")   # coerced to a valid one
