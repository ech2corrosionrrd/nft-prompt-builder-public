"""Тести профілю якості генерації (ПЛАН_ЯКОСТІ.md § Q1.0)."""

from services.prompt_quality import (
    DEFAULT_NEGATIVE,
    TIER_DRAFT,
    TIER_FINAL,
    TIER_HYBRID,
    PromptQualityProfile,
    normalize_tier,
)


def test_effective_negative_disabled_by_default():
    assert PromptQualityProfile().effective_negative() == ""


def test_effective_negative_uses_default_when_enabled_without_custom():
    p = PromptQualityProfile(use_negative=True)
    assert p.effective_negative() == DEFAULT_NEGATIVE


def test_effective_negative_prefers_custom():
    p = PromptQualityProfile(use_negative=True, negative_base="  ugly, blurry  ")
    assert p.effective_negative() == "ugly, blurry"


def test_is_final_index_draft_never():
    p = PromptQualityProfile(quality_tier=TIER_DRAFT)
    assert not p.is_final_index(0)
    assert not p.is_final_index(5)


def test_is_final_index_final_always():
    p = PromptQualityProfile(quality_tier=TIER_FINAL)
    assert p.is_final_index(0)
    assert p.is_final_index(999)


def test_is_final_index_hybrid_first_n():
    p = PromptQualityProfile(quality_tier=TIER_HYBRID, hybrid_final_n=3)
    assert [p.is_final_index(i) for i in range(5)] == [True, True, True, False, False]


def test_normalize_tier():
    assert normalize_tier("FINAL") == TIER_FINAL
    assert normalize_tier(" hybrid ") == TIER_HYBRID
    assert normalize_tier("nonsense") == TIER_DRAFT
    assert normalize_tier("") == TIER_DRAFT
