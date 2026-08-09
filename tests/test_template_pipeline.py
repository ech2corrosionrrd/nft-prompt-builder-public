"""Тести auto-seed Stage 1 з шаблону (ПЛАН_NFT_РЕЗУЛЬТАТ.md § A5)."""

from services import template_pipeline
from templates import COLLECTION_TEMPLATES


def test_prompts_from_bayc_template_is_matrix():
    tpl = COLLECTION_TEMPLATES["BAYC-style PFP"]
    prompts = template_pipeline.prompts_from_template(tpl)
    assert len(prompts) > 1
    assert all("prompt" in p for p in prompts)


def test_prompts_from_fine_art_template_is_single():
    tpl = COLLECTION_TEMPLATES["1/1 Fine Art"]
    prompts = template_pipeline.prompts_from_template(tpl)
    assert len(prompts) == 1
    assert tpl["idea"].split()[0].lower() in prompts[0]["prompt"].lower() or prompts[0]["core"]


def test_bible_from_template_maps_fields():
    tpl = COLLECTION_TEMPLATES["Cyberpunk PFP"]
    bible = template_pipeline.bible_from_template(tpl)
    assert bible.style == tpl["style"]
    assert bible.lighting == tpl["lighting"]
    assert bible.camera == tpl["camera"]
    assert bible.background_rule == tpl["background"]


def test_abstract_geometry_template_yields_25_matrix_prompts():
    tpl = COLLECTION_TEMPLATES["Abstract Geometry Series"]
    prompts = template_pipeline.prompts_from_template(tpl)
    assert len(prompts) == 25
    assert tpl["collection_size"] == 25
    assert tpl.get("archetype") == "abstract_geometric"
    assert all("prompt" in p for p in prompts)


def test_brand_icon_template_yields_25_matrix_prompts():
    tpl = COLLECTION_TEMPLATES["Brand Icon System"]
    prompts = template_pipeline.prompts_from_template(tpl)
    assert len(prompts) == 25
    assert tpl["collection_size"] == 25
    assert "Flat UI / App Icon Design" in tpl["style"]
    assert all("prompt" in p for p in prompts)


def test_atmospheric_worlds_template_yields_25_matrix_prompts():
    tpl = COLLECTION_TEMPLATES["Atmospheric Worlds"]
    prompts = template_pipeline.prompts_from_template(tpl)
    assert len(prompts) == 25
    assert tpl.get("archetype") == "landscape"
    assert all("prompt" in p for p in prompts)


def test_event_badge_template_yields_25_matrix_prompts():
    tpl = COLLECTION_TEMPLATES["Event Badge Series"]
    prompts = template_pipeline.prompts_from_template(tpl)
    assert len(prompts) == 25
    assert tpl.get("archetype") == "event_badge"
    assert all("prompt" in p for p in prompts)


def test_suffix_preset_for_archetype_templates():
    abstract = COLLECTION_TEMPLATES["Abstract Geometry Series"]
    assert template_pipeline.suffix_preset_for_template(abstract) == "geometric"
    brand = COLLECTION_TEMPLATES["Brand Icon System"]
    assert template_pipeline.suffix_preset_for_template(brand) == "brand"
    event = COLLECTION_TEMPLATES["Event Badge Series"]
    assert template_pipeline.suffix_preset_for_template(event) == "event_badge"
    fine = COLLECTION_TEMPLATES["1/1 Fine Art"]
    assert template_pipeline.suffix_preset_for_template(fine) == "fine_art"


def test_archetype_session_hints_keys():
    tpl = COLLECTION_TEMPLATES["Abstract Geometry Series"]
    hints = template_pipeline.archetype_session_hints(tpl)
    assert hints["_pl2_archetype"] == "abstract_geometric"
    assert hints["pl2_suffix_preset"] == "geometric"
    assert "human" in hints["_pl2_archetype_negative"].lower()


def test_classic_trait_lines_from_abstract_template():
    tpl = COLLECTION_TEMPLATES["Abstract Geometry Series"]
    lines = template_pipeline.classic_trait_lines_from_template(tpl)
    assert "sphere with a smooth gradient" in lines["Аксесуари / Зброя"]
    assert "deep black void" in lines["Фон / Аура"]


def test_classic_trait_lines_from_bayc_template():
    tpl = COLLECTION_TEMPLATES["BAYC-style PFP"]
    lines = template_pipeline.classic_trait_lines_from_template(tpl)
    assert "gold crown" in lines["Голова / Шолом / Маска"]
    assert lines["Очі / Окуляри"]


def test_matrix_categories_from_abstract_template():
    tpl = COLLECTION_TEMPLATES["Abstract Geometry Series"]
    cats = template_pipeline.matrix_categories_from_template(tpl)
    assert len(cats["Варіанти аксесуарів"]) == 5
    assert len(cats["Варіанти фону"]) == 5


def test_ui_session_from_template_sets_matrix_and_style():
    tpl = COLLECTION_TEMPLATES["Brand Icon System"]
    state = template_pipeline.ui_session_from_template(tpl)
    assert state["pl1_style_matrix"] == tpl["style"]
    assert state["pl1_matrix_Варіанти аксесуарів"]
    # Базовий об'єкт більше НЕ вісь матриці: він фіксована частина промпту
    # (base_object_from_template), інакше зникав би там, де вісь «персонажа»
    # зайнята власними значеннями шаблону.
    assert tpl["idea"] not in state["pl1_matrix_Варіанти персонажа"]
    assert template_pipeline.base_object_from_template(tpl) == tpl["base_object"]


def test_prompts_count_matches_matrix_size():
    """prompts_from_template і matrix_categories_from_template — одне джерело."""
    from services import prompt_service

    for name in (
        "Abstract Geometry Series",
        "Atmospheric Worlds",
        "Brand Icon System",
        "Event Badge Series",
    ):
        tpl = COLLECTION_TEMPLATES[name]
        cats = template_pipeline.matrix_categories_from_template(tpl)
        prompts = template_pipeline.prompts_from_template(tpl)
        assert len(prompts) == prompt_service.matrix_size(cats), name
        assert len(prompts) == tpl["collection_size"], name


def test_bayc_prompts_match_matrix_not_supply_cap():
    """Generative PFP: матриця traits, collection_size — цільовий supply, не len(prompts)."""
    from services import prompt_service

    tpl = COLLECTION_TEMPLATES["BAYC-style PFP"]
    cats = template_pipeline.matrix_categories_from_template(tpl)
    prompts = template_pipeline.prompts_from_template(tpl)
    assert len(prompts) == prompt_service.matrix_size(cats)
    assert len(prompts) > 1
    assert tpl["collection_size"] > len(prompts)


def test_landscape_idea_not_in_character_axis_when_scenes_present():
    tpl = COLLECTION_TEMPLATES["Atmospheric Worlds"]
    cats = template_pipeline.matrix_categories_from_template(tpl)
    char_key = "Варіанти персонажа"
    assert char_key not in cats or tpl["idea"] not in cats.get(char_key, [])
    assert len(cats["Варіанти персонажа"]) == 5


def test_widget_keys_from_template_matrix_mode():
    tpl = COLLECTION_TEMPLATES["Abstract Geometry Series"]
    keys = template_pipeline.widget_keys_from_template(tpl)
    assert keys["pl1_mode"] == "matrix"
    assert keys["build_idea"] == tpl["idea"]
    assert keys["build_style"] == tpl["style"]
