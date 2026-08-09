"""Тести NFT quality suffix і композиції (ПЛАН_ЯКОСТІ.md § Q1.1)."""

from services.prompt_enhancer import (
    SUFFIX_PRESETS,
    apply_suffix,
    dynamic_preset,
    enhance,
    suffix_text,
)
from services.prompt_quality import DEFAULT_NEGATIVE, PromptQualityProfile


def test_suffix_text_known_and_unknown():
    assert suffix_text("pfp") == SUFFIX_PRESETS["pfp"]
    assert suffix_text("nope") == ""
    assert suffix_text("") == ""


def test_apply_suffix_appends():
    out = apply_suffix("cyber fox, neon", "high detail, no text")
    assert out == "cyber fox, neon, high detail, no text"


def test_apply_suffix_skips_duplicates_case_insensitive():
    out = apply_suffix("cyber fox, High Detail", "high detail, no text")
    assert out == "cyber fox, High Detail, no text"


def test_apply_suffix_empty_suffix_returns_prompt():
    assert apply_suffix("cyber fox", "") == "cyber fox"


def test_apply_suffix_empty_prompt():
    assert apply_suffix("", "high detail") == "high detail"


def test_apply_suffix_all_duplicate_yields_base():
    assert apply_suffix("a, b", "a, b") == "a, b"


def test_dynamic_preset_matches_keywords():
    assert dynamic_preset("cute avatar portrait") == "pfp"
    assert dynamic_preset("epic landscape scenery") == "landscape"
    assert dynamic_preset("full body warrior") == "full_body"
    assert dynamic_preset("intense battle action") == "dynamic"


def test_dynamic_preset_geometric_and_brand():
    assert dynamic_preset("generative abstract parametric art") == "geometric"
    assert dynamic_preset("minimal logo brand badge") == "brand"
    assert dynamic_preset("commemorative event medallion") == "event_badge"
    assert dynamic_preset("sumi-e ink wash gallery piece") == "fine_art"
    assert dynamic_preset("synthwave vaporwave neon grid") == "dynamic"
    assert dynamic_preset("glitch datamosh rgb split") == "geometric"
    assert dynamic_preset("chibi kawaii mascot") == "pfp"


def test_suffix_geometric_and_brand_presets_exist():
    assert "geometric" in SUFFIX_PRESETS
    assert "brand" in SUFFIX_PRESETS
    assert "event_badge" in SUFFIX_PRESETS
    assert "fine_art" in SUFFIX_PRESETS
    assert "no human face" in SUFFIX_PRESETS["geometric"]
    assert "no readable text" in SUFFIX_PRESETS["event_badge"]


def test_dynamic_preset_default_when_no_match():
    assert dynamic_preset("???") == "pfp"
    assert dynamic_preset("???", default="landscape") == "landscape"


def test_enhance_without_profile_is_passthrough():
    positive, negative = enhance("  cyber fox  ", None)
    assert positive == "cyber fox"
    assert negative == ""


def test_enhance_with_profile_adds_suffix_and_negative():
    profile = PromptQualityProfile(suffix_preset="pfp", use_negative=True)
    positive, negative = enhance("cyber fox", profile)
    assert positive.startswith("cyber fox, ")
    assert "centered composition" in positive
    assert negative == DEFAULT_NEGATIVE


def test_enhance_profile_negative_disabled():
    profile = PromptQualityProfile(suffix_preset="pfp", use_negative=False)
    _positive, negative = enhance("cyber fox", profile)
    assert negative == ""


def test_enhance_appends_extra_suffix_from_bible():
    profile = PromptQualityProfile(suffix_preset="", extra_suffix="neon cyberpunk, soft light")
    positive, _negative = enhance("cyber fox", profile)
    assert positive == "cyber fox, neon cyberpunk, soft light"


def test_enhance_extra_suffix_dedups_against_preset():
    # «no text» вже є в пресеті pfp — не дублюється з extra_suffix.
    profile = PromptQualityProfile(suffix_preset="pfp", extra_suffix="no text, neon")
    positive, _negative = enhance("fox", profile)
    assert positive.count("no text") == 1
    assert positive.endswith("neon")


def test_enhance_merges_item_negative_without_profile():
    positive, negative = enhance("cyber fox", None, item_negative="ugly, blurry")
    assert positive == "cyber fox"
    assert negative == "ugly, blurry"


def test_enhance_merges_item_and_profile_negative():
    profile = PromptQualityProfile(suffix_preset="pfp", use_negative=True, negative_base="ugly")
    _positive, negative = enhance("fox", profile, item_negative="blurry, ugly")
    assert "ugly" in negative
    assert "blurry" in negative
    assert negative.count("ugly") == 1
