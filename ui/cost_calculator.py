"""Калькулятор вартості дропу: supply × двигун → кредити та пакет Helio."""

from __future__ import annotations

import streamlit as st

from services.ai_service import ENGINE_FLUX, ENGINE_GPT_IMAGE, ENGINE_STABILITY
from services.payment_service import PACKAGES, credit_cost, helio_paylink_url
from ui_strings import package_label, t

_ENGINE_LABELS = {
    ENGINE_FLUX: "Flux.1",
    ENGINE_STABILITY: "Stability AI",
    ENGINE_GPT_IMAGE: "GPT Image",
}

_SUPPLY_KEY = "cost_calc_supply"
_SUPPLY_PENDING = "_cost_calc_supply_pending"


def _apply_pending_supply() -> None:
    """Підставити відкладене значення supply ДО створення number_input.

    Streamlit забороняє міняти `key` віджета в тому ж run, тож кнопка
    «Узяти з черги» лише ставить pending, а застосування — на початку
    наступного run (патерн pending-key + `st.rerun()`).
    """
    pending = st.session_state.pop(_SUPPLY_PENDING, None)
    if pending is not None:
        st.session_state[_SUPPLY_KEY] = int(pending)


def _suggest_package(total_credits: int) -> tuple[str | None, float]:
    """Повертає (package_id, usd) — найменший пакет, що покриває потребу."""
    best_id: str | None = None
    best_usd = 0.0
    for pid, pkg in PACKAGES.items():
        if pkg["credits"] >= total_credits:
            if best_id is None or pkg["usd"] < best_usd:
                best_id = pid
                best_usd = float(pkg["usd"])
    if best_id:
        return best_id, best_usd
    pid = max(PACKAGES, key=lambda k: PACKAGES[k]["credits"])
    return pid, float(PACKAGES[pid]["usd"])


def render(*, expanded: bool = True, queue_size: int = 0) -> None:
    """Блок калькулятора для головної / конвеєра.

    `queue_size` — кількість промптів у черзі генерації; якщо вона є й
    відрізняється від поточного supply, показуємо кнопку синхронізації, щоб
    рахувати ціну саме під реальний дроп (а не дефолтні 100).
    """
    _apply_pending_supply()
    with st.expander(t("calc.title"), expanded=expanded):
        c1, c2 = st.columns(2)
        with c1:
            supply = st.number_input(
                t("calc.supply"), min_value=1, max_value=10_000, value=100, step=10, key=_SUPPLY_KEY,
            )
            if queue_size > 0 and int(supply) != int(queue_size):
                if st.button(t("calc.sync_queue", n=int(queue_size)), key="cost_calc_sync"):
                    st.session_state[_SUPPLY_PENDING] = int(queue_size)
                    st.rerun()
        with c2:
            engines = list(_ENGINE_LABELS.keys())
            # Міграція: старий вибір 'DALL-E 3' (модель вилучено) → дефолт.
            if st.session_state.get("cost_calc_engine") not in engines:
                st.session_state.pop("cost_calc_engine", None)
            engine = st.selectbox(
                t("calc.engine"),
                engines,
                format_func=lambda e: _ENGINE_LABELS.get(e, e),
                key="cost_calc_engine",
            )
        final = st.checkbox(t("calc.final"), key="cost_calc_final")
        per = credit_cost(engine, final)
        total = int(supply) * per
        pkg_id, usd = _suggest_package(total)
        pkg_label = package_label(pkg_id) if pkg_id else "—"

        m1, m2, m3 = st.columns(3)
        m1.metric(t("calc.credits_per"), per)
        m2.metric(t("calc.total_credits"), total)
        m3.metric(t("calc.usd_hint"), f"${usd:.2f}" if usd else "—")

        st.caption(f"{t('calc.package_hint')}: **{pkg_label}** ({PACKAGES[pkg_id]['credits']} credits)" if pkg_id else "")

        # Прямий шлях до оплати: hosted-paylink Helio рекомендованого пакета
        # (Streamlit не приймає крипто — лише посилання на зовнішню сторінку).
        pay_url = helio_paylink_url(pkg_id) if pkg_id else None
        if pay_url:
            st.link_button(t("calc.pay_cta", label=pkg_label), pay_url, width='stretch')
