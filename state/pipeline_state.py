"""Стан Web3-конвеєра в st.session_state.

Контракти передачі даних між етапами:
- GENERATED_PROMPTS (Етап 1 → Етап 2): list[dict] з ключами
  prompt, core, style, details, tags, traits.
- PIPELINE_IMAGES (Етап 2, внутрішній): list[dict] з ключами
  prompt, bytes, path, traits.
- APPROVED_CONTENT (Етап 2 → Етап 3): list[dict] з ключами
  name, description, prompt, traits, bytes, filename.
- MINT_ASSETS (Етап 3, внутрішній): елементи APPROVED_CONTENT, доповнені
  image_uri, metadata, token_uri, mint_result.
"""

import streamlit as st

GENERATED_PROMPTS = "generated_prompts"
PIPELINE_IMAGES = "pipeline_images"
APPROVED_CONTENT = "approved_content"
MINT_ASSETS = "mint_assets"

_KEYS = (GENERATED_PROMPTS, PIPELINE_IMAGES, APPROVED_CONTENT, MINT_ASSETS)


def init_pipeline_state() -> None:
    for key in _KEYS:
        if key not in st.session_state:
            st.session_state[key] = []


def reset_stage(key: str) -> None:
    st.session_state[key] = []


def sync_mint_queue_from_approved() -> int:
    """Копіює APPROVED_CONTENT → MINT_ASSETS (Export без зайвого «забрати схвалене»).

    Повертає кількість елементів у черзі експорту.
    """
    approved = st.session_state.get(APPROVED_CONTENT, [])
    st.session_state[MINT_ASSETS] = [dict(item) for item in approved]
    return len(st.session_state[MINT_ASSETS])


def ensure_mint_queue_from_approved() -> int:
    """Синхронізує чергу експорту, якщо є схвалений контент, а MINT_ASSETS порожній."""
    existing = st.session_state.get(MINT_ASSETS) or []
    if existing:
        return len(existing)
    return sync_mint_queue_from_approved() if st.session_state.get(APPROVED_CONTENT) else 0
