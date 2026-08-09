"""Агрегована статистика сайту над users.db (чисті функції, без Streamlit).

Читає ту саму базу, що й payment_service (через payment_service._connect, тож
поважає DB_PATH і працює з тестовою БД). Лише SELECT — нічого не змінює.
"""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timedelta, timezone

from services import payment_service, wallet_class


def _conn():
    return payment_service._connect()


def overview() -> dict:
    """Зведені показники: користувачі, дохід, кредити в обігу.

    Дохід подається двома числами: `revenue_usd` — **весь** дохід (оплата з
    власного гаманця через Helio офіційна: реальний USDC, комісія, кредити, які
    далі витрачаються на реальні виклики API) і `revenue_usd_external` — та його
    частина, що прийшла НЕ з наших гаманців (`services/wallet_class`).

    Зовнішній зріз — завжди присутній ключ, а не опційний параметр, бо саме його
    читають як **попит**: сумарне число на це питання не відповідає, коли платник
    і продавець — одна особа. Ніде не віднімаємо внутрішні оплати з доходу.
    """
    ext_sql, ext_params = wallet_class.scope_sql("external")
    with closing(_conn()) as c:
        users_total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        verified = c.execute(
            "SELECT COUNT(*) FROM users WHERE verified_at IS NOT NULL"
        ).fetchone()[0]
        outstanding = c.execute(
            "SELECT COALESCE(SUM(credits_balance), 0) FROM users"
        ).fetchone()[0]
        revenue = c.execute("SELECT COALESCE(SUM(amount_usd), 0) FROM payments").fetchone()[0]
        payments_count = c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        credits_sold = c.execute("SELECT COALESCE(SUM(credits), 0) FROM payments").fetchone()[0]
        ext = c.execute(
            "SELECT COALESCE(SUM(amount_usd), 0), COUNT(*), COALESCE(SUM(credits), 0) "
            "FROM payments WHERE 1 = 1" + ext_sql,
            ext_params,
        ).fetchone()
        users_ext = c.execute(
            "SELECT COUNT(*) FROM users WHERE 1 = 1" + ext_sql, ext_params
        ).fetchone()[0]
    revenue_ext = round(float(ext[0]), 2)
    return {
        "users_total": int(users_total),
        "users_verified": int(verified),
        "credits_outstanding": int(outstanding),  # невитрачені кредити = зобов'язання
        "revenue_usd": round(float(revenue), 2),
        "payments_count": int(payments_count),
        "credits_sold": int(credits_sold),
        "revenue_usd_external": revenue_ext,
        "revenue_usd_internal": round(float(revenue) - revenue_ext, 2),
        "payments_count_external": int(ext[1]),
        "credits_sold_external": int(ext[2]),
        "users_external": int(users_ext),
        "internal_wallets_known": len(wallet_class.internal_wallets()),
    }


def credits_by_kind() -> dict[str, int]:
    """Сума кредитів за видом транзакції (debit від'ємний — це витрачене)."""
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT kind, COALESCE(SUM(credits), 0) FROM transactions GROUP BY kind"
        ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def credits_by_kind_since(days: int | None = None) -> dict[str, int]:
    """Сума кредитів за видом транзакції за останні N днів (None — усе)."""
    if days is None or days <= 0:
        return credits_by_kind()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT kind, COALESCE(SUM(credits), 0) FROM transactions "
            "WHERE created_at >= ? GROUP BY kind",
            (cutoff,),
        ).fetchall()
    return {r[0]: int(r[1]) for r in rows}


def generations_by_engine() -> list[dict]:
    """Списання (kind='debit') за двигуном: кількість і витрачено кредитів."""
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT COALESCE(NULLIF(engine, ''), '(невідомо)') AS eng, COUNT(*), "
            "COALESCE(SUM(-credits), 0) FROM transactions WHERE kind = 'debit' "
            "GROUP BY eng ORDER BY 3 DESC"
        ).fetchall()
    return [
        {"engine": r[0], "count": int(r[1]), "credits_spent": int(r[2])} for r in rows
    ]


def new_users(days: int = 7) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with closing(_conn()) as c:
        row = c.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (cutoff,)
        ).fetchone()
    return int(row[0])


def funnel(days: int = 30, *, scope: str = "all") -> dict:
    """Воронка бети за вікно: реєстрація → verified → перший debit → оплата.

    churn_proxy — verified >30 днів тому, які жодного разу не списували кредити
    (фіксоване 30-денне вікно, незалежно від `days`).

    `scope` (`all` | `external` | `internal`) відсіює клас гаманця через
    `wallet_class.scope_sql`. Дефолт `all` лишає історичну поведінку; рішення про
    трафік (напр. guard достатності в `e67_gate_check`) мусять брати `external`,
    інакше власний dogfood закриває поріг зовнішнього попиту.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days)).isoformat()
    churn_cutoff = (now - timedelta(days=30)).isoformat()
    scope_sql, scope_params = wallet_class.scope_sql(scope)
    u_scope_sql, u_scope_params = wallet_class.scope_sql(scope, "u.wallet_address")
    with closing(_conn()) as c:
        new_users_n = c.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?" + scope_sql,
            (cutoff, *scope_params),
        ).fetchone()[0]

        # Когорти гаманців у вікні (МНОЖИНИ адрес). Конверсії раніше ділили на
        # `first_debit` (ПЕРШИЙ debit у вікні), а чисельник рахував зберігачів/
        # експортерів у вікні — ІНША когорта → можливі >100% (баг проявився від
        # першого зовнішнього трафіку: 2/1 = 200%). Тепер строгі підмножини:
        # перетин ⊆ знаменник, тож конверсія завжди ≤100%.
        def _wallets(sql: str) -> set[str]:
            return {r[0] for r in c.execute(sql + scope_sql, (cutoff, *scope_params)).fetchall()}

        verified_set = _wallets(
            "SELECT wallet_address FROM users WHERE verified_at IS NOT NULL AND verified_at >= ?"
        )
        payers = _wallets("SELECT DISTINCT wallet_address FROM payments WHERE created_at >= ?")
        generators = _wallets(
            "SELECT DISTINCT wallet_address FROM transactions WHERE kind = 'debit' AND created_at >= ?"
        )
        savers = _wallets(
            "SELECT DISTINCT wallet_address FROM funnel_events WHERE event = 'curator_save' AND created_at >= ?"
        )
        exporters = _wallets(
            "SELECT DISTINCT wallet_address FROM funnel_events WHERE event = 'export' AND created_at >= ?"
        )
        # `first_debit` (перший debit у вікні) — окрема метрика «нові генератори».
        # Фільтр класу — у внутрішньому запиті: інакше зріз рахував би MIN() по
        # всіх гаманцях і лише потім різав, тобто «перший debit» міг би належати
        # внутрішньому гаманцю, а лічильник — зовнішньому зрізу.
        first_debit = c.execute(
            "SELECT COUNT(*) FROM (SELECT wallet_address, MIN(created_at) m FROM transactions "
            "WHERE kind = 'debit'" + scope_sql + " GROUP BY wallet_address HAVING m >= ?)",
            (*scope_params, cutoff),
        ).fetchone()[0]
        churn = c.execute(
            "SELECT COUNT(*) FROM users u WHERE u.verified_at IS NOT NULL "
            "AND u.verified_at < ? AND NOT EXISTS ("
            "SELECT 1 FROM transactions t WHERE t.wallet_address = u.wallet_address "
            "AND t.kind = 'debit')" + u_scope_sql,
            (churn_cutoff, *u_scope_params),
        ).fetchone()[0]

    new_verified = len(verified_set)
    paying = len(payers)

    def _pct(num: set[str], denom: set[str]) -> float | None:
        """Конверсія як підмножина: |num ∩ denom| / |denom| (завжди ≤100%)."""
        return round(100 * len(num & denom) / len(denom), 1) if denom else None

    conversion = _pct(payers, verified_set)            # verified→paying
    save_conversion = _pct(savers, generators)         # generate→save
    export_conversion = _pct(exporters, generators)    # generate→export
    save_export_conversion = _pct(exporters, savers)   # save→export
    return {
        "days": days,
        "scope": scope,
        "new_users": int(new_users_n),
        "new_verified": new_verified,
        "first_debit_wallets": int(first_debit),
        "curator_save_wallets": len(savers),
        "exported_wallets": len(exporters),
        "paying_wallets": paying,
        "conversion_verified_to_paying_pct": conversion,
        "conversion_generate_to_save_pct": save_conversion,
        "conversion_save_to_export_pct": save_export_conversion,
        "conversion_generate_to_export_pct": export_conversion,
        "churn_proxy_verified_no_debit": int(churn),
    }


def _parse_ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _funnel_timeline(days: int, scope: str = "all") -> dict[str, list[tuple[str, str]]]:
    """Хронологія подій generate/regenerate/save/export по гаманцях."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    scope_sql, scope_params = wallet_class.scope_sql(scope)
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT wallet_address, created_at, event FROM funnel_events "
            "WHERE created_at >= ? AND event IN ('generate', 'regenerate', 'curator_save', 'export')"
            + scope_sql
            + " ORDER BY created_at",
            (cutoff, *scope_params),
        ).fetchall()
    by_wallet: dict[str, list[tuple[str, str]]] = {}
    for wallet, created_at, event in rows:
        by_wallet.setdefault(wallet, []).append((created_at, event))
    return by_wallet


def _save_without_regen_pct(by_wallet: dict[str, list[tuple[str, str]]]) -> float | None:
    """% curator_save після generate без regenerate між ними (евристика E1)."""
    saves_clean = 0
    saves_total = 0
    for timeline in by_wallet.values():
        for ts, ev in timeline:
            if ev != "curator_save":
                continue
            saves_total += 1
            last_gen: str | None = None
            had_regen = False
            for ts2, ev2 in timeline:
                if ts2 >= ts:
                    break
                if ev2 == "generate":
                    last_gen = ts2
                    had_regen = False
                elif ev2 == "regenerate" and last_gen is not None:
                    had_regen = True
            if last_gen is not None and not had_regen:
                saves_clean += 1
    return round(100 * saves_clean / saves_total, 1) if saves_total else None


def _median_export_minutes(by_wallet: dict[str, list[tuple[str, str]]]) -> float | None:
    """Медіана хвилин від НАЙБЛИЖЧОГО попереднього generate/regenerate до КОЖНОГО export.

    Сесійна латентність «згенерував → зібрав бандл» (ціль <15хв). Раніше брався span від
    ПЕРШОГО generate до ПЕРШОГО export на гаманець — він розтягувався крос-сесійно
    (оператор генерував увечері, експортував зранку → 746хв, спотворюючи медіану до 387,
    хоча реальні сесії — хвилини). Тепер кожен export рахується окремо за останньою
    генерацією перед ним; timeline відсортований за created_at у `_funnel_timeline`.
    """
    latencies: list[float] = []
    for timeline in by_wallet.values():
        last_gen: str | None = None
        for ts, ev in timeline:
            if ev in ("generate", "regenerate"):
                last_gen = ts
            elif ev == "export" and last_gen is not None:
                delta = (_parse_ts(ts) - _parse_ts(last_gen)).total_seconds() / 60
                if delta >= 0:
                    latencies.append(delta)
    if not latencies:
        return None
    latencies.sort()
    mid = len(latencies) // 2
    if len(latencies) % 2:
        return round(latencies[mid], 1)
    return round((latencies[mid - 1] + latencies[mid]) / 2, 1)


def quality_summary(days: int = 30, *, scope: str = "all") -> dict:
    """Агрегати якості з curator_save payload за вікно (D4 + E1).

    `scope` — як у `funnel`: дефолт `all`, а пороги §2.8 (Style Bible / Classic
    частка) рахуються по `external`, бо описують поведінку користувачів, не нашу.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    scope_sql, scope_params = wallet_class.scope_sql(scope)
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT payload FROM funnel_events "
            "WHERE event = 'curator_save' AND created_at >= ? AND payload IS NOT NULL" + scope_sql,
            (cutoff, *scope_params),
        ).fetchall()
        generate_events = c.execute(
            "SELECT COUNT(*) FROM funnel_events WHERE event = 'generate' AND created_at >= ?"
            + scope_sql,
            (cutoff, *scope_params),
        ).fetchone()[0]
        regenerate_events = c.execute(
            "SELECT COUNT(*) FROM funnel_events WHERE event = 'regenerate' AND created_at >= ?"
            + scope_sql,
            (cutoff, *scope_params),
        ).fetchone()[0]
        gen_payload_rows = c.execute(
            "SELECT payload FROM funnel_events "
            "WHERE event = 'generate' AND created_at >= ? AND payload IS NOT NULL" + scope_sql,
            (cutoff, *scope_params),
        ).fetchall()
    rating_weighted_sum = 0.0
    rating_weight = 0
    total_items = 0
    engine_counts: dict[str, int] = {}
    for (payload_json,) in rows:
        try:
            data = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError):
            continue
        items_n = int(data.get("items") or 0)
        total_items += items_n
        avg = data.get("avg_rating")
        if avg is not None and items_n > 0:
            rating_weighted_sum += float(avg) * items_n
            rating_weight += items_n
        for eng, cnt in (data.get("engines") or {}).items():
            engine_counts[str(eng)] = engine_counts.get(str(eng), 0) + int(cnt)
    avg_rating = round(rating_weighted_sum / rating_weight, 2) if rating_weight else None
    top_engine = max(engine_counts, key=engine_counts.get) if engine_counts else None
    by_wallet = _funnel_timeline(days, scope)
    gen_n = int(generate_events)
    regen_n = int(regenerate_events)
    regenerate_rate = round(100 * regen_n / gen_n, 1) if gen_n else None
    # §2.8: розбивка генерацій за джерелом (classic/pipeline) + Style Bible-частка.
    # Лічимо за кількістю зображень (`count` у payload). Legacy-події без `source`
    # потрапляють у `untracked` (не псують частку — рахуємо лише з відомим source).
    source_images = {"pipeline": 0, "classic": 0, "untracked": 0}
    style_bible_images = 0
    for (payload_json,) in gen_payload_rows:
        try:
            data = json.loads(payload_json)
        except (TypeError, json.JSONDecodeError):
            continue
        cnt = int(data.get("count") or 0)
        src = data.get("source")
        source_images[src if src in ("pipeline", "classic") else "untracked"] += cnt
        if data.get("style_bible"):
            style_bible_images += cnt
    tracked = source_images["pipeline"] + source_images["classic"]
    classic_share = round(100 * source_images["classic"] / tracked, 1) if tracked else None
    style_bible_share = round(100 * style_bible_images / tracked, 1) if tracked else None
    return {
        "days": days,
        "scope": scope,
        "save_events": len(rows),
        "total_items_saved": total_items,
        "avg_curator_rating": avg_rating,
        "top_engine_by_saves": top_engine,
        "engine_save_counts": engine_counts,
        "generate_events": gen_n,
        "regenerate_events": regen_n,
        "regenerate_rate_pct": regenerate_rate,
        "save_without_regen_pct": _save_without_regen_pct(by_wallet),
        "median_export_minutes": _median_export_minutes(by_wallet),
        "generate_source_images": source_images,
        "classic_share_pct": classic_share,
        "style_bible_images": style_bible_images,
        "style_bible_share_pct": style_bible_share,
    }


def payments_by_package() -> list[dict]:
    """Розбивка оплат за пакетами (евристика amount_usd+credits → PACKAGES)."""
    lookup = {
        (round(float(p["usd"]), 2), int(p["credits"])): pid
        for pid, p in payment_service.PACKAGES.items()
    }
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT amount_usd, credits, COUNT(*) FROM payments "
            "GROUP BY amount_usd, credits ORDER BY 3 DESC"
        ).fetchall()
    out = []
    for amount, credits, n in rows:
        pid = lookup.get((round(float(amount), 2), int(credits)), "невідомо")
        out.append({
            "package_id": pid,
            "amount_usd": round(float(amount), 2),
            "credits": int(credits),
            "count": int(n),
        })
    return out


def sybil_candidates(limit: int = 20, min_spent: int = 20) -> list[dict]:
    """Гаманці з великими списаннями, але БЕЗ оплат — кандидати на Sybil/abuse."""
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT t.wallet_address, COUNT(*), COALESCE(SUM(-t.credits), 0) AS spent, "
            "MIN(t.created_at) "
            "FROM transactions t WHERE t.kind = 'debit' "
            "AND t.wallet_address NOT IN (SELECT wallet_address FROM payments) "
            "GROUP BY t.wallet_address HAVING spent > ? "
            "ORDER BY spent DESC LIMIT ?",
            (min_spent, limit),
        ).fetchall()
    # Внутрішні гаманці лишаємо у списку, але з позначкою: оператор із grant-ами
    # (574 списання, 0 оплат) — сталий «кандидат», і тихо ховати його означало б
    # зробити перевірку неповною. Позначка дає відсіяти око, не втративши рядок.
    return [
        {"wallet": r[0], "debits": int(r[1]), "credits_spent": int(r[2]),
         "first_seen": (r[3] or "")[:19], "internal": wallet_class.is_internal(r[0])}
        for r in rows
    ]


def recent_payments(limit: int = 10) -> list[dict]:
    """Останні оплати (для адмін-стрічки)."""
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT wallet_address, amount_usd, credits, created_at FROM payments "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"wallet": r[0], "amount_usd": round(float(r[1]), 2), "credits": int(r[2]),
         "created_at": (r[3] or "")[:19], "internal": wallet_class.is_internal(r[0])}
        for r in rows
    ]


def top_wallets(limit: int = 10) -> list[dict]:
    """Найактивніші гаманці за витраченими кредитами (kind='debit')."""
    with closing(_conn()) as c:
        rows = c.execute(
            "SELECT wallet_address, COUNT(*), COALESCE(SUM(-credits), 0) "
            "FROM transactions WHERE kind = 'debit' GROUP BY wallet_address "
            "ORDER BY 3 DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"wallet": r[0], "debits": int(r[1]), "credits_spent": int(r[2]),
         "internal": wallet_class.is_internal(r[0])}
        for r in rows
    ]
