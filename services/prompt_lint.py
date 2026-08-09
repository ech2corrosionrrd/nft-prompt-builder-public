"""Лінт промптів перед генерацією (ПЛАН_ЯКОСТІ.md § Q2.5).

Чисті функції без Streamlit: швидко перевіряють набір промптів на типові
проблеми (порожній, надто короткий/довгий, дублікати) ДО витрати кредитів.
Повертають стабільні коди проблем — UI перекладає їх через ui_strings (lint.<code>).
"""

from __future__ import annotations

MIN_PROMPT_CHARS = 8
MAX_PROMPT_CHARS = 1500  # запас від лімітів image-API на довжину промпту

LINT_EMPTY = "empty"
LINT_TOO_SHORT = "too_short"
LINT_TOO_LONG = "too_long"
LINT_DUPLICATE = "duplicate"


def _normalize(prompt: str) -> str:
    return " ".join((prompt or "").split()).lower()


def lint_prompt(prompt: str) -> list[str]:
    """Коди проблем одного промпту (без урахування дублів — це робить lint_prompts)."""
    issues: list[str] = []
    text = (prompt or "").strip()
    if not text:
        issues.append(LINT_EMPTY)
        return issues
    if len(text) < MIN_PROMPT_CHARS:
        issues.append(LINT_TOO_SHORT)
    if len(text) > MAX_PROMPT_CHARS:
        issues.append(LINT_TOO_LONG)
    return issues


def lint_prompts(prompts: list[dict]) -> dict[int, list[str]]:
    """Лінт набору: {індекс: [коди]}. Дублікати — однаковий нормалізований промпт.

    У результат потрапляють лише індекси, де є хоч одна проблема.
    """
    seen: dict[str, int] = {}
    result: dict[int, list[str]] = {}
    for i, item in enumerate(prompts):
        prompt = item.get("prompt", "")
        issues = lint_prompt(prompt)
        norm = _normalize(prompt)
        if norm and norm in seen:
            issues.append(LINT_DUPLICATE)
        elif norm:
            seen[norm] = i
        if issues:
            result[i] = issues
    return result


def summary(prompts: list[dict]) -> dict[str, int]:
    """Зведення по кодах проблем для підказки в UI ({} якщо все чисто)."""
    counts: dict[str, int] = {}
    for issues in lint_prompts(prompts).values():
        for code in issues:
            counts[code] = counts.get(code, 0) + 1
    return counts
