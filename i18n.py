"""Мова інтерфейсу vs мова продукту для мінту."""

import re

from metadata_provenance import provenance_attributes

# Категорії traits: українська (оператор) → англійська (метадані on-chain)
TRAIT_CATEGORY_EN: dict[str, str] = {
    "Голова / Шолом / Маска": "Head / Helmet / Mask",
    "Очі / Окуляри": "Eyes / Glasses",
    "Одяг / Броня": "Clothing / Armor",
    "Аксесуари / Зброя": "Accessories / Weapon",
    "Фон / Аура": "Background / Aura",
    "Емоція / Вираз обличчя": "Expression / Emotion",
    # Abstract / brand / landscape / event (ПЛАН_АБСТРАКЦІЯ, ПЛАН_БРЕНД, ПЛАН_LANDSCAPE)
    "Форма / Силует": "Form",
    "Фон / Поле": "Background",
    "Подача / Контекст": "Layout",
    "Сцена / Локація": "Scene",
    "Настрій / Освітлення": "Mood / Lighting",
    "Рівень / Tier": "Tier",
    "Візуальна подача": "Visual Style",
}

# Категорії матриці Web3-конвеєра (Етап 1) → англійська для on-chain метаданих
PIPELINE_MATRIX_CATEGORY_EN: dict[str, str] = {
    "Варіанти персонажа": "Character",
    "Варіанти фону": "Background",
    "Варіанти аксесуарів": "Accessory",
    "Персонаж": "Character",
    "Фон": "Background",
    "Аксесуар": "Accessory",
    "Style": "Style",
}


def trait_type_en(category: str) -> str:
    """Назва trait для мінту — англійською (класичний контур і конвеєр)."""
    return (
        TRAIT_CATEGORY_EN.get(category)
        or PIPELINE_MATRIX_CATEGORY_EN.get(category)
        or category
    )


def trait_category_label(category: str, lang: str = "en") -> str:
    """Підпис поля traits у UI: uk — канонічна назва, en — TRAIT_CATEGORY_EN."""
    if (lang or "en").startswith("uk"):
        return category
    return TRAIT_CATEGORY_EN.get(category, category)


def trait_categories_en_joined() -> str:
    """Англійські назви 6 classic-категорій для системного промпту Builder."""
    from options import TRAIT_CATEGORIES

    return "; ".join(TRAIT_CATEGORY_EN[c] for c in TRAIT_CATEGORIES)

_CYRILLIC = re.compile(r"[\u0400-\u04FF]")


def default_mint_collection_name(idea: str) -> str:
    """Назва колекції за замовчуванням для полів мінту — англійською."""
    idea = (idea or "").strip()
    if not idea or _CYRILLIC.search(idea):
        return "My Collection"
    return idea


def mint_attributes(row: dict) -> list[dict[str, str]]:
    """Атрибути ERC-721/Metaplex для мінту — англійською.

    Пріоритет: `attributes` з відповіді batch-LLM (повний переклад).
    Fallback: англійські назви категорій + значення як у traits (операторські).
    Додає provenance: Rarity Score/Rank/Tier, Engine, Date, Prompt Hash.
    """
    if attrs := row.get("attributes"):
        base = [
            {"trait_type": str(a["trait_type"]), "value": str(a["value"])}
            for a in attrs
            if isinstance(a, dict) and a.get("trait_type") and a.get("value") is not None
        ]
    else:
        base = [
            {"trait_type": trait_type_en(cat), "value": str(val)}
            for cat, val in row.get("traits", {}).items()
        ]
    return base + provenance_attributes(row)
