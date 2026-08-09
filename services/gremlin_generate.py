"""Gremlin Generator — валідація трейтів і побудова промпту для Flux.1.

Контракт дзеркалить клієнт Gremlin Passport (`src/lib/generator-traits.ts`
та `src/server/generator.ts`): ті самі ключі трейтів і ті самі дозволені
значення. Тут — суто чиста логіка (без FastAPI/мережі), щоб покрити тестами;
сам ендпоінт у `api_server.py` лише гейтить доступ і кличе AIService.
"""
from __future__ import annotations

# Дозволені трейти й значення — мусять збігатися з TRAIT_OPTIONS у Passport.
TRAIT_OPTIONS: dict[str, tuple[str, ...]] = {
    "body": ("void", "ember", "moss", "signal"),
    "eyes": ("glow", "slit", "wide", "pixel"),
    "accessory": ("none", "antenna", "hoodie", "crown"),
    "backdrop": ("nebula", "grid", "forest", "studio"),
}

MAX_SEED = 1_000_000

# Опис кожного значення для промпту (людська мова для моделі, не слаг).
_BODY = {
    "void": "deep void-black skin with faint purple sheen",
    "ember": "glowing ember-orange skin with warm cracks of light",
    "moss": "mossy green skin with mottled texture",
    "signal": "electric cyan skin with neon signal glow",
}
_EYES = {
    "glow": "big glowing luminous eyes",
    "slit": "sharp reptilian slit-pupil eyes",
    "wide": "wide round curious eyes",
    "pixel": "blocky pixelated 8-bit eyes",
}
_ACCESSORY = {
    "none": "",
    "antenna": "a small antenna on its head",
    "hoodie": "wearing a cozy hoodie",
    "crown": "wearing a tiny golden crown",
}
_BACKDROP = {
    "nebula": "cosmic nebula background",
    "grid": "glowing cyberpunk grid background",
    "forest": "dark enchanted forest background",
    "studio": "clean neutral studio background",
}


class TraitError(ValueError):
    """Невалідні трейти / seed у запиті генерації."""


def validate_traits(payload: object) -> dict[str, str]:
    """Пропустити лише відомі трейти з відомими значеннями.

    Захист у глибину: беремо саме дозволені ключі й перевіряємо значення, а не
    довіряємо тілу запиту — інакше довільний рядок поїхав би у промпт моделі.
    """
    if not isinstance(payload, dict):
        raise TraitError("traits must be an object")
    result: dict[str, str] = {}
    for key, allowed in TRAIT_OPTIONS.items():
        value = payload.get(key)
        if not isinstance(value, str) or value not in allowed:
            raise TraitError(f"invalid trait: {key}")
        result[key] = value
    return result


def validate_seed(seed: object) -> int:
    """Seed — ціле в [0, MAX_SEED]. bool відкидаємо (в Python bool є int)."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TraitError("invalid seed")
    if seed < 0 or seed > MAX_SEED:
        raise TraitError("invalid seed")
    return seed


def build_prompt(traits: dict[str, str]) -> str:
    """Скласти текстовий промпт Flux із валідованих трейтів."""
    parts = [
        "a portrait of a cute mischievous gremlin creature",
        _BODY[traits["body"]],
        _EYES[traits["eyes"]],
    ]
    accessory = _ACCESSORY[traits["accessory"]]
    if accessory:
        parts.append(accessory)
    parts.append(_BACKDROP[traits["backdrop"]])
    parts.append("digital art, character design, centered, highly detailed")
    return ", ".join(parts)
