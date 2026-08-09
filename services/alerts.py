"""Операторські алерти: низький баланс провайдерів + денний дайджест статистики.

Чисті функції побудови тексту й рішення «алертити» (тестуються без мережі);
надсилання — через services.notify.send_telegram. Прямий API-баланс має лише
Stability, тож low-balance стосується його; дайджест — зведення з services.stats.
"""

from __future__ import annotations

import os

from services import margin_report, offsite_status, provider_status, stats, storage_gc

STABILITY_LOW_DEFAULT = 100.0
QUALITY_RATING_DEFAULT = 3.5
QUALITY_SAVE_EXPORT_DEFAULT = 30.0
_FETCH = object()  # sentinel: «дістати баланс з мережі» (відрізняє від явного None = «балансу нема»)


def stability_threshold() -> float:
    """Поріг низького балансу Stability (кредити) — env STABILITY_LOW_BALANCE."""
    try:
        return float(os.environ.get("STABILITY_LOW_BALANCE") or STABILITY_LOW_DEFAULT)
    except ValueError:
        return STABILITY_LOW_DEFAULT


def quality_min_rating() -> float:
    """Поріг середнього рейтингу куратора для алерту (E5)."""
    try:
        return float(os.environ.get("QUALITY_ALERT_MIN_RATING") or QUALITY_RATING_DEFAULT)
    except ValueError:
        return QUALITY_RATING_DEFAULT


def quality_min_save_export_pct() -> float:
    """Поріг конверсії save→export % для алерту (E5)."""
    try:
        return float(os.environ.get("QUALITY_ALERT_MIN_SAVE_EXPORT_PCT") or QUALITY_SAVE_EXPORT_DEFAULT)
    except ValueError:
        return QUALITY_SAVE_EXPORT_DEFAULT


def quality_alert_items(
    quality: dict,
    funnel: dict,
    *,
    min_rating: float | None = None,
    min_save_export: float | None = None,
) -> list[dict]:
    """Структуровані алерти якості (код + поля для i18n у адмінці)."""
    items: list[dict] = []
    rating_thr = quality_min_rating() if min_rating is None else min_rating
    save_thr = quality_min_save_export_pct() if min_save_export is None else min_save_export

    avg = quality.get("avg_curator_rating")
    if avg is not None and float(avg) < rating_thr:
        items.append({
            "code": "low_rating",
            "avg": round(float(avg), 2),
            "threshold": rating_thr,
        })

    save_export = funnel.get("conversion_save_to_export_pct")
    if (
        int(funnel.get("curator_save_wallets") or 0) > 0
        and save_export is not None
        and float(save_export) < save_thr
    ):
        items.append({
            "code": "low_save_export",
            "pct": round(float(save_export), 1),
            "threshold": save_thr,
        })
    return items


def quality_alert_messages(
    quality: dict,
    funnel: dict,
    *,
    min_rating: float | None = None,
    min_save_export: float | None = None,
) -> list[str]:
    """Текстові алерти якості конвеєра (дайджест Telegram)."""
    msgs: list[str] = []
    for item in quality_alert_items(
        quality, funnel, min_rating=min_rating, min_save_export=min_save_export,
    ):
        if item["code"] == "low_rating":
            msgs.append(
                f"⚠️ Якість: сер. рейтинг куратора {item['avg']:.2f} "
                f"< поріг {item['threshold']:.1f}"
            )
        elif item["code"] == "low_save_export":
            msgs.append(
                f"⚠️ Воронка: save→export {item['pct']:.1f}% "
                f"< поріг {item['threshold']:.0f}%"
            )
    return msgs


def low_balance_messages(balance=_FETCH) -> list[str]:
    """Повідомлення про низький баланс (порожньо, якщо норма / балансу нема).

    balance можна передати (напр. з кешу панелі), щоб не робити зайвий запит;
    явний None = «балансу немає» (Stability не налаштовано) → без алерту й без мережі.
    """
    bal = provider_status.stability_balance() if balance is _FETCH else balance
    msgs: list[str] = []
    thr = stability_threshold()
    if bal is not None and bal < thr:
        msgs.append(
            f"⚠️ Stability AI: низький баланс {bal:.0f} cr (поріг {thr:.0f}).\n"
            f"Поповнити: https://platform.stability.ai/account/credits"
        )
    return msgs


def digest_text() -> str:
    """Текст денного дайджесту: статистика сайту + баланс Stability."""
    ov = stats.overview()
    lines = [
        "📊 NFT Prompt Builder — дайджест",
        f"👛 Гаманців: {ov['users_total']} (verified {ov['users_verified']}) "
        f"· нових за 24г: {stats.new_users(1)}",
        f"💵 Дохід: ${ov['revenue_usd']} · кредитів в обігу: {ov['credits_outstanding']}",
    ]
    bal = provider_status.stability_balance()
    if bal is not None:
        lines.append(f"🎨 Stability баланс: {bal:.0f} cr")
    eng = stats.generations_by_engine()
    if eng:
        top = " · ".join(f"{e['engine']}×{e['count']}" for e in eng[:3])
        lines.append(f"🖼 Генерації (топ): {top}")
    mr = margin_report.gross_margin_report()
    if mr["gross_margin_pct"] is not None:
        lines.append(
            f"📈 Оцінка маржі: {mr['gross_margin_pct']}% "
            f"(API ~${mr['estimated_api_usd']}, {mr['credits_debited']} cr списано)"
        )
    if mr.get("has_actual_imports") and mr.get("actual_gross_margin_pct") is not None:
        lines.append(
            f"💳 Факт маржа: {mr['actual_gross_margin_pct']}% "
            f"(імпорт API ${mr['actual_api_usd']})"
        )
    be = margin_report.break_even_summary()
    if be["break_even_count"] > 0:
        lines.append(
            f"🎯 Беззбитковість: {be['payments_this_month']}/{be['break_even_count']} Start цього міс "
            f"({be['covered_pct']}%, бракує {be['remaining']}; фікс ${be['fixed_monthly_usd']})"
        )
    lines.append(offsite_status.status_line())
    lines.append(offsite_status.host_status_line())
    lines.append(offsite_status.metadata_status_line())
    lines.append(storage_gc.digest_line())
    fn = stats.funnel(7)
    qs = stats.quality_summary(7)
    q_alerts = quality_alert_messages(qs, fn)
    lines.extend(q_alerts)
    return "\n".join(lines)
