"""Локалізовані підписи для творчих пресетів без зміни prompt-значень."""

from __future__ import annotations

from options import OPTION_LABELS
from styles import NFT_STYLE_DESCRIPTIONS, NFT_STYLE_LABELS

_LANG_EN = "en"


def preset_label(value: str, lang: str) -> str:
    """Повертає UI-підпис пресету; custom/невідомі значення показує без змін."""
    labels = NFT_STYLE_LABELS.get(value) or OPTION_LABELS.get(value)
    if not labels:
        return value
    return labels.get(lang) or labels.get(_LANG_EN) or value


def style_description(value: str, lang: str) -> str:
    """Короткий опис стилю для UI (uk/en); порожній рядок для custom значень."""
    labels = NFT_STYLE_DESCRIPTIONS.get(value)
    if not labels:
        return ""
    return labels.get(lang) or labels.get(_LANG_EN) or ""
