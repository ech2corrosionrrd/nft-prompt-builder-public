"""Хелпери курації: pilot-вибірка та середній рейтинг (ПЛАН_ЯКОСТІ.md § Q2.4).

Чисті функції без Streamlit: дають оператору запустити невелику pilot-партію перед
великою чергою й оцінити середній рейтинг, щоб не палити кредити на свідомо слабкий
прогін.
"""

from __future__ import annotations

PILOT_DEFAULT = 10
LOW_RATING_THRESHOLD = 3.5


def pilot_count(total: int, n: int = PILOT_DEFAULT) -> int:
    """Скільки промптів увійде в pilot (не більше за наявні, не менше 0)."""
    return max(0, min(total, n))


def pilot_subset(prompts: list[dict], n: int = PILOT_DEFAULT) -> list[dict]:
    """Перші n промптів для pilot-прогону."""
    return list(prompts[: max(n, 0)])


def average_rating(ratings: list[int]) -> float | None:
    """Середній рейтинг за оціненими (>0) зображеннями; None якщо оцінок немає."""
    vals = [int(r) for r in ratings if r]
    return round(sum(vals) / len(vals), 2) if vals else None


def is_low_quality(avg: float | None, threshold: float = LOW_RATING_THRESHOLD) -> bool:
    """True, якщо середній рейтинг відомий і нижчий за поріг (попередження в UI)."""
    return avg is not None and avg < threshold


# ── Куратор 2.0: масові дії (ПЛАН_ЯКОСТІ.md § Q2.3) ───────────────────────────

def borderline_indices(rating_by_index: dict[int, int], star: int = 3) -> list[int]:
    """Індекси з точним рейтингом star (для final-pass borderline)."""
    return sorted(i for i, r in rating_by_index.items() if int(r) == star)


def bulk_approve_indices(rating_by_index: dict[int, int], min_star: int) -> list[int]:
    """Індекси зображень із рейтингом >= min_star (для масового схвалення)."""
    return sorted(i for i, r in rating_by_index.items() if int(r) >= min_star)


def engine_winner(items: list[tuple[str, int]]) -> str | None:
    """Двигун із найвищим середнім рейтингом серед оцінених (>0).

    items — пари (engine, rating). Без оцінок → None. За рівності перемагає той,
    у кого більше оцінених зображень (надійніша вибірка), далі — назва (стабільність).
    """
    totals: dict[str, list[int]] = {}
    for engine, rating in items:
        if engine and rating:
            totals.setdefault(engine, []).append(int(rating))
    if not totals:
        return None
    return max(
        totals,
        key=lambda e: (sum(totals[e]) / len(totals[e]), len(totals[e]), e),
    )
