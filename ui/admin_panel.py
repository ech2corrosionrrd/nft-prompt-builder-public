"""Адмін-панель: статистика сайту + стан провайдерів.

Рендериться лише для гаманців зі списку ADMIN_WALLETS (гейт у app.py через
services.admin_access.is_admin). Чиста логіка — у services/stats.py,
services/margin_report.py, services/provider_status.py, services/ops_status.py,
services/provider_spend.py; тут лише відображення. UI-рядки локалізовані (uk+en)
через ui_strings.t — namespace adm.*.

Структура (ADM-D): 5 вкладок st.tabs — Огляд / Економіка / Користувачі / Ops /
Провайдери. Період обирається у «Огляд» і застосовується до Економіки й
Користувачів (st.tabs виконують усі блоки в одному run, тож значення спільне).
"""

from __future__ import annotations

import hashlib

import streamlit as st

from services import (
    alerts,
    margin_report,
    mint_path,
    notify,
    ops_status,
    provider_spend,
    provider_status,
    stats,
    workspace_limits,
)
from ui_strings import t


@st.cache_data(ttl=300, show_spinner=False)
def _cached_health() -> list[dict]:
    """Стан провайдерів із кешем ~5 хв — щоб валідність показувалась одразу, але не
    бити по API на кожен ререндер. Кнопка «Оновити» скидає кеш."""
    return provider_status.key_health()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_readiness() -> dict:
    """Операційний стан (health + env + секрети) з кешем ~5 хв (ADM-C)."""
    return ops_status.readiness_summary()


@st.cache_data(ttl=300, show_spinner=False)
def _cached_float() -> list[dict]:
    """Провайдерський флоат (рек. мінімум vs баланс) з кешем ~5 хв (проба Stability)."""
    return provider_status.provider_float_status()


def _render_overview() -> tuple[str, int | None]:
    """Огляд + перемикач періоду. Повертає (період-підпис, days|None)."""
    ov = stats.overview()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("adm.ov.wallets"), ov["users_total"], help=t("adm.ov.wallets_help"))
    c2.metric(t("adm.ov.verified"), ov["users_verified"], help=t("adm.ov.verified_help"))
    c3.metric(t("adm.ov.revenue"), f"${ov['revenue_usd']}", help=t("adm.ov.revenue_help", count=ov["payments_count"]))
    c4.metric(t("adm.ov.outstanding"), ov["credits_outstanding"], help=t("adm.ov.outstanding_help"))
    st.caption(t("adm.ov.sold_caption", sold=ov["credits_sold"], n7=stats.new_users(7), n30=stats.new_users(30)))
    # Клас гаманця: сумарний виторг включає наш dogfood (він платить реальними
    # грошима), тож зовнішній зріз показуємо поруч — інакше огляд читається як попит.
    if ov["revenue_usd_internal"]:
        st.caption(
            t(
                "adm.ov.external_caption",
                rev=ov["revenue_usd_external"],
                count=ov["payments_count_external"],
                internal=ov["revenue_usd_internal"],
                wallets=ov["users_external"],
            )
        )

    st.divider()
    # value-ключі періоду стабільні (en), підписи перекладені через format_func.
    _period_labels = {"7d": t("adm.period.7d"), "30d": t("adm.period.30d"), "all": t("adm.period.all")}
    period_key = st.radio(
        t("adm.period.label"),
        ["7d", "30d", "all"],
        index=2,
        horizontal=True,
        format_func=lambda k: _period_labels[k],
        help=t("adm.period.help"),
    )
    period_choice = _period_labels[period_key]
    days = {"7d": 7, "30d": 30, "all": None}[period_key]
    return period_choice, days


def _render_economics(period_choice: str, days: int | None) -> None:
    """Маржа, KPI, генерації за двигуном + імпорт фактичних витрат (ADM-D.2)."""
    mr = margin_report.gross_margin_report(days)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("adm.econ.est_api"), f"${mr['estimated_api_usd']}", help=t("adm.econ.est_api_help"))
    actual_val = mr.get("actual_api_usd")
    delta_val = mr.get("api_delta_usd")
    m2.metric(
        t("adm.econ.actual_api"),
        f"${actual_val}" if actual_val is not None else "—",
        delta=t("adm.econ.delta_vs_est", delta=delta_val) if delta_val is not None else None,
        delta_color="inverse",  # вищі витрати = гірше
        help=t("adm.econ.actual_api_help"),
    )
    m3.metric(
        t("adm.econ.margin_est"),
        f"{mr['gross_margin_pct']}%" if mr["gross_margin_pct"] is not None else "—",
        help=t("adm.econ.margin_help"),
    )
    act_margin = mr.get("actual_gross_margin_pct")
    m4.metric(
        t("adm.econ.margin_actual"),
        f"{act_margin}%" if act_margin is not None else "—",
        help=t("adm.econ.margin_actual_help"),
    )
    u1, u2 = st.columns(2)
    u1.metric(
        "Utilization",
        f"{mr['credits_utilization_pct']}%" if mr["credits_utilization_pct"] is not None else "—",
        help=t("adm.econ.util_help"),
    )
    stab = mr["stability_share_pct"]
    u2.metric(
        "Stability % debit",
        f"{stab}%" if stab is not None else "—",
        help=t("adm.econ.stab_help"),
    )
    arpu = mr.get("arpu_usd")
    st.caption(t(
        "adm.econ.arpu_caption",
        arpu=("$%.2f" % arpu) if arpu is not None else "—",
        count=mr["payments_count"], avg=mr["avg_usd_per_credit"], welcome=mr["welcome_credits_net"],
    ))
    if mr.get("actual_by_provider"):
        st.caption(
            t("adm.econ.import_by_provider")
            + " · ".join(f"{p['provider']} ${p['amount_usd']}" for p in mr["actual_by_provider"])
        )
    if stab is not None and stab > 40:
        st.warning(t("adm.econ.stab_warn", stab=stab))

    st.divider()
    st.markdown(t("adm.econ.net_title"))
    nm = margin_report.net_margin_report(days, gross=mr)
    n1, n2, n3 = st.columns(3)
    n1.metric(t("adm.econ.net_profit"), f"${nm['net_profit_usd']}", help=t("adm.econ.net_profit_help"))
    n2.metric(t("adm.econ.net_margin"), f"{nm['net_margin_pct']}%" if nm["net_margin_pct"] is not None else "—",
              help=t("adm.econ.net_margin_help"))
    n3.metric(t("adm.econ.fixed_period"), f"${nm['fixed_cost_usd']}",
              help=t("adm.econ.fixed_period_help", monthly=nm["fixed_monthly_usd"], days=nm["period_days"]))
    st.caption(t(
        "adm.econ.net_caption",
        rev=nm["revenue_usd"], api=nm["api_cost_usd"], fee_pct=nm["payment_fee_pct"], fee=nm["payment_fee_usd"],
        fx_pct=nm["fx_fee_pct"], fx=nm["fx_fee_usd"], fixed=nm["fixed_cost_usd"], net=nm["net_profit_usd"],
    ))

    be = margin_report.break_even_summary()
    if be["break_even_count"] > 0:
        st.divider()
        st.markdown(t("adm.econ.be_title"))
        b1, b2, b3 = st.columns(3)
        b1.metric(t("adm.econ.be_need"), be["break_even_count"],
                  help=t("adm.econ.be_need_help", fixed=be["fixed_monthly_usd"], contrib=be["contribution_usd"]))
        b2.metric(t("adm.econ.be_this_month"), be["payments_this_month"],
                  help=t("adm.econ.be_this_month_help", rev=be["revenue_this_month"]))
        b3.metric(t("adm.econ.be_remaining"), be["remaining"], help=t("adm.econ.be_remaining_help"))
        st.progress(
            min(1.0, be["payments_this_month"] / be["break_even_count"]),
            text=t("adm.econ.be_progress", pct=be["covered_pct"],
                   have=be["payments_this_month"], need=be["break_even_count"]),
        )
        st.caption(t(
            "adm.econ.be_caption",
            contrib=be["contribution_usd"], price=be["package_price"],
            api=round(be["blended_api_per_credit"] * be["package_credits"], 2),
        ))
    elif nm["fixed_monthly_usd"] == 0:
        st.caption(t("adm.econ.be_zero"))

    st.markdown(t("adm.econ.by_engine_title", period=period_choice.lower()))
    by_engine = mr["by_engine_cost"]
    st.dataframe(
        [{t("adm.col.engine"): e["engine"], t("adm.col.ops"): e["ops"],
          t("adm.col.credits"): e["credits_spent"], t("adm.col.api_est"): e["api_usd"]} for e in by_engine],
        width='stretch', hide_index=True,
    ) if by_engine else st.caption(t("adm.econ.no_debits"))

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(t("adm.econ.credits_by_kind"))
        kinds = stats.credits_by_kind()
        st.dataframe(
            [{t("adm.col.kind"): k, t("adm.col.credits2"): v} for k, v in kinds.items()],
            width='stretch', hide_index=True,
        ) if kinds else st.caption(t("adm.econ.no_tx"))
    with col_b:
        st.markdown(t("adm.econ.top_wallets"))
        top = stats.top_wallets(10)
        st.dataframe(
            [{t("adm.col.wallet"): f"{w['wallet'][:8]}…{w['wallet'][-4:]}",
              t("adm.col.debits"): w["debits"], t("adm.col.credits"): w["credits_spent"]} for w in top],
            width='stretch', hide_index=True,
        ) if top else st.caption(t("adm.econ.no_spend"))

    st.divider()
    st.markdown(t("adm.econ.float_title"))
    _FICON = {"ok": "🟢", "low": "🟡", "critical": "🔴", "unknown": "⚪"}
    floats = _cached_float()
    st.dataframe(
        [{t("adm.col.provider"): f["name"], t("adm.col.status"): _FICON.get(f["status"], "⚪"),
          t("adm.col.balance_usd"): f["balance_usd"] if f["balance_usd"] is not None else "—",
          t("adm.col.rec_min"): f["recommended_usd"] or "—",
          t("adm.col.note"): t(f["note_key"], **f.get("note_args", {}))}
         for f in floats],
        width='stretch', hide_index=True,
    )
    st.caption(t("adm.econ.float_caption"))

    _render_spend_import()


def _render_spend_import() -> None:
    """Імпорт фактичних API-витрат без CLI (ADM-D.2). UPSERT — повторний імпорт безпечний."""
    st.divider()
    with st.expander(t("adm.spend.expander")):
        st.caption(t("adm.spend.caption"))
        up = st.file_uploader(t("adm.spend.uploader"), type=["csv"], key="spend_csv")
        if up is not None:
            raw = up.getvalue()
            digest = hashlib.sha256(raw).hexdigest()
            # Імпортуємо лише коли файл змінився — щоб не гнати UPSERT на кожен rerun.
            if st.session_state.get("_spend_csv_hash") != digest:
                try:
                    saved, rows = provider_spend.import_csv_text(raw.decode("utf-8-sig", errors="replace"))
                    st.session_state["_spend_csv_hash"] = digest
                    if saved:
                        st.success(t("adm.spend.imported_ok", saved=saved, rows=len(rows)))
                    else:
                        st.warning(t("adm.spend.imported_none"))
                except Exception as exc:  # noqa: BLE001 — не валимо сторінку через поганий CSV
                    st.error(t("adm.spend.import_err", err=f"{type(exc).__name__}: {exc}"))
            else:
                st.caption(t("adm.spend.already"))

        if st.button(t("adm.spend.fetch_openai"), key="fetch_openai", width='stretch'):
            saved, rows, err = provider_spend.fetch_openai_costs(30)
            if err:
                st.error(t("adm.spend.openai_err", err=err))
            elif saved:
                st.success(t("adm.spend.openai_ok", saved=saved))
            else:
                st.info(t("adm.spend.openai_none"))

        last = provider_spend.list_imports(1)
        if last:
            li = last[0]
            st.caption(t(
                "adm.spend.last",
                provider=li["provider"], amount=li["amount_usd"],
                start=li["period_start"], end=li["period_end"], source=li["source"], at=li["imported_at"],
            ))
        else:
            st.caption(t("adm.spend.last_none"))


def _render_users(period_choice: str, days: int | None) -> None:
    """Воронка, пакети, останні оплати, sybil (ADM-B)."""
    st.markdown(t("adm.users.title", period=period_choice.lower()))
    fn = stats.funnel(days if days else 3650)
    f1, f2, f3, f4 = st.columns(4)
    f1.metric(t("adm.users.new_verified"), fn["new_verified"], help=t("adm.users.new_verified_help"))
    f2.metric(t("adm.users.paying"), fn["paying_wallets"], help=t("adm.users.paying_help"))
    f3.metric(
        t("adm.users.conv_pay"),
        f"{fn['conversion_verified_to_paying_pct']}%"
        if fn["conversion_verified_to_paying_pct"] is not None else "—",
        help=t("adm.users.conv_pay_help"),
    )
    f4.metric(t("adm.users.churn"), fn["churn_proxy_verified_no_debit"], help=t("adm.users.churn_help"))

    # Воронка білдера: чи доходять генератори до термінальної події (export-бандл).
    e1, e2, e3 = st.columns(3)
    e1.metric(t("adm.users.generators"), fn["first_debit_wallets"], help=t("adm.users.generators_help"))
    e2.metric(t("adm.users.exporters"), fn["exported_wallets"], help=t("adm.users.exporters_help"))
    e3.metric(
        t("adm.users.conv_export"),
        f"{fn['conversion_generate_to_export_pct']}%"
        if fn["conversion_generate_to_export_pct"] is not None else "—",
        help=t("adm.users.conv_export_help"),
    )

    s1, s2, s3 = st.columns(3)
    s1.metric(t("adm.users.savers"), fn["curator_save_wallets"], help=t("adm.users.savers_help"))
    s2.metric(
        t("adm.users.conv_save"),
        f"{fn['conversion_generate_to_save_pct']}%"
        if fn["conversion_generate_to_save_pct"] is not None else "—",
        help=t("adm.users.conv_save_help"),
    )
    s3.metric(
        t("adm.users.conv_save_export"),
        f"{fn['conversion_save_to_export_pct']}%"
        if fn["conversion_save_to_export_pct"] is not None else "—",
        help=t("adm.users.conv_save_export_help"),
    )

    qs = stats.quality_summary(days if days else 3650)
    st.markdown(t("adm.quality.title"))
    q1, q2, q3, q4 = st.columns(4)
    q1.metric(
        t("adm.quality.avg_rating"),
        f"{qs['avg_curator_rating']:.2f}" if qs["avg_curator_rating"] is not None else "—",
        help=t("adm.quality.avg_rating_help"),
    )
    q2.metric(t("adm.quality.items_saved"), qs["total_items_saved"], help=t("adm.quality.items_saved_help"))
    q3.metric(
        t("adm.quality.top_engine"),
        qs["top_engine_by_saves"] or "—",
        help=t("adm.quality.top_engine_help"),
    )
    q4.metric(t("adm.quality.save_events"), qs["save_events"], help=t("adm.quality.save_events_help"))
    q5, q6, q7 = st.columns(3)
    q5.metric(
        t("adm.quality.regen_rate"),
        f"{qs['regenerate_rate_pct']}%"
        if qs["regenerate_rate_pct"] is not None else "—",
        help=t("adm.quality.regen_rate_help"),
    )
    q6.metric(
        t("adm.quality.save_clean"),
        f"{qs['save_without_regen_pct']}%"
        if qs["save_without_regen_pct"] is not None else "—",
        help=t("adm.quality.save_clean_help"),
    )
    q7.metric(
        t("adm.quality.median_export"),
        f"{qs['median_export_minutes']:.0f} min"
        if qs["median_export_minutes"] is not None else "—",
        help=t("adm.quality.median_export_help"),
    )

    # §2.8 data-gate (E6/E7): Classic-частка (поріг E7 >15%) + Style Bible (поріг E6 >20%).
    src = qs.get("generate_source_images") or {}
    s1, s2, s3 = st.columns(3)
    s1.metric(
        t("adm.quality.classic_share"),
        f"{qs['classic_share_pct']}%" if qs.get("classic_share_pct") is not None else "—",
        help=t("adm.quality.classic_share_help"),
    )
    s2.metric(
        t("adm.quality.style_bible_share"),
        f"{qs['style_bible_share_pct']}%" if qs.get("style_bible_share_pct") is not None else "—",
        help=t("adm.quality.style_bible_share_help"),
    )
    s3.metric(
        t("adm.quality.gen_source_split"),
        f"{int(src.get('classic', 0))} / {int(src.get('pipeline', 0))}",
        help=t("adm.quality.gen_source_split_help"),
    )
    if int(src.get("untracked", 0)):
        st.caption(t("adm.quality.gen_untracked", n=int(src["untracked"])))

    window_days = days if days else 3650
    q_alert_items = alerts.quality_alert_items(qs, fn)
    if q_alert_items:
        for item in q_alert_items:
            st.warning(t(f"adm.quality.alert.{item['code']}", **item))
    elif qs["save_events"] or fn["curator_save_wallets"]:
        st.caption(t("adm.quality.alerts_ok", days=window_days))

    pcol, scol = st.columns(2)
    with pcol:
        st.markdown(t("adm.users.pkgs_title"))
        pkgs = stats.payments_by_package()
        st.dataframe(
            [{t("adm.col.package"): p["package_id"], "$": p["amount_usd"],
              t("adm.col.credits2"): p["credits"], t("adm.col.payments"): p["count"]} for p in pkgs],
            width='stretch', hide_index=True,
        ) if pkgs else st.caption(t("adm.users.no_pay"))
    with scol:
        st.markdown(t("adm.users.recent_title"))
        recent = stats.recent_payments(10)
        st.dataframe(
            [{t("adm.col.wallet"): f"{r['wallet'][:8]}…{r['wallet'][-4:]}", "$": r["amount_usd"],
              t("adm.col.credits2"): r["credits"], t("adm.col.when"): r["created_at"]} for r in recent],
            width='stretch', hide_index=True,
        ) if recent else st.caption(t("adm.users.no_pay"))

    sybil = stats.sybil_candidates(20, 20)
    if sybil:
        st.warning(t("adm.users.sybil_warn", n=len(sybil)))
        st.dataframe(
            [{t("adm.col.wallet"): f"{s['wallet'][:8]}…{s['wallet'][-4:]}",
              t("adm.col.debits"): s["debits"], t("adm.col.credits"): s["credits_spent"],
              t("adm.col.first_seen"): s["first_seen"]} for s in sybil],
            width='stretch', hide_index=True,
        )
    else:
        st.caption(t("adm.users.sybil_none"))


def _render_ops() -> None:
    """Операційний стан стека: health + env + секрети + час звіряння (ADM-C)."""
    ops_head, ops_refresh = st.columns([4, 1])
    ops_head.markdown(t("adm.ops.title"))
    if ops_refresh.button(t("adm.refresh"), width='stretch', key="ops_refresh"):
        _cached_readiness.clear()
    with st.spinner(t("adm.ops.checking")):
        rd = _cached_readiness()
    for it in rd["items"]:
        # ok: True → ✅, False → ❌, None (мережа/не перевірено) → ⚠️.
        icon = "✅" if it["ok"] is True else ("❌" if it["ok"] is False else "⚠️")
        detail = t(it["detail_key"], **it.get("detail_args", {}))
        st.markdown(f"{icon} **{it['name']}** — {detail}")
    lr = rd["last_reconcile"]
    st.caption(
        (t("adm.ops.reconcile", at=lr) if lr else t("adm.ops.reconcile_none"))
        + t("adm.ops.reconcile_suffix")
    )
    st.divider()
    st.markdown(t("adm.ops.workspace_title"))
    ws = workspace_limits.host_summary()
    w1, w2, w3 = st.columns(3)
    w1.metric(t("adm.ops.workspace_total_mb"), ws["total_mb"])
    w2.metric(t("adm.ops.workspace_wallets"), ws["wallet_count"])
    limits = []
    if workspace_limits.max_projects_limit() > 0:
        limits.append(t("adm.ops.workspace_lim_projects", n=workspace_limits.max_projects_limit()))
    if workspace_limits.max_mb_limit() > 0:
        limits.append(t("adm.ops.workspace_lim_mb", n=workspace_limits.max_mb_limit()))
    w3.metric(
        t("adm.ops.workspace_limits"),
        ", ".join(limits) if limits else t("adm.ops.workspace_unlimited"),
    )
    if ws["top_wallets"]:
        st.caption(t("adm.ops.workspace_top_caption"))
        st.dataframe(
            [{"wallet": r["slug"], "MB": r["mb"], "projects": r["projects"]} for r in ws["top_wallets"]],
            width='stretch',
            hide_index=True,
        )
    else:
        st.caption(t("adm.ops.workspace_empty"))

    st.divider()
    st.markdown(t("adm.ops.mint_path_title"))
    mp = mint_path.mint_path_intent_summary(days=7)
    m1, m2 = st.columns(2)
    m1.metric(t("adm.ops.mint_path_total"), mp["total"])
    m2.caption(t("adm.ops.mint_path_window", days=mp["days"]))
    if mp["by_kind"]:
        st.dataframe(
            [{"path_kind": k, "count": v} for k, v in sorted(mp["by_kind"].items(), key=lambda x: -x[1])],
            width='stretch',
            hide_index=True,
        )
    else:
        st.caption(t("adm.ops.mint_path_empty"))

    st.markdown(t("adm.ops.concierge_title"))
    reqs = mint_path.list_concierge_requests(limit=15)
    if reqs:
        st.dataframe(
            [
                {
                    "when": r["created_at"][:19] if r["created_at"] else "",
                    "wallet": (r["wallet"] or "")[:12],
                    "email": r["email"],
                    "chain": r["preferred_chain"],
                    "collection": r["collection"],
                    "supply": r["supply"] if r["supply"] is not None else "",
                }
                for r in reqs
            ],
            width='stretch',
            hide_index=True,
        )
    else:
        st.caption(t("adm.ops.concierge_empty"))


def _render_providers() -> None:
    """Валідність ключів провайдерів + блок Telegram-сповіщень."""
    head, refresh = st.columns([4, 1])
    head.markdown(t("adm.prov.title"))
    if refresh.button(t("adm.refresh"), width='stretch', key="providers_refresh"):
        _cached_health.clear()
    st.caption(t("adm.prov.caption"))
    with st.spinner(t("adm.prov.checking")):
        health = _cached_health()
    for h in health:
        if not h["configured"]:
            icon, status = "⚪", t("adm.prov.st_unconfigured")
        elif not h["checked"]:
            icon, status = "🔧", t("adm.prov.st_no_probe")   # Helio — навмисне не пробуємо
        elif h["valid"] is True:
            icon, status = "✅", t("adm.prov.st_valid")
        elif h["valid"] is False:
            icon, status = "❌", t("adm.prov.st_invalid")
        else:
            icon, status = "⚠️", t("adm.prov.st_unknown")
        bal = t("adm.prov.balance", bal=h["balance"]) if h.get("balance") is not None else ""
        st.markdown(f"{icon} **{h['name']}** — {status}{bal} · [{t('adm.prov.dashboard')}]({h['url']})")
        st.caption(t(h["purpose_key"]))

    # ── Сповіщення (Telegram) ──────────────────────────────────────────────────
    st.divider()
    st.markdown(t("adm.prov.tg_title"))
    if notify.telegram_configured():
        st.caption(t("adm.prov.tg_on", threshold=alerts.stability_threshold()))
        # Низький баланс — з уже отриманого (кешованого) значення Stability, без зайвого запиту.
        _stab = next((x for x in health if x["name"] == "Stability AI"), None)
        for msg in alerts.low_balance_messages(_stab["balance"] if _stab else None):
            st.warning(msg)
        bt1, bt2 = st.columns(2)
        if bt1.button(t("adm.prov.tg_test_btn"), width='stretch'):
            ok = notify.send_telegram(t("adm.prov.tg_test_msg"))
            st.success(t("adm.prov.tg_sent")) if ok else st.error(t("adm.prov.tg_fail"))
        if bt2.button(t("adm.prov.tg_digest_btn"), width='stretch'):
            ok = notify.send_telegram(alerts.digest_text())
            st.success(t("adm.prov.tg_digest_sent")) if ok else st.error(t("adm.prov.tg_fail"))
    else:
        st.caption(t("adm.prov.tg_off"))


def render() -> None:
    st.subheader(t("adm.title"))
    tab_ov, tab_econ, tab_users, tab_ops, tab_prov = st.tabs(
        [t("adm.tab.overview"), t("adm.tab.economics"), t("adm.tab.users"),
         t("adm.tab.ops"), t("adm.tab.providers")]
    )
    # Огляд рендериться першим і задає період — Економіка/Користувачі його читають
    # (усі st.tabs-блоки виконуються в одному run, тож значення доступне далі).
    with tab_ov:
        period_choice, days = _render_overview()
    with tab_econ:
        _render_economics(period_choice, days)
    with tab_users:
        _render_users(period_choice, days)
    with tab_ops:
        _render_ops()
    with tab_prov:
        _render_providers()
