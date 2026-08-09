"""Профіль якості генерації конвеєра (ПЛАН_ЯКОСТІ.md § Q1.0).

Чистий модуль без Streamlit: збирає в одне місце налаштування, що визначають
якість зображення для матриці/черги — пресет суфікса, базовий negative, рівень
якості (draft/final/hybrid), бажаний двигун і temperature LLM-полірування.

UI лише наповнює PromptQualityProfile й передає його в pipeline; сам білінг
final-tier і виклик negative в API вмикаються в подальших PR (Q1.2/Q1.3).
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Рівні якості ──────────────────────────────────────────────────────────────
# Draft  — дешевий чернетковий прохід (schnell/standard/medium, ~1 cr).
# Final  — фінальний прохід вищої якості (dev/pro/hd/high, 2–4 cr).
# Hybrid — перші N зображень у Final, решта в Draft (швидкий pilot + дешева маса).
TIER_DRAFT = "draft"
TIER_FINAL = "final"
TIER_HYBRID = "hybrid"
QUALITY_TIERS = (TIER_DRAFT, TIER_FINAL, TIER_HYBRID)

# Базовий negative-prompt (Q1.2): універсальний відсів типових артефактів.
DEFAULT_NEGATIVE = (
    "blurry, low quality, watermark, text, logo, deformed, "
    "extra fingers, cropped, artifacts"
)

# Базовий negative за архетипом колекції (ПЛАН_АБСТРАКЦІЯ / ПЛАН_БРЕНД / landscape).
NEGATIVE_BY_ARCHETYPE: dict[str, str] = {
    "abstract_geometric": (
        "human, face, portrait, limbs, text, watermark, blurry, noisy, "
        "photographic, realistic skin, characters"
    ),
    "brand_icon": (
        "random text, misspelled letters, watermark, extra logos, blurry, deformed, "
        "photorealistic skin, human portrait"
    ),
    "landscape": (
        "human face close-up, portrait, selfie, text, watermark, blurry, cropped, "
        "low quality, deformed anatomy"
    ),
    "event_badge": (
        "random text, misspelled letters, watermark, blurry, deformed, "
        "photorealistic skin, cluttered layout"
    ),
    "fine_art": (
        "text, watermark, blurry, low quality, collage clutter, meme, "
        "photographic snapshot, deformed anatomy"
    ),
}


def negative_for_archetype(archetype: str) -> str:
    """Negative-prompt за архетипом шаблону; невідомий → порожній (дефолт у профілі)."""
    return NEGATIVE_BY_ARCHETYPE.get((archetype or "").strip(), "")


# ── Технічні фіксатори консистентності серії ─────────────────────────────────
# Хвіст промпту, ОДНАКОВИЙ для всіх айтемів колекції. Negative каже, чого не
# має бути в кадрі; фіксатори — що має лишатись незмінним МІЖ кадрами
# (композиція, формат, пропорції, світло). Без них 25 згенерованих зображень
# виглядають як 25 випадкових картинок, а не як одна серія: кожен виклик моделі
# незалежний, тож компонування й масштаб «пливуть» від айтема до айтема.
#
# Свідомо тримаємо їх короткими: довгий хвіст розмиває вагу самого BASE OBJECT.
# Межа відповідальності: BASE OBJECT описує САМ об'єкт та його внутрішні
# константи (анатомія, поверхня, товщина ліній), фіксатори — РАМКУ кадру
# (композиція, формат, місце суб'єкта в кадрі, світло між кадрами). Тримати її
# треба свідомо: коли обидва боки описували те саме, промпт роздувався дублями
# («depth layering» і «lens» двічі поспіль), а зайві слова відбирають вагу в
# самого об'єкта.
DEFAULT_CONSISTENCY = (
    "centered composition, consistent framing and lighting across all variations"
)

CONSISTENCY_BY_ARCHETYPE: dict[str, str] = {
    "pfp": (
        "centered composition, square format, subject fills the same portion of the frame, "
        "consistent lighting across all variations"
    ),
    "abstract_geometric": (
        "centered composition, square format, consistent scale and lighting across all variations"
    ),
    "brand_icon": (
        "centered with equal padding, square format, consistent optical size across all variations"
    ),
    "landscape": (
        "consistent horizon placement, color grading and lens across all variations"
    ),
    "event_badge": (
        "centered symmetrical composition, square format, consistent diameter and "
        "lighting across all variations"
    ),
    "fine_art": (
        "consistent framing, brushwork density and lighting across all variations"
    ),
}


def consistency_for_archetype(archetype: str) -> str:
    """Технічні фіксатори серії за архетипом; невідомий → універсальний дефолт."""
    return CONSISTENCY_BY_ARCHETYPE.get((archetype or "").strip(), DEFAULT_CONSISTENCY)

# Дефолтна temperature LLM-полірування матриці (Q1.4): помірна варіативність.
DEFAULT_POLISH_TEMPERATURE = 0.7


@dataclass
class PromptQualityProfile:
    """Налаштування якості одного прогону конвеєра.

    suffix_preset    — ключ пресета суфікса (див. prompt_enhancer.SUFFIX_PRESETS)
                       або порожній рядок, якщо суфікс вимкнено.
    negative_base    — базовий negative; порожній → DEFAULT_NEGATIVE при увімкненому.
    use_negative     — чи додавати negative взагалі (Style Lock / opt-in у UI).
    style_bible      — короткий «біблейний» опис стилю колекції (Q2.1, поки текст).
    quality_tier     — draft / final / hybrid.
    hybrid_final_n   — для hybrid: скільки перших зображень робити у Final.
    preferred_engine — зафіксований двигун-переможець (A/B) або "".
    temperature      — temperature LLM-полірування.
    """

    suffix_preset: str = ""
    extra_suffix: str = ""  # детермінований суфікс зі StyleBible.as_suffix() (Q2.1)
    negative_base: str = ""
    use_negative: bool = False
    style_bible: str = ""
    quality_tier: str = TIER_DRAFT
    hybrid_final_n: int = 0
    preferred_engine: str = ""
    temperature: float = DEFAULT_POLISH_TEMPERATURE

    def effective_negative(self) -> str:
        """Фактичний negative: вимкнено → "", власний → trim, інакше дефолт."""
        if not self.use_negative:
            return ""
        custom = (self.negative_base or "").strip()
        return custom or DEFAULT_NEGATIVE

    def is_final_index(self, index: int) -> bool:
        """Чи має зображення під номером index (з 0) генеруватися у Final-якості.

        draft  → ніколи; final → завжди; hybrid → перші hybrid_final_n.
        """
        if self.quality_tier == TIER_FINAL:
            return True
        if self.quality_tier == TIER_HYBRID:
            return index < max(self.hybrid_final_n, 0)
        return False


def normalize_tier(tier: str) -> str:
    """Приводить рівень якості до відомого значення (невідоме → draft)."""
    t = (tier or "").strip().lower()
    return t if t in QUALITY_TIERS else TIER_DRAFT
