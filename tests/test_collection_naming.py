"""Тести collection_naming (CN-1)."""

from services.collection_naming import (
    apply_naming,
    build_description,
    default_hashtags,
    token_name,
)


def test_token_name():
    assert token_name("Cyber Owls", 7) == "Cyber Owls #7"


def test_default_hashtags_includes_brand():
    tags = default_hashtags("Neon Drift")
    assert "#NeonDrift" in tags
    assert tags.count("#") >= 3


def test_build_description_with_tagline():
    desc = build_description("Alpha", 25, tagline="Custom lead.", hashtags="#NFT")
    assert desc.startswith("Custom lead.")
    assert "#NFT" in desc


def test_apply_naming_updates_all():
    assets = [{"name": "Token #1", "description": ""}, {"name": "x", "prompt": "p"}]
    out = apply_naming(assets, "Brand X", "Shared desc #NFT")
    assert out[0]["name"] == "Brand X #1"
    assert out[1]["name"] == "Brand X #2"
    assert out[0]["description"] == "Shared desc #NFT"
    assert assets[0]["name"] == "Token #1"
