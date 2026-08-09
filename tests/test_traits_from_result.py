"""Тести парсингу traits з відповіді Конструктора."""

from i18n import TRAIT_CATEGORY_EN, trait_category_label
from options import TRAIT_CATEGORIES
from services.traits_from_result import parse_traits_from_content, resolve_trait_category


def test_resolve_canonical_and_aliases():
    assert resolve_trait_category("Голова / Шолом / Маска") == "Голова / Шолом / Маска"
    assert resolve_trait_category("Форма голови") == "Голова / Шолом / Маска"
    assert resolve_trait_category("тип меча") == "Аксесуари / Зброя"
    assert resolve_trait_category("Head / Helmet / Mask") == "Голова / Шолом / Маска"
    assert resolve_trait_category(TRAIT_CATEGORY_EN["Аксесуари / Зброя"]) == "Аксесуари / Зброя"
    assert resolve_trait_category(TRAIT_CATEGORY_EN["Емоція / Вираз обличчя"]) == "Емоція / Вираз обличчя"
    # legacy builder wording
    assert resolve_trait_category("Accessories / Weapons") == "Аксесуари / Зброя"
    assert resolve_trait_category("Emotion / Facial expression") == "Емоція / Вираз обличчя"
    assert resolve_trait_category("unknown xyz") is None


def test_trait_category_label_i18n():
    cat = TRAIT_CATEGORIES[0]
    assert trait_category_label(cat, "uk") == cat
    assert trait_category_label(cat, "en") == TRAIT_CATEGORY_EN[cat]


def test_parse_vertical_markdown_table():
    content = """
## Concept
```
cyber fox samurai
```
| Категорія | Варіанти |
| --- | --- |
| Голова / Шолом / Маска | шолом, маска, капюшон |
| Фон / Аура | неон, туман |
"""
    out = parse_traits_from_content(content)
    assert "Голова / Шолом / Маска" in out
    assert "шолом" in out["Голова / Шолом / Маска"]
    assert "Фон / Аура" in out
    assert set(out) <= set(TRAIT_CATEGORIES)


def test_parse_horizontal_traits_table_en():
    """LLM часто робить 6 колонок у заголовку — один ряд варіантів."""
    en = [TRAIT_CATEGORY_EN[c] for c in TRAIT_CATEGORIES]
    content = f"""
## Traits
| {en[0]} | {en[1]} | {en[2]} | {en[3]} | {en[4]} | {en[5]} |
| --- | --- | --- | --- | --- | --- |
| Oni mask, Steel kabuto | Laser eyes, Goggles | Robe, Plate armor | Katana, Pistol | Neon city, Mist | Stoic, Fierce |
"""
    out = parse_traits_from_content(content)
    assert len(out) == 6
    assert "Oni mask" in out["Голова / Шолом / Маска"]
    assert "Laser eyes" in out["Очі / Окуляри"]
    assert "Katana" in out["Аксесуари / Зброя"]


def test_parse_inline_bold_lines():
    content = """
**Head / Helmet / Mask**: Oni mask, Steel kabuto, Bamboo hat
**Eyes / Glasses**: Laser eyes, Cyber goggles
"""
    out = parse_traits_from_content(content)
    assert "Oni mask" in out["Голова / Шолом / Маска"]
    assert "Laser eyes" in out["Очі / Окуляри"]


def test_parse_bullet_sections_with_aliases():
    content = """
### Форма голови
- кругла
- кубічна

### Тип меча
- катана
- лазерний меч
"""
    out = parse_traits_from_content(content)
    assert "кругла" in out["Голова / Шолом / Маска"]
    assert "катана" in out["Аксесуари / Зброя"]


def test_parse_empty():
    assert parse_traits_from_content("") == {}
    assert parse_traits_from_content("no traits here") == {}
