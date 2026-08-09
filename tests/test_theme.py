"""Тести перемикача теми (без Streamlit-рантайму)."""

from unittest.mock import MagicMock

import theme


def test_themes_have_required_keys():
    required = {"bg", "text", "text_muted", "surface", "border", "sidebar", "input_bg"}
    assert set(theme.THEMES) == {"dark", "light"}
    for name, palette in theme.THEMES.items():
        assert required <= set(palette), f"{name}: бракує ключів {required - set(palette)}"


def test_default_theme_is_valid():
    assert theme.DEFAULT_THEME in theme.THEMES


def test_theme_css_uses_palette_values():
    for name, palette in theme.THEMES.items():
        css = theme.theme_css(name)
        assert palette["bg"] in css
        assert palette["surface"] in css
        assert ".stApp" in css


def test_theme_css_falls_back_on_unknown():
    assert theme.theme_css("несправжня") == theme.theme_css(theme.DEFAULT_THEME)


def test_theme_css_has_motion_layer():
    """UX-A8: рух, focus-visible та reduced-motion присутні в обох темах."""
    for name in theme.THEMES:
        css = theme.theme_css(name)
        assert "transition" in css                       # micro-interactions
        assert ":focus-visible" in css                   # WCAG 2.4.7 keyboard ring
        assert "prefers-reduced-motion" in css           # WCAG 2.3.3
        assert "fadeInUp" in css                          # одноразовий entrance
        assert "cubic-bezier(.16,1,.3,1)" in css          # крива, узгоджена з login


def test_theme_css_has_sidebar_standards_layer():
    """Стандарт секцій sidebar: h4-eyebrow, тонкі hr зон, акцентний metric,
    компактний вертикальний ритм — в обох темах."""
    for name in theme.THEMES:
        css = theme.theme_css(name)
        assert "text-transform: uppercase" in css                      # h4-eyebrow секцій
        assert 'div[data-testid="stSidebar"] hr' in css                # розділювачі зон
        assert 'div[data-testid="stSidebar"] [data-testid="stMetricValue"]' in css
        assert ".template-card h4" in css                              # картка не стає eyebrow
        assert 'div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"]' in css


def test_light_theme_secondary_button_override():
    css = theme.theme_css("light")
    assert "stBaseButton-secondary" in css
    assert theme.THEMES["light"]["surface"] in css
    assert theme.THEMES["light"]["text"] in css
    assert theme.theme_css("dark").count("stBaseButton-secondary") == 0


def test_native_theme_label():
    assert theme.native_theme_label("light") == "Light"
    assert theme.native_theme_label("dark") == "Dark"


def test_theme_sync_script_sets_localstorage_for_both():
    light_script = theme.theme_sync_script("light")
    assert "stActiveTheme-" in light_script
    assert '"Light"' in light_script
    assert "localStorage.setItem" in light_script
    assert "document.cookie" in light_script
    dark_script = theme.theme_sync_script("dark")
    assert '"Dark"' in dark_script
    assert "cur === null && want === 'Dark'" not in dark_script
    assert "document.cookie" in dark_script


def test_theme_sync_script_persists_cookie_key():
    """Cookie ui_theme переживає reload — інакше CSS/native знову роз’їдуться."""
    for name in ("light", "dark"):
        script = theme.theme_sync_script(name)
        assert theme.THEME_COOKIE in script
        assert f'"{name}"' in script


def test_theme_from_cookie_reads_valid(monkeypatch):
    cookies = MagicMock()
    cookies.get.return_value = "light"
    ctx = MagicMock()
    ctx.cookies = cookies
    monkeypatch.setattr(theme.st, "context", ctx)
    assert theme.theme_from_cookie() == "light"
    cookies.get.return_value = "bogus"
    assert theme.theme_from_cookie() is None


def test_light_theme_native_widget_overrides():
    css = theme.theme_css("light")
    assert '[data-testid="stExpander"]' in css
    assert '[data-baseweb="popover"]' in css
    assert theme.THEMES["light"]["bg"] in css


def test_dark_theme_native_widget_overrides():
    css = theme.theme_css("dark")
    assert '[data-testid="stExpander"]' in css
    assert '[data-baseweb="popover"]' in css
    assert theme.THEMES["dark"]["bg"] in css
    assert theme.THEMES["dark"]["surface"] in css


def test_light_badge_colors_readable():
    css = theme.theme_css("light")
    assert "#047857" in css
    assert theme.theme_css("dark").count("#047857") == 0
