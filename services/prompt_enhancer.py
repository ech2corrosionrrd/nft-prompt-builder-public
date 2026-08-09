"""NFT quality suffix і композиція промпту (ПЛАН_ЯКОСТІ.md § Q1.1).

Чисті функції без Streamlit і без мережі: додають до сирого промпту матриці
суфікс узгодженості стилю (без LLM), уникаючи дублів і не ламаючи слова, що вже
є в промпті. LLM-полірування (Q1.4) — окремий крок; тут лише детермінований
суфікс «майже безкоштовно».

Landmine (ПЛАН_ЯКОСТІ.md): суфікс додаємо ПІСЛЯ strip_platform_flags — інакше
MJ-теги (--ar тощо) опиняться всередині промпту, а не наприкінці.
"""

from __future__ import annotations

from services.prompt_quality import PromptQualityProfile

# ── Пресети суфіксів ──────────────────────────────────────────────────────────
# Кожен пресет — рядок із комами, що дописується в кінець positive-промпту.
SUFFIX_PRESETS: dict[str, str] = {
    "pfp": (
        "professional NFT portrait, centered composition, clean background, "
        "high detail, consistent art style, no text, no watermark, no extra limbs"
    ),
    "full_body": (
        "full body character, dynamic pose, consistent art style, "
        "clean background, high detail, no text, no watermark, no extra limbs"
    ),
    "landscape": (
        "detailed scenery, balanced composition, atmospheric lighting, "
        "consistent art style, high detail, no text, no watermark"
    ),
    "dynamic": (
        "dynamic action scene, motion, dramatic lighting, consistent art style, "
        "high detail, no text, no watermark, no extra limbs"
    ),
    "geometric": (
        "symmetrical composition, clean geometric forms, crisp edges, gradient mesh, "
        "generative art, no text, no watermark, no human face, no characters"
    ),
    "brand": (
        "centered brand mark, clean vector-like shapes, consistent palette, "
        "minimal composition, no random text, no watermark, no extra logos"
    ),
    "event_badge": (
        "commemorative badge or medallion, centered emblem, embossed relief, "
        "consistent metallic palette, ceremonial composition, no readable text, "
        "no watermark, no random letters"
    ),
    "fine_art": (
        "single cohesive fine art piece, gallery quality, balanced composition, "
        "intentional brushwork, no text, no watermark, no collage clutter"
    ),
}

# Ключові слова шаблону → пресет (для автоматичного вибору, Q1.1 «динамічний»).
_KEYWORD_PRESET: tuple[tuple[tuple[str, ...], str], ...] = (
    (("portrait", "pfp", "avatar", "headshot", "face", "bust"), "pfp"),
    (("full body", "full-body", "character", "figure", "standing"), "full_body"),
    (("landscape", "scenery", "environment", "vista", "атмосфер", "пейзаж"), "landscape"),
    (("action", "dynamic", "battle", "motion", "fight", "explosion"), "dynamic"),
    (
        ("abstract", "geometric", "parametric", "sacred", "mandala", "minimal line",
         "абстракт", "геометр", "сакральн"),
        "geometric",
    ),
    (
        ("medallion", "enamel", "commemorative", "tier badge", "event badge",
         "медальйон", "бейдж", "івент"),
        "event_badge",
    ),
    (
        ("fine art", "gallery", "sumi-e", "ink wash", "1/1 art", "gallery piece",
         "fine-art", "галере", "туш", "живопис"),
        "fine_art",
    ),
    (
        ("logo", "brand", "badge", "icon system", "mascot mark",
         "лого", "бренд", "емблем", "знак"),
        "brand",
    ),
    (
        ("synthwave", "vaporwave", "outrun", "retro 80s", "neon grid",
         "синтвейв", "вейпорвейв"),
        "dynamic",
    ),
    (
        ("glitch", "datamosh", "rgb split", "scanline", "corrupted pixel",
         "глитч", "датамош"),
        "geometric",
    ),
    (
        ("chibi", "super-deformed", "kawaii sd", "чібі"),
        "pfp",
    ),
    (
        ("matte painting", "cinematic landscape", "concept art vista",
         "мат-пейнтинг", "пейзаж концепт"),
        "landscape",
    ),
    (
        ("app icon", "flat ui", "figma vector", "іконка додатку"),
        "brand",
    ),
)


def dynamic_preset(keywords: str, default: str = "pfp") -> str:
    """Вибирає пресет суфікса за ключовими словами шаблону/стилю.

    keywords — довільний текст (напр. опис стилю шаблону); пошук
    нечутливий до регістру. Якщо нічого не збіглося — default.
    """
    text = (keywords or "").lower()
    for needles, preset in _KEYWORD_PRESET:
        if any(n in text for n in needles):
            return preset
    return default


def suffix_text(preset: str) -> str:
    """Текст суфікса за ключем пресета ("" для невідомого/порожнього)."""
    return SUFFIX_PRESETS.get((preset or "").strip(), "")


def _existing_tokens(prompt: str) -> set[str]:
    return {tok.strip().lower() for tok in prompt.split(",") if tok.strip()}


def apply_suffix(prompt: str, suffix: str) -> str:
    """Дописує суфікс до промпту, пропускаючи частини, що вже присутні.

    Очікує, що prompt уже очищено від platform-тегів. Кожна кома-частина
    суфікса додається лише якщо її ще немає (порівняння без регістру), щоб
    не роздувати промпт повторами на матриці з однаковим стилем.
    """
    base = (prompt or "").strip()
    suffix = (suffix or "").strip()
    if not suffix:
        return base
    have = _existing_tokens(base)
    additions = [
        part.strip() for part in suffix.split(",")
        if part.strip() and part.strip().lower() not in have
    ]
    if not additions:
        return base
    joined = ", ".join(additions)
    return f"{base}, {joined}" if base else joined


def merge_negatives(*parts: str) -> str:
    """Зливає кілька negative-рядків без дублів (case-insensitive по комах)."""
    tokens: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for raw in (part or "").split(","):
            tok = raw.strip()
            key = tok.lower()
            if tok and key not in seen:
                seen.add(key)
                tokens.append(tok)
    return ", ".join(tokens)


def enhance(
    prompt: str,
    profile: PromptQualityProfile | None,
    item_negative: str = "",
) -> tuple[str, str]:
    """Повертає (positive, negative) для готового (вже очищеного) промпту.

    Без профілю — промпт як є; negative лише з item (polish). З профілем —
    додається суфікс пресета й зливається profile negative + item negative.
    """
    polished_neg = (item_negative or "").strip()
    if profile is None:
        return (prompt or "").strip(), polished_neg
    positive = apply_suffix(prompt, suffix_text(profile.suffix_preset))
    # Суфікс зі StyleBible (Q2.1) — після пресета; apply_suffix дедупить повтори.
    positive = apply_suffix(positive, profile.extra_suffix)
    return positive, merge_negatives(profile.effective_negative(), polished_neg)
