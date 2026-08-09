"""Тести конструктора (ui/build_panel.py) та опцій (options.py), винесених з app.py."""

import builder
import options
from preset_labels import preset_label
from styles import NFT_STYLES
from ui import build_panel  # noqa: F401  # import-smoke: build_panel має імпортуватися без помилок


def test_build_user_data_contains_all_fields():
    out = builder.build_user_data(
        idea="cyber cat",
        style="Anime",
        camera="Close-up",
        lighting="Neon",
        background="Cyber-City",
        quality="8k",
        mood="Epic",
        platform="opensea",
        tech="--ar 1:1",
        collection_size=100,
        extra_notes="no text",
    )
    for fragment in ("cyber cat", "Anime", "Close-up", "Neon", "Cyber-City",
                     "8k", "Epic", "opensea", "--ar 1:1", "100", "no text"):
        assert fragment in out


def test_build_user_data_empty_notes_dash():
    out = builder.build_user_data(
        idea="x", style="s", camera="c", lighting="l", background="b",
        quality="q", mood="m", platform="p", tech="t",
        collection_size=10, extra_notes="",
        lang="uk",
    )
    assert "Побажання: —" in out


def test_options_lists_nonempty_and_unique():
    for lst in (options.CAMERA_ANGLES, options.LIGHTING, options.BACKGROUNDS,
                options.QUALITY_TIERS, options.MOODS, options.ASPECT_RATIOS,
                options.RANDOM_IDEAS):
        assert lst, "список опцій не має бути порожнім"
        assert len(lst) == len(set(lst)), "опції мають бути унікальні"


def test_list_index_found_and_missing():
    assert options.list_index(["a", "b", "c"], "b") == 1
    assert options.list_index(["a", "b", "c"], "missing") == 0
    assert options.list_index([], "x") == 0


def test_preset_label_translates_known_option():
    value = options.CAMERA_ANGLES[0]

    assert preset_label(value, "en") == "Close-up PFP"
    assert "портрет" in preset_label(value, "uk").lower()
    assert preset_label("custom value", "uk") == "custom value"


def test_preset_label_translates_style_without_changing_value():
    value = NFT_STYLES[0]

    assert preset_label(value, "en") == "3D Premium Render"
    assert "3d" in preset_label(value, "uk").lower()
    assert value in NFT_STYLES


def test_image_quality_labels_are_localized():
    assert preset_label("medium", "en") == "Medium (balanced)"
    assert "середня" in preset_label("medium", "uk").lower()


def test_build_ar_tag_supports_new_aspect_ratios():
    assert builder.build_ar_tag("9:16 (Vertical story)", "Midjourney v7") == "--ar 9:16"
    assert builder.build_ar_tag("3:4 (Portrait poster)", "OpenAI Images") == "aspect ratio 3:4"
