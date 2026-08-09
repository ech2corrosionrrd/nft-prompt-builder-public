"""Тести трейтів (ui/traits_panel.py) та примітивів options, винесених з app.py."""

import options
from ui import traits_panel


def test_weights_to_lines_format():
    out = traits_panel.weights_to_lines({"Gold": 10, "Silver": 90})
    assert out == "Gold | 10\nSilver | 90"


def test_weights_to_lines_empty():
    assert traits_panel.weights_to_lines({}) == ""


def test_trait_key_stable_prefix():
    assert options.trait_key("Очі / Окуляри") == "trait_Очі / Окуляри"
    # детермінованість — той самий вхід дає той самий ключ
    assert options.trait_key("X") == options.trait_key("X")


def test_trait_categories_nonempty_unique():
    assert options.TRAIT_CATEGORIES
    assert len(options.TRAIT_CATEGORIES) == len(set(options.TRAIT_CATEGORIES))


def test_core_object_presets_include_english_and_random():
    assert "cyber samurai" in options.CORE_OBJECT_PRESETS
    assert options.RANDOM_IDEAS[0] in options.CORE_OBJECT_PRESETS


def test_engine_tag_presets_nonempty():
    assert options.ENGINE_TAG_PRESETS
    assert all("--ar" in tag for tag in options.ENGINE_TAG_PRESETS)


def test_matrix_trait_options_covers_storage_keys():
    opts = options.matrix_trait_options()
    for key in options.MATRIX_STORAGE_KEYS:
        assert key in opts
        assert len(opts[key]) >= 4


def test_matrix_trait_options_character_is_core_not_headgear():
    opts = options.matrix_trait_options()
    chars = opts["Варіанти персонажа"]
    acc = opts["Варіанти аксесуарів"]
    assert "cyber samurai" in chars
    assert "golden crown" not in chars
    assert "golden crown" in acc
    assert "золота корона" in acc or "viking helmet" in acc


def test_matrix_trait_options_includes_template_ideas():
    opts = options.matrix_trait_options()
    assert any("мавп" in v.lower() or "ape" in v.lower() for v in opts["Варіанти персонажа"])


def test_weights_to_lines_roundtrips_via_parse_trait_lines():
    """Вихід weights_to_lines читається parse_trait_lines (контракт двигуна)."""
    from batch import parse_trait_lines

    text = traits_panel.weights_to_lines({"Common": 70, "Rare": 30})
    parsed = parse_trait_lines(text)
    names = [name for name, _ in parsed]
    assert "Common" in names and "Rare" in names
