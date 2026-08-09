"""Авто-підготовка pipeline Stage 1 із шаблону колекції (ПЛАН_NFT_РЕЗУЛЬТАТ.md § A5).

Чисті функції без Streamlit: будують GENERATED_PROMPTS і Style Bible з
`templates.COLLECTION_TEMPLATES`, щоб welcome/sidebar одразу давали готовий
вхід на Етап 2 без ручного збору матриці.
"""

from __future__ import annotations

import hashlib
import random

import batch
from builder import build_tech_params
from options import MATRIX_STORAGE_KEYS, TRAIT_CATEGORIES, trait_key
from services import prompt_service, style_bible
from services.prompt_enhancer import dynamic_preset
from services.prompt_quality import consistency_for_archetype, negative_for_archetype
from trait_i18n import strip_uk_hint

# Синхрон із options._MATRIX_TEMPLATE_CAT_MAP — trait-категорія → ключ матриці.
_TRAIT_TO_MATRIX: dict[str, str] = {
    "Голова / Шолом / Маска": "Варіанти аксесуарів",
    "Очі / Окуляри": "Варіанти аксесуарів",
    "Одяг / Броня": "Варіанти аксесуарів",
    "Аксесуари / Зброя": "Варіанти аксесуарів",
    "Фон / Аура": "Варіанти фону",
    "Емоція / Вираз обличчя": "Варіанти аксесуарів",
    # Abstract / brand / landscape / event
    "Форма / Силует": "Варіанти аксесуарів",
    "Фон / Поле": "Варіанти фону",
    "Подача / Контекст": "Варіанти аксесуарів",
    "Сцена / Локація": "Варіанти персонажа",
    "Настрій / Освітлення": "Варіанти фону",
    "Рівень / Tier": "Варіанти персонажа",
    "Візуальна подача": "Варіанти аксесуарів",
}

# Архетипні категорії шаблону → classic TRAIT_CATEGORIES (② Traits / Batch).
_ARCHETYPE_CAT_TO_CLASSIC: dict[str, str] = {
    "Форма / Силует": "Аксесуари / Зброя",
    "Фон / Поле": "Фон / Аура",
    "Подача / Контекст": "Одяг / Броня",
    "Сцена / Локація": "Голова / Шолом / Маска",
    "Настрій / Освітлення": "Фон / Аура",
    "Рівень / Tier": "Емоція / Вираз обличчя",
    "Візуальна подача": "Одяг / Броня",
}

_ARCHETYPE_SUFFIX: dict[str, str] = {
    "abstract_geometric": "geometric",
    "brand_icon": "brand",
    "landscape": "landscape",
    "event_badge": "event_badge",
    "fine_art": "fine_art",
}


def _matrix_categories_from_traits(traits: dict) -> dict[str, list[str]]:
    """Мапить trait-таблицю шаблону на категорії матриці Етапу 1."""
    pools: dict[str, list[str]] = {k: [] for k in MATRIX_STORAGE_KEYS}
    for cat, values in (traits or {}).items():
        key = _TRAIT_TO_MATRIX.get(cat)
        if key and values:
            pools[key].extend(str(v).strip() for v in values if str(v).strip())
    return {
        k: list(dict.fromkeys(v))
        for k, v in pools.items()
        if v
    }


def classic_trait_lines_from_template(template: dict) -> dict[str, str]:
    """Тексти для classic trait_key(cat): PFP-категорії + мапінг архетипних осей."""
    traits_raw = dict(template.get("traits") or {})
    out = {cat: "" for cat in TRAIT_CATEGORIES}
    for cat in TRAIT_CATEGORIES:
        vals = traits_raw.get(cat)
        if vals:
            out[cat] = "\n".join(str(v) for v in vals)
    for arch_cat, classic_cat in _ARCHETYPE_CAT_TO_CLASSIC.items():
        vals = traits_raw.get(arch_cat)
        if not vals:
            continue
        block = "\n".join(str(v) for v in vals)
        prev = out[classic_cat]
        out[classic_cat] = f"{prev}\n{block}".strip() if prev else block
    return out


def base_object_from_template(template: dict) -> str:
    """BASE OBJECT серії — фіксоване ядро, спільне для всіх айтемів колекції.

    Явне поле `base_object`, інакше `idea`. Раніше `idea` підставлялась як
    ЗНАЧЕННЯ осі «Варіанти персонажа» і лише коли та вісь порожня — тож у
    шаблонах, де вісь зайнята (landscape зі сценами, event із tier-ами), базовий
    об'єкт просто зникав з промпту, і колекція втрачала спільне ядро
    (`Event Badge Series` не згадував Web3-бейдж узагалі). Тепер це окрема
    фіксована частина, що не конкурує з осями матриці.
    """
    return strip_uk_hint(
        str(template.get("base_object") or template.get("idea") or "").strip()
    )


def consistency_from_template(template: dict) -> str:
    """Технічні фіксатори серії: явне поле `consistency`, інакше дефолт архетипу."""
    explicit = str(template.get("consistency") or "").strip()
    if explicit:
        return strip_uk_hint(explicit)
    return consistency_for_archetype(str(template.get("archetype") or "pfp"))


def matrix_categories_from_template(template: dict) -> dict[str, list[str]]:
    """Категорії матриці Етапу 1 (Конструктор → Матриця) з trait-таблиці шаблону.

    BASE OBJECT сюди НЕ потрапляє — він фіксована частина промпту
    (`base_object_from_template`), а не вісь. Матриця лишається множенням лише
    змінних trait-ів, тож розмір колекції передбачуваний (5×5 = 25, а не 6×5).
    """
    return _matrix_categories_from_traits(dict(template.get("traits") or {}))


def ui_session_from_template(template: dict) -> dict[str, str | list[str]]:
    """Ключі session_state: classic Traits + multiselect матриці + спільний стиль."""
    state: dict[str, str | list[str]] = {}
    for key in MATRIX_STORAGE_KEYS:
        state[f"pl1_matrix_{key}"] = []
    for cat, text in classic_trait_lines_from_template(template).items():
        state[trait_key(cat)] = text
    for key, values in matrix_categories_from_template(template).items():
        state[f"pl1_matrix_{key}"] = list(values)
    style = str(template.get("style", "")).strip()
    if style:
        state["pl1_style_matrix"] = style
    return state


def widget_keys_from_template(template: dict) -> dict[str, str | int]:
    """Ключі Streamlit-віджетів, що дзеркалять canonical-поля шаблону."""
    state: dict[str, str | int] = {}
    idea = str(template.get("idea", "")).strip()
    style = str(template.get("style", "")).strip()
    if idea:
        state["pl1_core_single"] = idea
        state["build_idea"] = idea
    if style:
        state["pl1_style_single"] = style
        state["build_style"] = style
    for field, build_key in (
        ("camera", "build_camera"),
        ("lighting", "build_lighting"),
        ("background", "build_background"),
        ("quality", "build_quality"),
        ("mood", "build_mood"),
        ("aspect_ratio", "build_aspect"),
        ("stylize", "build_stylize"),
        ("chaos", "build_chaos"),
    ):
        if field in template:
            state[build_key] = template[field]
    cats = matrix_categories_from_template(template)
    collection_size = int(template.get("collection_size", 0) or 0)
    matrix_n = prompt_service.matrix_size(cats)
    if collection_size > 1 and len(cats) >= 2 and matrix_n > 0:
        state["pl1_mode"] = "matrix"
    elif collection_size <= 1:
        state["pl1_mode"] = "single"
    return state


def _template_rng(template: dict) -> random.Random:
    """Детермінований rng шаблону: той самий шаблон → той самий набір комбінацій.

    Streamlit перевиконує скрипт на кожну дію, а `apply_template` викликається
    не один раз. З глобальним `random` користувач бачив би інші traits після
    кожного кліку, і «Застосувати шаблон» ніколи не давало б відтворюваного
    результату. Сід — від назви (стабільної між запусками, на відміну від hash()
    рядка, який рандомізується PYTHONHASHSEED).
    """
    name = str(template.get("label") or template.get("idea") or "w3ir")
    seed = int(hashlib.sha256(name.encode("utf-8")).hexdigest()[:8], 16)
    return random.Random(seed)


def _engine_tags(template: dict) -> str:
    """MJ-теги з aspect_ratio/stylize/chaos шаблону (Midjourney v7 як дефолт)."""
    return build_tech_params(
        "Midjourney v7",
        strip_uk_hint(str(template.get("aspect_ratio", "1:1 (Квадрат для NFT)"))),
        int(template.get("stylize", 250)),
        int(template.get("chaos", 0)),
        0,
    )


def _details_from_template(template: dict) -> list[str]:
    # Порядок деталей: camera (FIXED ANGLE) першим — ракурс належить рамці серії
    # і має стояти якнайближче до trait-ів, а не губитися між світлом і настроєм.
    # Продукт EN: знімаємо укр-підказку в дужках з опцій-полів (див. trait_i18n).
    return [
        strip_uk_hint(str(template[k]).strip())
        for k in ("camera", "lighting", "background", "quality", "mood")
        if str(template.get(k, "")).strip()
    ]


def prompts_from_template(template: dict) -> list[dict]:
    """Повертає список prompt dict для GENERATED_PROMPTS.

    Якщо в шаблоні достатньо traits для матриці (≥2 категорії з варіантами) —
    будує матрицю; інакше один промпт (single).
    """
    categories = matrix_categories_from_template(template)
    style = strip_uk_hint(str(template.get("style", "")).strip())
    tags = _engine_tags(template)
    details = _details_from_template(template)
    base = base_object_from_template(template)
    consistency = consistency_from_template(template)
    collection_size = int(template.get("collection_size", 0) or 0)
    matrix_n = prompt_service.matrix_size(categories)

    use_matrix = (
        collection_size > 1
        and len(categories) >= 2
        and matrix_n > 0
    )

    if use_matrix:
        # Шаблони з повним набором шарів (≥3 trait-категорії) збираємо пошарово:
        # кожен айтем отримує по одному значенню з КОЖНОЇ категорії. Кількість
        # лишаємо ту саму, що дала б матриця, — змінюється не обсяг колекції, а
        # повнота айтема (див. prompt_service.build_layered). Матриця лишається
        # для шаблонів на 1-2 осі, де зливати нічого.
        traits_raw = {
            cat: [str(v) for v in vals if str(v).strip()]
            for cat, vals in (template.get("traits") or {}).items()
            if vals
        }
        if len(traits_raw) >= 3:
            combos = batch.sample_trait_combinations(
                traits_raw, matrix_n, rng=_template_rng(template),
            )
            return prompt_service.build_layered(
                combos, style, details, tags, base=base, consistency=consistency,
            )
        return prompt_service.build_matrix(
            categories, style, details, tags, base=base, consistency=consistency,
        )

    # Single: базовий об'єкт і є всім промптом — окремого core немає.
    return prompt_service.build_single(
        base or "NFT collection character", style, details, tags, consistency=consistency,
    )


def bible_from_template(template: dict) -> style_bible.StyleBible:
    """Style Bible з полів шаблону."""
    return style_bible.from_template(template)


def suffix_preset_for_template(template: dict) -> str:
    """Пресет Style lock за архетипом шаблону (ПЛАН_ЯКОСТІ / archetype playbooks)."""
    arch = str(template.get("archetype") or "pfp")
    if arch in _ARCHETYPE_SUFFIX:
        return _ARCHETYPE_SUFFIX[arch]
    return dynamic_preset(
        f"{template.get('style', '')} {template.get('idea', '')}",
        default="pfp",
    )


def archetype_session_hints(template: dict) -> dict[str, str]:
    """Підказки для session_state після apply_template (suffix + negative)."""
    arch = str(template.get("archetype") or "pfp")
    return {
        "_pl2_archetype": arch,
        "_pl2_archetype_negative": negative_for_archetype(arch),
        "pl2_suffix_preset": suffix_preset_for_template(template),
    }
