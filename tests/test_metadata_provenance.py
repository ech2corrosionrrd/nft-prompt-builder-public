from metadata_provenance import (
    TRAIT_GENERATION_ENGINE,
    TRAIT_PROMPT_HASH,
    TRAIT_RARITY_RANK,
    TRAIT_RARITY_SCORE,
    TRAIT_RARITY_TIER,
    add_rarity_ranks,
    prompt_hash,
    provenance_attributes,
    rarity_tier,
)


def test_rarity_tier_unique():
    assert rarity_tier(1, 1) == "Unique"


def test_rarity_tier_legendary_top_percent():
    assert rarity_tier(1, 100) == "Legendary"
    assert rarity_tier(5, 100) == "Epic"
    assert rarity_tier(15, 100) == "Rare"
    assert rarity_tier(35, 100) == "Uncommon"
    assert rarity_tier(80, 100) == "Common"


def test_add_rarity_ranks_orders_by_score():
    rows = [
        {"id": 1, "traits": {"a": "x"}, "rarity_score": 2.0},
        {"id": 2, "traits": {"a": "y"}, "rarity_score": 5.0},
        {"id": 3, "traits": {"a": "z"}, "rarity_score": 3.0},
    ]
    add_rarity_ranks(rows)
    assert rows[1]["rarity_rank"] == 1
    assert rows[2]["rarity_rank"] == 2
    assert rows[0]["rarity_rank"] == 3
    assert rows[1]["rarity_tier"] == "Uncommon"


def test_provenance_attributes_full():
    row = {
        "rarity_score": 4.5,
        "rarity_rank": 2,
        "rarity_total": 100,
        "rarity_tier": "Epic",
        "engine": "Flux.1 (Replicate)",
        "generated_at": "2026-06-12",
        "prompt": "cyber fox",
    }
    types = {a["trait_type"] for a in provenance_attributes(row)}
    assert TRAIT_RARITY_SCORE in types
    assert TRAIT_RARITY_RANK in types
    assert TRAIT_RARITY_TIER in types
    assert TRAIT_GENERATION_ENGINE in types
    assert TRAIT_PROMPT_HASH in types


def test_prompt_hash_stable():
    assert prompt_hash("fox") == prompt_hash("fox")
    assert len(prompt_hash("test")) == 16


def test_mint_attributes_includes_provenance():
    from i18n import mint_attributes

    row = {
        "traits": {"Style": "pixel"},
        "rarity_score": 3.0,
        "rarity_rank": 1,
        "rarity_total": 10,
        "rarity_tier": "Legendary",
        "prompt": "fox, pixel art",
    }
    types = [a["trait_type"] for a in mint_attributes(row)]
    assert "Style" in types
    assert TRAIT_RARITY_SCORE in types
    assert TRAIT_PROMPT_HASH in types


def test_build_metadata_adds_rarity_traits():
    from batch import add_rarity_scores, build_metadata

    rows = [
        {"id": 1, "traits": {"Head": "crown"}},
        {"id": 2, "traits": {"Head": "hat"}},
        {"id": 3, "traits": {"Head": "crown"}},
    ]
    add_rarity_scores(rows)
    meta = build_metadata(rows, "Apes")
    rank_traits = [a for a in meta[0]["attributes"] if a["trait_type"] == TRAIT_RARITY_RANK]
    assert rank_traits
    tier_traits = [a for a in meta[0]["attributes"] if a["trait_type"] == TRAIT_RARITY_TIER]
    assert tier_traits
