"""Тести rarity_report — EN-категорії у frequency table (BUG-023)."""

from services.rarity_report import skewed_traits, summarize_collection


def test_trait_frequency_uses_english_categories():
    assets = [
        {"name": "#1", "traits": {"Голова / Шолом / Маска": "crown", "Фон / Аура": "neon"}},
        {"name": "#2", "traits": {"Голова / Шолом / Маска": "helm", "Фон / Аура": "space"}},
    ]
    summary = summarize_collection(assets)
    assert summary is not None
    cats = {row["category"] for row in summary["trait_rows"]}
    assert "Head / Helmet / Mask" in cats
    assert "Background / Aura" in cats
    assert not any("Голова" in c for c in cats)


def test_skewed_traits_detects_dominant_trait():
    assets = [
        {"name": f"#{i}", "traits": {"Color": "red" if i < 8 else "blue"}}
        for i in range(10)
    ]
    skewed = skewed_traits(assets, threshold_pct=50.0)
    assert len(skewed) == 1
    assert skewed[0]["trait"] == "red"
    assert skewed[0]["pct"] == 80.0
