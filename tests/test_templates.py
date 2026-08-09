"""Структурна валідація всіх вбудованих шаблонів колекцій.

Регресійний бар'єр: новий/змінений шаблон у `COLLECTION_TEMPLATES` має бути
самодостатнім — усі поля, які `app.apply_template` читає НАПРЯМУ (`tpl[field]`),
присутні, а значення-пресети збігаються з каталогами опцій (інакше selectbox
показує off-catalog значення, а `preset_label`/`style_description` не резолвлять).
"""

from __future__ import annotations

import pytest

from options import (
    ASPECT_RATIOS,
    BACKGROUNDS,
    CAMERA_ANGLES,
    LIGHTING,
    MOODS,
    QUALITY_TIERS,
)
from styles import NFT_STYLES
from templates import ADMIN_ONLY_TEMPLATES, COLLECTION_TEMPLATES, template_archetype, template_description, template_supply_badge_args, visible_templates

# Поля, до яких apply_template звертається напряму (без .get) — обов'язкові.
REQUIRED_FIELDS = (
    "label", "description", "description_en", "idea", "style", "camera", "lighting",
    "background", "quality", "mood", "aspect_ratio", "stylize", "chaos",
    "collection_size",
)

# Поле-пресет → каталог допустимих значень (для resolve підписів/описів).
CATALOG_FIELDS = {
    "style": NFT_STYLES,
    "camera": CAMERA_ANGLES,
    "lighting": LIGHTING,
    "background": BACKGROUNDS,
    "quality": QUALITY_TIERS,
    "mood": MOODS,
    "aspect_ratio": ASPECT_RATIOS,
}

_NAMES = sorted(COLLECTION_TEMPLATES)


@pytest.mark.parametrize("name", _NAMES)
def test_template_has_required_fields(name):
    tpl = COLLECTION_TEMPLATES[name]
    missing = [f for f in REQUIRED_FIELDS if f not in tpl]
    assert not missing, f"{name}: бракує полів {missing}"


@pytest.mark.parametrize("name", _NAMES)
def test_template_preset_values_in_catalog(name):
    tpl = COLLECTION_TEMPLATES[name]
    for field, catalog in CATALOG_FIELDS.items():
        assert tpl[field] in catalog, (
            f"{name}: {field}={tpl[field]!r} немає в каталозі опцій"
        )


@pytest.mark.parametrize("name", _NAMES)
def test_template_has_archetype(name):
    tpl = COLLECTION_TEMPLATES[name]
    assert tpl.get("archetype")
    assert template_archetype(tpl) in {
        "pfp", "abstract_geometric", "brand_icon", "landscape", "event_badge", "fine_art",
    }


@pytest.mark.parametrize("name", _NAMES)
def test_template_numeric_fields_sane(name):
    tpl = COLLECTION_TEMPLATES[name]
    assert isinstance(tpl["collection_size"], int) and tpl["collection_size"] >= 1
    assert isinstance(tpl["stylize"], int) and tpl["stylize"] >= 0
    assert isinstance(tpl["chaos"], int) and 0 <= tpl["chaos"] <= 100


@pytest.mark.parametrize("name", _NAMES)
def test_template_traits_shape(name):
    """traits опційні, але якщо є — це dict[str, list[str]] з непорожніми списками."""
    traits = COLLECTION_TEMPLATES[name].get("traits")
    if traits is None:
        return
    assert isinstance(traits, dict)
    for cat, opts in traits.items():
        assert isinstance(cat, str) and cat
        assert isinstance(opts, list) and opts
        assert all(isinstance(o, str) and o for o in opts)


def test_admin_only_templates_exist():
    assert ADMIN_ONLY_TEMPLATES <= set(COLLECTION_TEMPLATES)


def test_visible_templates_gate_admin_only():
    public = visible_templates(is_admin=False)
    admin = visible_templates(is_admin=True)
    assert ADMIN_ONLY_TEMPLATES.isdisjoint(public)
    assert ADMIN_ONLY_TEMPLATES <= set(admin)
    # Звичайний користувач бачить решту (всі мінус admin-only).
    assert set(public) == set(COLLECTION_TEMPLATES) - ADMIN_ONLY_TEMPLATES


def test_template_supply_badge_args_tiers():
    assert template_supply_badge_args(25) == {"kind": "mini", "short": "~25"}
    assert template_supply_badge_args(100) == {"kind": "mini", "short": "~100"}
    assert template_supply_badge_args(500) is None
    assert template_supply_badge_args(1000) == {"kind": "large", "short": "1k+"}
    assert template_supply_badge_args(9999) == {"kind": "large", "short": "10k+"}


def test_large_public_templates_have_large_badge():
    """Публічні PFP-шаблони з supply ≥1k мають large-badge (sidebar UX)."""
    for name in visible_templates(is_admin=False):
        size = COLLECTION_TEMPLATES[name]["collection_size"]
        if name in (
            "Abstract Geometry Series",
            "Brand Icon System",
            "Atmospheric Worlds",
            "Event Badge Series",
        ):
            assert template_supply_badge_args(size)["kind"] == "mini"
        elif size >= 1000:
            assert template_supply_badge_args(size)["kind"] == "large"


@pytest.mark.parametrize("name", _NAMES)
def test_template_descriptions_bilingual(name):
    tpl = COLLECTION_TEMPLATES[name]
    uk = template_description(tpl, "uk")
    en = template_description(tpl, "en")
    assert len(uk) >= 30, f"{name}: uk description too short"
    assert len(en) >= 30, f"{name}: en description too short"
    assert uk != en, f"{name}: uk/en descriptions must differ"
