"""Правила сумісності traits (ПЛАН_ЯКОСТІ.md § Q2.2).

Чисті функції без Streamlit: оператор задає пари trait-значень, які не мають
з'являтися разом в одному токені (напр. «golden crown | viking helmet» — два
головні убори). Несумісні комбінації відсіюються ДО генерації, що прибирає
безглузді кадри й економить кредити.

Правило — невпорядкована пара значень (frozenset з двох рядків). Комбінація
блокується, якщо ОБА значення правила присутні серед її traits (незалежно від
категорії — головні убори можуть бути в різних категоріях у різних шаблонах).
"""

from __future__ import annotations

# Роздільники пари в одному рядку: «a | b», «a + b», «a vs b».
_PAIR_SPLIT = ("|", "+", " vs ")


def parse_rules(raw: str) -> list[frozenset[str]]:
    """Парсить правила: один рядок = одна несумісна пара значень.

    Порожні рядки, рядки без роздільника та самопари (a|a) ігноруються.
    Значення приводяться до нижнього регістру для нечутливого порівняння.
    """
    rules: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = _split_pair(line)
        if len(parts) != 2:
            continue
        a, b = parts[0].strip().lower(), parts[1].strip().lower()
        if not a or not b or a == b:
            continue
        rule = frozenset({a, b})
        if rule not in seen:
            seen.add(rule)
            rules.append(rule)
    return rules


def _split_pair(line: str) -> list[str]:
    for sep in _PAIR_SPLIT:
        if sep in line:
            left, _, right = line.partition(sep)
            return [left, right]
    return [line]


def combo_allowed(traits: dict[str, str], rules: list[frozenset[str]]) -> bool:
    """True, якщо жодне правило несумісності не порушено комбінацією traits."""
    if not rules:
        return True
    values = {str(v).strip().lower() for v in traits.values() if str(v).strip()}
    return not any(rule <= values for rule in rules)


def filter_combos(combos: list[dict], rules: list[frozenset[str]]) -> list[dict]:
    """Лишає лише сумісні елементи матриці (кожен має ключ 'traits')."""
    if not rules:
        return list(combos)
    return [c for c in combos if combo_allowed(c.get("traits", {}), rules)]


def count_blocked(combos: list[dict], rules: list[frozenset[str]]) -> int:
    """Скільки комбінацій буде відсіяно правилами (для підказки в UI)."""
    if not rules:
        return 0
    return sum(1 for c in combos if not combo_allowed(c.get("traits", {}), rules))
