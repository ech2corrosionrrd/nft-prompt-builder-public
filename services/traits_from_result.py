"""Парсинг таблиці traits з відповіді Конструктора → поля вкладки Traits.

Чисті функції (без Streamlit) — щоб тест покривав мапінг категорій і форматів.
Зіставлення за назвою (uk/en) і за позицією в таблиці / списку.
"""

from __future__ import annotations

import re

from i18n import TRAIT_CATEGORY_EN
from options import TRAIT_CATEGORIES

# Додаткові синоніми LLM (не збігаються з TRAIT_CATEGORY_EN).
_EXTRA_ALIASES: dict[str, str] = {
    "accessories / weapons": "Аксесуари / Зброя",
    "emotion / facial expression": "Емоція / Вираз обличчя",
    "форма голови": "Голова / Шолом / Маска",
    "тип меча": "Аксесуари / Зброя",
    "колір шкіри": "Одяг / Броня",
}


def _normalize_key(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").strip().lower())
    s = s.strip("*:#.-—|_ ")
    s = re.sub(r"\s*/\s*", " / ", s)
    return s


def _build_alias_map() -> dict[str, str]:
    """uk/en назви → канонічний ключ TRAIT_CATEGORIES."""
    out: dict[str, str] = {}
    for uk in TRAIT_CATEGORIES:
        out[_normalize_key(uk)] = uk
    for uk, en in TRAIT_CATEGORY_EN.items():
        if uk not in TRAIT_CATEGORIES:
            continue
        out[_normalize_key(en)] = uk
        out[_normalize_key(en.replace(" / ", "/"))] = uk
    for alias, uk in _EXTRA_ALIASES.items():
        out[_normalize_key(alias)] = uk
    return out


_ALIAS_MAP = _build_alias_map()


def resolve_trait_category(raw_name: str) -> str | None:
    """Мапить вільну назву категорії на TRAIT_CATEGORIES або None."""
    key = _normalize_key(raw_name)
    if not key:
        return None
    if key in _ALIAS_MAP:
        return _ALIAS_MAP[key]
    # Частковий збіг лише для довгих аліасів (уникаємо «head» у «overhead»).
    for alias, canon in _ALIAS_MAP.items():
        if len(alias) < 5:
            continue
        if alias in key or key in alias:
            return canon
    return None


def _split_table_cells(line: str) -> list[str]:
    if "|" not in line:
        return []
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.match(r"^[-:\s]+$", c or "") for c in cells)


def _split_variants(raw: str) -> list[str]:
    text = raw.strip().strip("|").strip()
    if not text:
        return []
    if "\n" in text:
        parts = []
        for line in text.splitlines():
            line = re.sub(r"^[-*•]\s*", "", line.strip())
            if line:
                parts.append(line)
        return parts
    parts = re.split(r"\s*[,;/]\s*", text)
    return [p.strip() for p in parts if p.strip()]


def _merge_into(
    found: dict[str, list[str]],
    parsed: dict[str, str],
) -> None:
    for cat, text in parsed.items():
        if cat not in found:
            continue
        for v in text.splitlines():
            v = v.strip()
            if v and v not in found[cat]:
                found[cat].append(v)


def _parse_horizontal_traits_table(content: str) -> dict[str, str]:
    """Таблиця з кількома категоріями в заголовку й варіантами в рядку нижче."""
    lines = content.splitlines()
    for i, line in enumerate(lines):
        cells = _split_table_cells(line)
        if len(cells) < 2:
            continue
        header: list[tuple[int, str]] = []
        for idx, cell in enumerate(cells):
            canon = resolve_trait_category(cell)
            if canon:
                header.append((idx, canon))
        if len(header) < 2:
            continue
        j = i + 1
        if j < len(lines) and _is_separator_row(_split_table_cells(lines[j])):
            j += 1
        if j >= len(lines):
            continue
        data_cells = _split_table_cells(lines[j])
        if not data_cells:
            continue
        out: dict[str, str] = {}
        for col_idx, canon in header:
            if col_idx >= len(data_cells):
                continue
            variants = _split_variants(data_cells[col_idx])
            if variants:
                out[canon] = "\n".join(variants)
        if len(out) >= 2:
            return out
    return {}


def _parse_vertical_traits_table(content: str) -> dict[str, str]:
    """Класична 2-колонкова таблиця | категорія | варіанти |."""
    found: dict[str, list[str]] = {c: [] for c in TRAIT_CATEGORIES}
    for m in re.finditer(
        r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        content,
        flags=re.MULTILINE,
    ):
        cat_raw, variants_raw = m.group(1), m.group(2)
        if _is_separator_row([cat_raw, variants_raw]):
            continue
        if cat_raw.lower() in ("category", "категорія", "trait", "variants", "варіанти"):
            continue
        canon = resolve_trait_category(cat_raw)
        if not canon:
            continue
        for v in _split_variants(variants_raw):
            if v not in found[canon]:
                found[canon].append(v)
    return {cat: "\n".join(items) for cat, items in found.items() if items}


def _parse_inline_category_lines(content: str) -> dict[str, str]:
    """Рядки на кшталт **Head / Helmet / Mask**: v1, v2, v3."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r"(?:^|\n)\s*(?:\*\*|__)?\s*([^\n:*#]{2,70}?)\s*(?:\*\*|__)?\s*:\s*([^\n]+)",
        content,
        flags=re.MULTILINE,
    ):
        canon = resolve_trait_category(m.group(1))
        if not canon:
            continue
        variants = _split_variants(m.group(2))
        if variants:
            out[canon] = "\n".join(variants)
    return out


def _parse_bullet_sections(content: str) -> dict[str, str]:
    """### Категорія + маркований список."""
    found: dict[str, list[str]] = {c: [] for c in TRAIT_CATEGORIES}
    section_re = re.compile(
        r"(?:^|\n)(?:#{1,4}\s*|\*\*|__)?\s*([^\n:*#]{2,70}?)\s*(?:\*\*|__)?\s*:?\s*\n"
        r"((?:[-*•].+\n?)+)",
        flags=re.MULTILINE,
    )
    for m in section_re.finditer(content):
        canon = resolve_trait_category(m.group(1))
        if not canon:
            continue
        for line in m.group(2).splitlines():
            item = re.sub(r"^[-*•]\s*", "", line.strip())
            if item and item not in found[canon]:
                found[canon].append(item)
    return {cat: "\n".join(items) for cat, items in found.items() if items}


def _parse_position_bullet_sections(content: str) -> dict[str, str]:
    """Якщо є 6 послідовних списків без розпізнаних назв — мапимо за індексом."""
    blocks: list[list[str]] = []
    section_re = re.compile(
        r"(?:^|\n)(?:#{1,4}\s*|\*\*|__)?\s*([^\n]+?)\s*(?:\*\*|__)?\s*:?\s*\n"
        r"((?:[-*•].+\n?)+)",
        flags=re.MULTILINE,
    )
    for m in section_re.finditer(content):
        items = [
            re.sub(r"^[-*•]\s*", "", line.strip())
            for line in m.group(2).splitlines()
            if line.strip()
        ]
        if items:
            blocks.append(items)
    if len(blocks) < len(TRAIT_CATEGORIES):
        return {}
    # Якщо назви вже зіставились — position fallback не потрібен.
    named = sum(1 for m in section_re.finditer(content) if resolve_trait_category(m.group(1)))
    if named >= len(TRAIT_CATEGORIES) // 2:
        return {}
    out: dict[str, str] = {}
    for i, canon in enumerate(TRAIT_CATEGORIES):
        if i < len(blocks) and blocks[i]:
            out[canon] = "\n".join(blocks[i])
    return out


def parse_traits_from_content(content: str) -> dict[str, str]:
    """Витягує {канонічна категорія: текст «варіант\\n…»} з markdown відповіді Builder."""
    if not content or not content.strip():
        return {}
    found: dict[str, list[str]] = {c: [] for c in TRAIT_CATEGORIES}

    for chunk in (
        _parse_horizontal_traits_table(content),
        _parse_vertical_traits_table(content),
        _parse_inline_category_lines(content),
        _parse_bullet_sections(content),
        _parse_position_bullet_sections(content),
    ):
        _merge_into(found, chunk)

    return {cat: "\n".join(items) for cat, items in found.items() if items}
