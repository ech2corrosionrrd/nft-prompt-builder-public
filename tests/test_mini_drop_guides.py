"""Тести мапінгу гайдів міні-дропів (без Streamlit)."""

from ui import mini_drop_guides


def test_all_mini_templates_have_guides():
    """Кожен публічний шаблон ~25 має i18n-гайд."""
    from templates import visible_templates

    for name in visible_templates(is_admin=False):
        if not mini_drop_guides.is_mini_drop(name):
            continue
        assert mini_drop_guides.guide_key(name), f"немає гайда для {name!r}"


def test_is_mini_drop_fine_art_one():
    assert mini_drop_guides.is_mini_drop("1/1 Fine Art")
    assert not mini_drop_guides.is_mini_drop("BAYC-style PFP")


def test_showcase_admin_has_guide():
    assert mini_drop_guides.guide_key("W3IR Showcase Demo") == "welcome.showcase_guide"
