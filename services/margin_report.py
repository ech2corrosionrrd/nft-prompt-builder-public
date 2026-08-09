"""Оцінка валової маржі: виручка з payments vs орієнтовна API-собівартість debit.

Чисті функції без Streamlit — тестуються без мережі. API $/оп. — орієнтири з
ai_service._ENGINE_COSTS і ПЛАН_БІЗНЕС.md; фактичні інвойси провайдерів не в БД.
"""

from __future__ import annotations

import math
import os
from contextlib import closing
from datetime import datetime, timedelta, timezone

from services import payment_service, provider_spend, stats, wallet_class
from services.ai_service import (
    ENGINE_DALLE3,
    ENGINE_FLUX,
    ENGINE_GPT_IMAGE,
    ENGINE_STABILITY,
)

# USD за одну API-операцію (1 debit-транзакція ≈ 1 виклик для зображень).
API_USD_PER_OP: dict[str, float] = {
    ENGINE_FLUX: 0.003,
    ENGINE_STABILITY: 0.030,
    ENGINE_DALLE3: 0.040,
    ENGINE_GPT_IMAGE: 0.042,
    "LLM": 0.0003,
    "vision": 0.020,
}
DEFAULT_API_USD = 0.010
STABILITY_ENGINE = ENGINE_STABILITY


def api_usd_per_op(engine: str) -> float:
    """Орієнтовна собівартість однієї debit-операції за двигуном."""
    return API_USD_PER_OP.get(engine, DEFAULT_API_USD)


def _cutoff_iso(days: int | None) -> str | None:
    if days is None or days <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _payment_totals(since: str | None, *, scope: str = "all") -> tuple[float, int, int]:
    """(revenue_usd, credits_sold, payments_count) за період або all-time.

    `scope='external'` відсіює наші гаманці (`services/wallet_class`). Маржа
    рахується по **всьому** виторгу — оплата з власного гаманця офіційна, кредити
    з неї витрачаються на реальні виклики API, тож собівартість і ціна кредита від
    особи платника не залежать. Зріз потрібен лише там, де число читають як
    **попит** (гейт §2.8), і в звіті — як довідка про джерело.
    """
    scope_sql, scope_params = wallet_class.scope_sql(scope)
    with closing(payment_service._connect()) as c:
        row = c.execute(
            "SELECT COALESCE(SUM(amount_usd), 0), COALESCE(SUM(credits), 0), COUNT(*) "
            "FROM payments WHERE 1 = 1"
            + (" AND created_at >= ?" if since else "")
            + scope_sql,
            ((since,) if since else ()) + tuple(scope_params),
        ).fetchone()
    return float(row[0]), int(row[1]), int(row[2])


def generations_for_period(days: int | None = None) -> list[dict]:
    """Списання debit за двигуном (як stats.generations_by_engine), опційно за N днів."""
    since = _cutoff_iso(days)
    with closing(payment_service._connect()) as c:
        if since:
            rows = c.execute(
                "SELECT COALESCE(NULLIF(engine, ''), '(невідомо)') AS eng, COUNT(*), "
                "COALESCE(SUM(-credits), 0) FROM transactions "
                "WHERE kind = 'debit' AND created_at >= ? GROUP BY eng ORDER BY 3 DESC",
                (since,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT COALESCE(NULLIF(engine, ''), '(невідомо)') AS eng, COUNT(*), "
                "COALESCE(SUM(-credits), 0) FROM transactions "
                "WHERE kind = 'debit' GROUP BY eng ORDER BY 3 DESC"
            ).fetchall()
    return [
        {"engine": r[0], "count": int(r[1]), "credits_spent": int(r[2])} for r in rows
    ]


def credits_debited_for_period(days: int | None = None) -> int:
    since = _cutoff_iso(days)
    with closing(payment_service._connect()) as c:
        if since:
            row = c.execute(
                "SELECT COALESCE(SUM(-credits), 0) FROM transactions "
                "WHERE kind = 'debit' AND created_at >= ?",
                (since,),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT COALESCE(SUM(-credits), 0) FROM transactions WHERE kind = 'debit'"
            ).fetchone()
    return int(row[0])


def estimated_api_cost_usd(generations: list[dict] | None = None) -> float:
    rows = generations if generations is not None else stats.generations_by_engine()
    return sum(row["count"] * api_usd_per_op(row["engine"]) for row in rows)


def avg_revenue_per_credit(revenue_usd: float, credits_sold: int) -> float:
    if credits_sold <= 0:
        return 0.0
    return revenue_usd / credits_sold


def stability_share_pct(generations: list[dict], credits_debited: int) -> float | None:
    if credits_debited <= 0:
        return None
    stab = next(
        (r["credits_spent"] for r in generations if r["engine"] == STABILITY_ENGINE),
        0,
    )
    return round(100 * stab / credits_debited, 1)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def _data_span_days() -> int:
    """Днів від першої оплати до зараз — для пропорції фікс-косту в all-time."""
    with closing(payment_service._connect()) as c:
        row = c.execute("SELECT MIN(created_at) FROM payments").fetchone()
    if not row or not row[0]:
        return 30
    try:
        first = datetime.fromisoformat(row[0])
    except ValueError:
        return 30
    return max(1, (datetime.now(timezone.utc) - first).days)


def net_margin_report(days: int | None = None, *, gross: dict | None = None) -> dict:
    """Чиста маржа: валова мінус комісія платежу, обмін крипти й фіксовані витрати.

    Параметри з env (налаштовні): PAYMENT_FEE_PCT (Helio, дефолт 1.0),
    FX_FEE_PCT (off-ramp USDC→фіат, дефолт 2.0), FIXED_MONTHLY_USD (хостинг+домен,
    дефолт 0 — self-host). Фікс-кост пропорційний періоду (30д = 1 міс; all-time —
    за фактичним проміжком даних). API-собівартість — фактична, якщо є імпорти.
    """
    r = gross if gross is not None else gross_margin_report(days)
    revenue = r["revenue_usd"]
    api_cost = r["actual_api_usd"] if r.get("actual_api_usd") is not None else r["estimated_api_usd"]

    pay_pct = _env_float("PAYMENT_FEE_PCT", 1.0)
    fx_pct = _env_float("FX_FEE_PCT", 2.0)
    fixed_monthly = _env_float("FIXED_MONTHLY_USD", 0.0)
    period_days = days if days is not None else _data_span_days()

    payment_fee = round(revenue * pay_pct / 100, 2)
    fx_fee = round(revenue * fx_pct / 100, 2)
    fixed_cost = round(fixed_monthly * period_days / 30.0, 2)
    net_profit = round(revenue - api_cost - payment_fee - fx_fee - fixed_cost, 2)
    net_margin_pct = round(100 * net_profit / revenue, 1) if revenue > 0 else None

    return {
        "revenue_usd": round(revenue, 2),
        "api_cost_usd": round(api_cost, 4),
        "payment_fee_usd": payment_fee,
        "fx_fee_usd": fx_fee,
        "fixed_cost_usd": fixed_cost,
        "net_profit_usd": net_profit,
        "net_margin_pct": net_margin_pct,
        "payment_fee_pct": pay_pct,
        "fx_fee_pct": fx_pct,
        "fixed_monthly_usd": fixed_monthly,
        "period_days": period_days,
    }


def gross_margin_report(days: int | None = None) -> dict:
    """Зведений звіт маржі. days=None — all-time; 7/30 — вікно з created_at."""
    ov = stats.overview()
    since = _cutoff_iso(days)
    revenue, sold, payments_count = _payment_totals(since)
    revenue_ext, _sold_ext, payments_ext = _payment_totals(since, scope="external")
    # Для середньої ціни кредита: якщо у вікні продажів не було — беремо all-time,
    # щоб оцінка маржі лишалась осмисленою (виручка/кредити в звіті — за період).
    avg_revenue, avg_sold = revenue, sold
    if days is not None and sold == 0:
        avg_revenue, avg_sold, _ = _payment_totals(None)

    by_engine = generations_for_period(days)
    debited = credits_debited_for_period(days)
    api_cost = estimated_api_cost_usd(by_engine)
    avg = avg_revenue_per_credit(avg_revenue, avg_sold)
    rev_on_deb = debited * avg
    arpu = round(revenue / payments_count, 2) if payments_count > 0 else None
    margin_pct: float | None = None
    if rev_on_deb > 0:
        margin_pct = round(100 * (1 - api_cost / rev_on_deb), 1)

    utilization: float | None = None
    if ov["credits_sold"] > 0:
        utilization = round(100 * debited / ov["credits_sold"], 1)

    outstanding_ratio: float | None = None
    if ov["credits_sold"] > 0:
        outstanding_ratio = round(100 * ov["credits_outstanding"] / ov["credits_sold"], 1)

    engine_costs = [
        {
            "engine": r["engine"],
            "ops": r["count"],
            "credits_spent": r["credits_spent"],
            "api_usd": round(r["count"] * api_usd_per_op(r["engine"]), 4),
        }
        for r in by_engine
    ]

    period_label = f"{days}d" if days else "all"

    actual_api = provider_spend.total_usd(days)
    actual_margin_pct: float | None = None
    has_actual = actual_api > 0
    api_delta: float | None = None
    if has_actual:
        api_delta = round(actual_api - api_cost, 4)
        if rev_on_deb > 0:
            actual_margin_pct = round(100 * (1 - actual_api / rev_on_deb), 1)

    welcome_credits_net = stats.credits_by_kind_since(days).get("welcome", 0)

    return {
        "period": period_label,
        "revenue_usd": round(revenue, 2),
        "revenue_usd_external": round(revenue_ext, 2),
        "revenue_usd_internal": round(revenue - revenue_ext, 2),
        "payments_count_external": payments_ext,
        "credits_sold": sold,
        "payments_count": payments_count,
        "arpu_usd": arpu,
        "welcome_credits_net": welcome_credits_net,
        "credits_debited": debited,
        "credits_outstanding": ov["credits_outstanding"],
        "avg_usd_per_credit": round(avg, 4),
        "estimated_api_usd": round(api_cost, 4),
        "actual_api_usd": round(actual_api, 4) if has_actual else None,
        "api_delta_usd": api_delta,
        "estimated_revenue_on_debited_usd": round(rev_on_deb, 2),
        "gross_margin_pct": margin_pct,
        "actual_gross_margin_pct": actual_margin_pct,
        "has_actual_imports": has_actual,
        "credits_utilization_pct": utilization,
        "outstanding_ratio_pct": outstanding_ratio,
        "stability_share_pct": stability_share_pct(by_engine, debited),
        "by_engine_cost": engine_costs,
        "actual_by_provider": provider_spend.by_provider(days) if has_actual else [],
    }


def _blended_api_per_credit() -> float:
    """Середня API-собівартість на 1 списаний кредит (all-time). Фолбек $0.005."""
    by_engine = generations_for_period(None)
    debited = credits_debited_for_period(None)
    if debited <= 0:
        return 0.005
    return estimated_api_cost_usd(by_engine) / debited


def break_even_summary(*, package_price: float = 4.99, package_credits: int = 100) -> dict:
    """Скільки оплат «Start» на місяць покриває фіксовані витрати + скільки вже є.

    Внесок на пакет = ціна − API(blended×credits) − Helio% − FX%. Беззбитковість =
    ceil(FIXED_MONTHLY_USD / внесок). «Цього місяця» — поточний календарний місяць.
    break_even_count=0, якщо фікс=0 (self-host) або внесок недодатний.
    """
    fixed = _env_float("FIXED_MONTHLY_USD", 0.0)
    fees = _env_float("PAYMENT_FEE_PCT", 1.0) / 100 + _env_float("FX_FEE_PCT", 2.0) / 100
    blended = _blended_api_per_credit()
    api = package_credits * blended
    contribution = round(package_price - api - package_price * fees, 2)
    needed = math.ceil(fixed / contribution) if (fixed > 0 and contribution > 0) else 0

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    rev_month, _, count_month = _payment_totals(month_start)

    return {
        "package_price": package_price,
        "package_credits": package_credits,
        "fixed_monthly_usd": round(fixed, 2),
        "blended_api_per_credit": round(blended, 5),
        "contribution_usd": contribution,
        "break_even_count": needed,
        "payments_this_month": count_month,
        "revenue_this_month": round(rev_month, 2),
        "remaining": max(0, needed - count_month) if needed > 0 else 0,
        "covered_pct": round(100 * count_month / needed) if needed > 0 else None,
    }


def format_report_text(report: dict | None = None, *, days: int | None = None) -> str:
    """Текстовий звіт для CLI / Telegram."""
    r = report if report is not None else gross_margin_report(days)
    lines = [
        f"📈 Маржа ({r['period']})",
        f"Дохід (період продажів): ${r['revenue_usd']} · продано {r['credits_sold']} cr",
    ]
    # Джерело оплат друкуємо лише коли є свої: за нульового dogfood це шум.
    # Формулювання нейтральне — обидві частини входять у дохід і в маржу вище;
    # рядок відповідає на «звідки прийшли гроші», не на «чи вони справжні».
    if r.get("revenue_usd_internal"):
        lines.append(
            f"  ├ джерело: зовнішні ${r['revenue_usd_external']}"
            f" ({r['payments_count_external']} оплат) · свої ${r['revenue_usd_internal']}"
        )
    lines += [
        f"Списано: {r['credits_debited']} cr · avg ${r['avg_usd_per_credit']}/cr",
        f"Оцінка API: ${r['estimated_api_usd']} · виручка на списані cr: "
        f"${r['estimated_revenue_on_debited_usd']}",
    ]
    if r["gross_margin_pct"] is not None:
        lines.append(f"Валова маржа (оцінка): {r['gross_margin_pct']}%")
    else:
        lines.append("Валова маржа (оцінка): — (немає списань)")
    if r.get("has_actual_imports") and r.get("actual_api_usd") is not None:
        act_m = r.get("actual_gross_margin_pct")
        act_line = f"Факт API: ${r['actual_api_usd']}"
        if act_m is not None:
            act_line += f" · маржа {act_m}%"
        lines.append(act_line)
    if r["credits_utilization_pct"] is not None:
        lines.append(
            f"Utilization: {r['credits_utilization_pct']}% · "
            f"в обігу: {r['credits_outstanding']} cr ({r['outstanding_ratio_pct']}%)"
        )
    if r["stability_share_pct"] is not None:
        flag = " ⚠️" if r["stability_share_pct"] > 40 else ""
        lines.append(f"Stability серед debit: {r['stability_share_pct']}%{flag}")
    if r["by_engine_cost"]:
        top = " · ".join(
            f"{e['engine']}×{e['ops']} (${e['api_usd']})" for e in r["by_engine_cost"][:4]
        )
        lines.append(f"API за двигунами: {top}")
    return "\n".join(lines)
