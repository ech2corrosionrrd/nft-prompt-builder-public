"""Style lock UI — усі пресети prompt_enhancer доступні на Етапі 2."""

from services.prompt_enhancer import SUFFIX_PRESETS
from ui.stage2_generator import _SUFFIX_PRESETS


def test_stage2_suffix_presets_match_enhancer():
    assert set(_SUFFIX_PRESETS) == set(SUFFIX_PRESETS)


def test_stage2_suffix_preset_i18n_keys_exist():
    from ui_strings import t

    for preset, i18n_key in _SUFFIX_PRESETS.items():
        assert t(i18n_key, lang="uk").strip(), preset
        assert t(i18n_key, lang="en").strip(), preset
