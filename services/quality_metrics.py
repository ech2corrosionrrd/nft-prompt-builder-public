"""Інструментація якості конвеєра (D4 Quality Dashboard).

Fail-open обгортки над funnel_events — збій обліку не ламає UX.
"""

from __future__ import annotations

from services import payment_service


def build_curator_save_payload(items: list[dict]) -> dict:
    """Зріз якості збережених у чергу активів для агрегації в stats."""
    ratings = [int(it.get("curator_rating") or 0) for it in items if int(it.get("curator_rating") or 0) > 0]
    avg = round(sum(ratings) / len(ratings), 2) if ratings else None
    engines: dict[str, int] = {}
    for it in items:
        eng = (it.get("engine") or "").strip()
        if "(" in eng:
            eng = eng.split("(")[0].strip()
        key = eng or "(невідомо)"
        engines[key] = engines.get(key, 0) + 1
    return {"items": len(items), "avg_rating": avg, "engines": engines}


def record_batch_generate(
    wallet: str,
    count: int,
    engine: str,
    *,
    source: str = "pipeline",
    style_bible: bool = False,
) -> None:
    """Подія генерації batch у funnel.

    `source` — звідки генерація: `pipeline` (Етап 2 конвеєра) чи `classic`
    (вкладки Images / Collection). `style_bible` — чи активна Style Bible у сесії.
    Інструментація для §2.8 data-gate (рішення E6/E7): без `source`/`style_bible`
    Classic-частку й попит на PFP-consistency не виміряти.
    """
    if not wallet or count <= 0:
        return
    src = source if source in ("pipeline", "classic") else "pipeline"
    payment_service.record_funnel_event(
        wallet,
        "generate",
        {
            "count": int(count),
            "engine": _short_engine(engine),
            "source": src,
            "style_bible": bool(style_bible),
        },
    )


def record_curator_save(wallet: str, items: list[dict]) -> None:
    if not wallet or not items:
        return
    payment_service.record_funnel_event(wallet, "curator_save", build_curator_save_payload(items))


def _short_engine(engine: str) -> str:
    eng = (engine or "").strip()
    if "(" in eng:
        eng = eng.split("(")[0].strip()
    return eng or "(невідомо)"


def record_regenerate(wallet: str, index: int, engine: str, *, final: bool = False) -> None:
    """Подія перегенерації кадру (E1 — regenerate rate у quality_summary)."""
    if not wallet:
        return
    payment_service.record_funnel_event(
        wallet,
        "regenerate",
        {"index": int(index), "engine": _short_engine(engine), "final": bool(final)},
    )
