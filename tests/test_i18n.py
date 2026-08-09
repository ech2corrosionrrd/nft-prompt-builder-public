from i18n import default_mint_collection_name, mint_attributes, trait_type_en, TRAIT_CATEGORY_EN


def test_default_mint_collection_name_cyrillic():
    assert default_mint_collection_name("Кібер-мавпа") == "My Collection"
    assert default_mint_collection_name("") == "My Collection"


def test_default_mint_collection_name_latin():
    assert default_mint_collection_name("Cyber Apes") == "Cyber Apes"


def test_mint_attributes_prefers_llm():
    row = {
        "traits": {"Голова": "корона"},
        "attributes": [{"trait_type": "Head", "value": "crown"}],
    }
    assert mint_attributes(row) == [{"trait_type": "Head", "value": "crown"}]


def test_mint_attributes_fallback_maps_category():
    row = {"traits": {"Очі / Окуляри": "лазерні"}}
    assert mint_attributes(row) == [{"trait_type": "Eyes / Glasses", "value": "лазерні"}]


def test_trait_category_en_includes_archetype_categories():
    assert "Форма / Силует" in TRAIT_CATEGORY_EN
    assert "Сцена / Локація" in TRAIT_CATEGORY_EN


def test_trait_type_en_pipeline_matrix():
    assert trait_type_en("Варіанти персонажа") == "Character"
    assert trait_type_en("Варіанти фону") == "Background"


def test_trait_type_en_abstract_brand_landscape_event():
    assert trait_type_en("Форма / Силует") == "Form"
    assert trait_type_en("Сцена / Локація") == "Scene"
    assert trait_type_en("Рівень / Tier") == "Tier"
    assert trait_type_en("Подача / Контекст") == "Layout"


def test_matrix_categories_by_archetype(monkeypatch):
    from ui_strings import matrix_categories

    monkeypatch.setattr("ui_strings.ui_lang", lambda: "en")
    assert matrix_categories("abstract_geometric")[0] == "Form / silhouette"
    assert matrix_categories("landscape")[0] == "Scene / location"
    assert matrix_categories("pfp")[0] == "Character variants"


def test_trait_type_en_passthrough_latin():
    assert trait_type_en("Rarity") == "Rarity"
