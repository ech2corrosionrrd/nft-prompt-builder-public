"""Білінг-панель конвеєра: Sign-In гаманця, баланс, тарифи, історія списань."""

import streamlit as st

from components.wallet_auth import metamask_sign_in, phantom_sign_in
from services import billing_guard, gateway_guard, holder_rewards, payment_service, wallet_auth
from services.payment_service import CREDIT_COSTS, PACKAGES, sim_payments_allowed
from ui_strings import package_label, package_note, t

WALLET_KEY = "wallet_address"
BILLING_USER_DISCONNECT_KEY = "_billing_user_disconnected"
SESSION_CREDITS_KEY = "session_credits_charged"
SIDEBAR_BALANCE_KEY = "_sidebar_balance"
SIDEBAR_BALANCE_SLOT_KEY = "_sidebar_balance_slot"
SIGN_MSG_KEY = "wallet_sign_message"
PENDING_NONCE_KEY = "wallet_pending_nonce"
PENDING_CHAIN_KEY = "wallet_pending_chain"
HANDLED_SIG_KEY = "wallet_handled_signature"


def connected_wallet() -> str:
    return st.session_state.get(WALLET_KEY, "")


def credits_billing_active() -> bool:
    """На проді (enforcement) користувач платить кредитами, не USD провайдера."""
    return billing_guard.enforcement_enabled()


def llm_credits(units: int) -> int:
    return billing_guard.CREDIT_COST_LLM * max(0, int(units))


def add_session_credits(cr: int) -> None:
    if cr <= 0:
        return
    prev = int(st.session_state.get(SESSION_CREDITS_KEY, 0) or 0)
    st.session_state[SESSION_CREDITS_KEY] = prev + cr


def sync_sidebar_balance(wallet: str | None) -> int | None:
    """Оновлює кеш балансу для sidebar (після списання в тому ж run — BUG-013)."""
    if not wallet:
        return None
    try:
        balance = payment_service.get_balance(wallet)
    except ValueError:
        return None
    st.session_state[SIDEBAR_BALANCE_KEY] = balance
    return balance


def _wallet_balance(wallet: str | None) -> int | None:
    if not wallet:
        return None
    try:
        return payment_service.get_balance(wallet)
    except ValueError:
        return None


def record_llm_usd_or_credits(wallet: str | None, units: int, usd_cost: float) -> None:
    """Сесійний облік: cr на ai.w3ir.io, USD лише у dev без enforcement."""
    if credits_billing_active():
        add_session_credits(llm_credits(units))
    elif usd_cost > 0:
        st.session_state.session_cost = float(st.session_state.get("session_cost", 0) or 0) + usd_cost


def show_llm_success(wallet: str | None, units: int, usd_cost: float = 0.0) -> None:
    """Success після classic LLM (конструктор, batch тощо)."""
    if credits_billing_active():
        cr = llm_credits(units)
        add_session_credits(cr)
        balance = _wallet_balance(wallet)
        if balance is not None:
            st.success(t("billing.done_credits", cr=cr, balance=balance))
        else:
            st.success(t("billing.done_credits_short", cr=cr))
    elif usd_cost > 0:
        st.session_state.session_cost = float(st.session_state.get("session_cost", 0) or 0) + usd_cost
        st.success(t("build.done_cost", cost=usd_cost))
    else:
        st.success(t("billing.done"))


def est_llm_metric_label() -> str:
    return t("batch.est_credits") if credits_billing_active() else t("batch.est_cost")


def est_llm_metric_value(count: int, usd: float) -> str:
    if credits_billing_active():
        return f"{llm_credits(count)} cr"
    return f"${usd:.4f}"


def prompt_cost_caption(model: str, count: int, usd: float) -> str:
    if credits_billing_active():
        return t("coll.prompt_credits", model=model, cr=llm_credits(count))
    return t("coll.prompt_cost", model=model, cost=usd)


def batch_results_credit_suffix(prompt_count: int) -> str:
    if not credits_billing_active():
        return ""
    return t("batch.actual_credits", cr=llm_credits(prompt_count), n=prompt_count)


def show_image_success(wallet: str | None, cr: int, msg_key: str, **kwargs) -> None:
    """Success після classic preview зображень (списання cr на платформі)."""
    if credits_billing_active():
        add_session_credits(cr)
        base = t(msg_key, **kwargs)
        balance = _wallet_balance(wallet)
        if balance is not None:
            st.success(f"{base} {t('billing.charged_suffix', cr=cr, balance=balance)}")
        else:
            st.success(f"{base} {t('billing.charged_suffix_short', cr=cr)}")
    else:
        st.success(t(msg_key, **kwargs))


def render_session_spend_sidebar(*, classic_mode: bool) -> None:
    """Лічильник витрат у sidebar: cr на проді, USD API-ключа у dev."""
    if not classic_mode:
        return
    if credits_billing_active():
        charged = int(st.session_state.get(SESSION_CREDITS_KEY, 0) or 0)
        if charged > 0:
            st.metric(t("sidebar.session_credits"), f"{charged} cr")
            st.caption(t("sidebar.session_credits_hint"))
            if st.button(t("sidebar.reset_cost"), width='stretch', key="sidebar_reset_session_credits"):
                st.session_state[SESSION_CREDITS_KEY] = 0
                st.rerun()
        return
    if float(st.session_state.get("session_cost", 0) or 0) > 0:
        st.metric(t("sidebar.session_cost"), f"${st.session_state.session_cost:.4f}")
        st.caption(t("sidebar.session_cost_hint"))
        if st.button(t("sidebar.reset_cost"), width='stretch'):
            st.session_state.session_cost = 0.0
            st.rerun()


def prompts_run_done_text(wallet: str | None, done: int, target: int) -> str:
    """Текст flash після завершення фази промптів у колекції."""
    text = t("coll.done_prompts", done=done, target=target)
    if not credits_billing_active():
        return text
    cr = llm_credits(done)
    balance = _wallet_balance(wallet)
    if balance is not None:
        return f"{text} {t('billing.charged_suffix', cr=cr, balance=balance)}"
    return f"{text} {t('billing.charged_suffix_short', cr=cr)}"


def show_batch_success(wallet: str | None, prompt_count: int, usd_cost: float) -> None:
    """Success після classic batch."""
    if credits_billing_active():
        cr = llm_credits(prompt_count)
        add_session_credits(cr)
        balance = _wallet_balance(wallet)
        if balance is not None:
            st.success(t("batch.ok_credits", n=prompt_count, cr=cr, balance=balance))
        else:
            st.success(t("batch.ok_credits_short", n=prompt_count, cr=cr))
    else:
        if usd_cost > 0:
            st.session_state.session_cost = float(st.session_state.get("session_cost", 0) or 0) + usd_cost
        st.success(t("batch.ok", n=prompt_count))


def wallet_is_verified() -> bool:
    """Чи доведено володіння підключеним гаманцем (підпис перевірено в БД)."""
    wallet = connected_wallet()
    if not wallet:
        return False
    try:
        return payment_service.is_wallet_verified(wallet)
    except ValueError:
        return False


def _render_wallet_identity(wallet: str, *, label_key: str, with_full_address: bool = False) -> None:
    """Скорочена адреса; повну — опційно в expander (Credits, без nested popover)."""
    st.markdown(t(label_key, short=wallet_auth.short_wallet(wallet)))
    if with_full_address:
        with st.expander(t("sidebar.copy_wallet"), expanded=False):
            st.code(wallet, language="text")


def render_sidebar_balance() -> None:
    """Постійний індикатор балансу кредитів у sidebar (коли гаманець підключено)."""
    wallet = connected_wallet()
    if not wallet:
        return
    try:
        balance = payment_service.get_balance(wallet)
    except ValueError:
        return
    st.divider()  # межа зони «Акаунт» (лише з гаманцем — без сирітських hr)
    _render_wallet_identity(wallet, label_key="sidebar.connected_wallet")
    st.session_state[SIDEBAR_BALANCE_KEY] = balance
    slot = st.empty()
    st.session_state[SIDEBAR_BALANCE_SLOT_KEY] = slot
    slot.metric(t("sidebar.credits"), balance)
    # Поповнення прямо тут: popover із пакетами (Helio paylink). Навігація до
    # вкладки «Конвеєр» неможлива програмно (st.tabs не перемикається), тож даємо
    # прямі посилання на купівлю — надійно з будь-якої вкладки.
    with st.popover(t("sidebar.topup"), width='stretch'):
        _render_topup_links()


def _render_topup_links() -> None:
    """Прямі посилання на пакети кредитів (hosted Helio paylink) для sidebar-поповнення."""
    st.markdown(t("bill.packages"))
    for package_id, p in PACKAGES.items():
        badge = " ⭐" if p["recommended"] else ""
        label = f"{package_label(package_id)}{badge} — ${p['usd']} · {p['credits']} cr"
        url = payment_service.helio_paylink_url(package_id)
        if url:
            st.link_button(label, url, width='stretch')
        else:
            st.caption(f"{label} — {t('bill.helio_missing')}")
    st.caption(t("sidebar.topup_full"))


def refresh_sidebar_balance_display() -> None:
    """Оновлює metric балансу після списань у вкладках (sidebar рендериться раніше — BUG-013)."""
    wallet = connected_wallet()
    if not wallet:
        return
    balance = sync_sidebar_balance(wallet)
    if balance is None:
        return
    slot = st.session_state.get(SIDEBAR_BALANCE_SLOT_KEY)
    if slot is not None:
        slot.metric(t("sidebar.credits"), balance)


def _connect_wallet(wallet: str, is_new: bool, welcome_msg: str = "") -> None:
    st.session_state.pop(BILLING_USER_DISCONNECT_KEY, None)
    st.session_state[WALLET_KEY] = wallet
    st.session_state.pop(SIGN_MSG_KEY, None)
    st.session_state.pop(PENDING_NONCE_KEY, None)
    st.session_state.pop(PENDING_CHAIN_KEY, None)
    if is_new:
        if welcome_msg:
            st.success(welcome_msg)
        elif payment_service.get_balance(wallet) > 0:
            st.success(t("bill.welcome_success", balance=payment_service.get_balance(wallet)))
        else:
            st.info(t("bill.registered_no_credits"))


def adopt_gateway_wallet() -> None:
    """Один вхід: гаманець, уже підтверджений SIWE-гейтвеєм при вході в застосунок,
    автоматично стає гаманцем білінгу — без повторного підпису на етапі Кредити.

    Володіння вже доведене серверним SIWE-verify гейтвея, тож другий підпис
    надлишковий. Ідемпотентно: якщо гаманець уже підключений або гейтвей вимкнено
    (current_wallet порожній), нічого не робить. Працює і для EVM, і для Solana —
    щойно гейтвей видасть сесію відповідній адресі.
    """
    if connected_wallet():
        return
    if st.session_state.get(BILLING_USER_DISCONNECT_KEY):
        return
    gw = gateway_guard.current_wallet()
    if not gw:
        return
    try:
        payment_service.complete_wallet_sign_in(gw)  # позначає verified, дає welcome
        wallet = payment_service.normalize_wallet(gw)
    except ValueError:
        return  # некоректна адреса з гейтвея — лишаємо ручний шлях
    # Тихо: без повідомлень угорі сторінки — баланс покаже сам етап Кредити.
    _connect_wallet(wallet, is_new=False)


def _after_sign_in(wallet: str, is_new: bool, balance: int) -> None:
    if is_new and balance == 0:
        _, sybil_msg = wallet_auth.welcome_balance_ok(wallet)
        _connect_wallet(wallet, True, sybil_msg or t("bill.connected_no_welcome"))
    else:
        _connect_wallet(wallet, is_new)


def _finish_evm_connect(wallet: str, message: str, signature: str) -> None:
    try:
        if not wallet_auth.verify_evm_signature(wallet, message, signature):
            st.error(t("bill.sig_mismatch"))
            return
    except RuntimeError as e:
        st.error(str(e))
        return
    stored = payment_service.consume_wallet_nonce(wallet)
    if stored is None or stored not in message:
        st.error(t("bill.nonce_expired"))
        return
    is_new, balance = payment_service.complete_wallet_sign_in(wallet)
    _after_sign_in(wallet, is_new, balance)


def _finish_solana_connect(wallet: str, message: str, signature: str) -> None:
    try:
        if not wallet_auth.verify_solana_signature(wallet, message, signature):
            st.error(t("bill.sig_mismatch"))
            return
    except RuntimeError as e:
        st.error(str(e))
        return
    stored = payment_service.consume_wallet_nonce(wallet)
    if stored is None or stored not in message:
        st.error(t("bill.nonce_expired"))
        return
    is_new, balance = payment_service.complete_wallet_sign_in(wallet)
    _after_sign_in(wallet, is_new, balance)


def _request_sign_nonce(chain: str) -> None:
    st.session_state[PENDING_NONCE_KEY] = wallet_auth.new_nonce()
    st.session_state[PENDING_CHAIN_KEY] = chain


def _render_metamask_oneclick() -> None:
    if st.button(t("bill.connect_metamask"), type="primary", width='stretch', key="bill_metamask_go"):
        _request_sign_nonce("evm")

    nonce = st.session_state.get(PENDING_NONCE_KEY, "")
    if nonce and st.session_state.get(PENDING_CHAIN_KEY) == "evm":
        result = metamask_sign_in(nonce=nonce, key="wallet_auth_component")
        if result:
            if result.get("error") == "NO_METAMASK":
                st.session_state.pop(PENDING_NONCE_KEY, None)
                st.session_state.pop(PENDING_CHAIN_KEY, None)
                st.warning(t("bill.no_metamask"))
            elif result.get("error"):
                st.session_state.pop(PENDING_NONCE_KEY, None)
                st.session_state.pop(PENDING_CHAIN_KEY, None)
                st.error(str(result["error"]))
            elif result.get("address") and result.get("signature"):
                sig = result["signature"]
                if st.session_state.get(HANDLED_SIG_KEY) != sig:
                    st.session_state[HANDLED_SIG_KEY] = sig
                    wallet = result["address"].lower()
                    payment_service.store_wallet_nonce(wallet, nonce)
                    _finish_evm_connect(wallet, result.get("message", ""), sig)


def _render_phantom_oneclick() -> None:
    if st.button(t("bill.connect_phantom"), width='stretch', key="bill_phantom_go"):
        _request_sign_nonce("solana")

    nonce = st.session_state.get(PENDING_NONCE_KEY, "")
    if nonce and st.session_state.get(PENDING_CHAIN_KEY) == "solana":
        result = phantom_sign_in(nonce=nonce, key="phantom_wallet_auth")
        if result:
            if result.get("error") == "NO_PHANTOM":
                st.session_state.pop(PENDING_NONCE_KEY, None)
                st.session_state.pop(PENDING_CHAIN_KEY, None)
                st.warning(t("bill.no_phantom"))
            elif result.get("error"):
                st.session_state.pop(PENDING_NONCE_KEY, None)
                st.session_state.pop(PENDING_CHAIN_KEY, None)
                st.error(str(result["error"]))
            elif result.get("address") and result.get("signature"):
                sig = result["signature"]
                if st.session_state.get(HANDLED_SIG_KEY) != sig:
                    st.session_state[HANDLED_SIG_KEY] = sig
                    wallet = result["address"]
                    payment_service.store_wallet_nonce(wallet, nonce)
                    _finish_solana_connect(wallet, result.get("message", ""), sig)


def _render_manual_connect() -> None:
    with st.expander(t("bill.manual_expand"), expanded=False):
        raw = st.text_input(
            t("bill.wallet_placeholder"),
            key="bill_wallet_input", placeholder="0x… або Solana base58",
        )
        if not raw.strip():
            return

        try:
            wallet = payment_service.normalize_wallet(raw)
        except ValueError as e:
            st.error(str(e))
            return

        if wallet_auth.is_evm_wallet(wallet):
            st.caption(t("bill.evm_caption"))
            if st.button(t("bill.get_message"), width='stretch', key="bill_get_nonce"):
                nonce = wallet_auth.new_nonce()
                payment_service.store_wallet_nonce(wallet, nonce)
                st.session_state[SIGN_MSG_KEY] = wallet_auth.build_sign_message(wallet, nonce)

            message = st.session_state.get(SIGN_MSG_KEY, "")
            if message and wallet.lower() in message.lower():
                st.text_area("Message", value=message, height=100, disabled=True, label_visibility="collapsed")
                signature = st.text_input(t("bill.paste_sig"), key="bill_signature", placeholder="0x…")
                if st.button(t("bill.verify"), type="primary", width='stretch', key="bill_verify"):
                    _finish_evm_connect(wallet, message, signature)
        else:
            st.caption(t("bill.solana_caption"))
            if st.button(t("bill.get_message"), width='stretch', key="bill_get_sol_nonce"):
                nonce = wallet_auth.new_nonce()
                payment_service.store_wallet_nonce(wallet, nonce)
                st.session_state[SIGN_MSG_KEY] = wallet_auth.build_sign_message(wallet, nonce)

            message = st.session_state.get(SIGN_MSG_KEY, "")
            if message and wallet in message:
                st.text_area("Message", value=message, height=100, disabled=True, label_visibility="collapsed")
                signature = st.text_input(t("bill.paste_sol_sig"), key="bill_sol_signature", placeholder="hex або base58")
                if st.button(t("bill.verify"), type="primary", width='stretch', key="bill_verify_sol"):
                    _finish_solana_connect(wallet, message, signature)


@st.fragment
def _render_wallet_connect() -> None:
    wallet = connected_wallet()
    if wallet:
        _render_wallet_identity(wallet, label_key="bill.connected_wallet", with_full_address=True)
        c1, c2 = st.columns([3, 1])
        with c1:
            st.metric(t("bill.balance"), f"{payment_service.get_balance(wallet)}")
        with c2:
            if st.button(t("bill.disconnect"), width='stretch', key="bill_disconnect"):
                st.session_state[WALLET_KEY] = ""
                st.session_state[BILLING_USER_DISCONNECT_KEY] = True
                st.session_state.pop(SIGN_MSG_KEY, None)
                st.session_state.pop(PENDING_NONCE_KEY, None)
                st.session_state.pop(PENDING_CHAIN_KEY, None)
                st.session_state.pop(HANDLED_SIG_KEY, None)
        if not wallet_is_verified():
            st.caption(t("bill.solana_unverified_note"))
        return

    _render_metamask_oneclick()
    _render_phantom_oneclick()
    st.caption(t("bill.component_fallback"))
    _render_manual_connect()


def _render_transaction_history(wallet: str) -> None:
    rows = payment_service.list_transactions(wallet)
    if not rows:
        return
    st.markdown(t("bill.history"))
    st.dataframe(rows, width='stretch', hide_index=True)


def _render_packages(wallet: str) -> None:
    st.markdown(t("bill.packages"))
    cols = st.columns(len(PACKAGES))
    for col, (package_id, p) in zip(cols, PACKAGES.items()):
        with col:
            badge = " ⭐" if p["recommended"] else ""
            per_credit = p["usd"] / p["credits"]
            st.markdown(
                f'<div class="template-card"><h4>{package_label(package_id)}{badge}</h4>'
                f'<p><b>&#36;{p["usd"]}</b> · {p["credits"]} credits<br>'
                f'≈ &#36;{per_credit:.3f} / credit<br>{package_note(package_id)}</p></div>',
                unsafe_allow_html=True,
            )
            url = payment_service.helio_paylink_url(package_id)
            if url:
                st.link_button(t("bill.buy"), url, width='stretch')
            else:
                st.caption(t("bill.helio_missing"))

    if payment_service.helio_keys():
        if st.button(t("bill.sync"), width='stretch', key="bill_sync"):
            try:
                with st.spinner("Polling Helio API…"):
                    new_tx, credited = payment_service.sync_helio_payments(wallet)
                if new_tx:
                    st.success(t("bill.payment_ok", credited=credited, new_tx=new_tx))
                else:
                    st.info(t("bill.no_payments"))
            except Exception as e:
                st.error(str(e))
    else:
        st.caption(t("bill.helio_env_hint"))

    if sim_payments_allowed():
        with st.expander(t("bill.test_topup")):
            package_id = st.selectbox(
                t("bill.package"),
                list(PACKAGES),
                format_func=lambda k: f"{package_label(k)} — ${PACKAGES[k]['usd']}",
                key="bill_sim_pkg",
            )
            if st.button(t("bill.simulate"), width='stretch', key="bill_sim_go"):
                balance = payment_service.simulate_payment(wallet, package_id)
                st.success(t("bill.balance_after", balance=balance))


def _render_costs_table() -> None:
    st.markdown(t("bill.costs"))
    st.dataframe(
        [{t("bill.col_engine"): e, t("bill.col_credits"): c} for e, c in CREDIT_COSTS.items()],
        width='stretch', hide_index=True,
    )


def _render_holder_bonus(wallet: str) -> None:
    """Genesis holder → bonus credits. Verifies on-chain ownership, one claim/period."""
    st.markdown(t("holder.title"))
    try:
        elig = holder_rewards.eligibility(wallet)
    except Exception:
        st.caption(t("holder.error"))
        return

    if not elig["is_solana"]:
        st.caption(t("holder.need_solana"))
        return
    if elig.get("excluded"):
        st.caption(t("holder.team_excluded"))
        return
    if not elig["holds"]:
        st.caption(t("holder.not_holder"))
        return
    if elig["already"]:
        st.success(t("holder.claimed", period=elig["period"]))
        return

    credits = elig["claimable_credits"]
    st.caption(t("holder.claimable", count=elig["count"], credits=credits))
    if st.button(t("holder.claim_btn", credits=credits), width='stretch', key="holder_claim"):
        try:
            res = holder_rewards.claim(wallet)
        except Exception:
            st.error(t("holder.error"))
            return
        if res.get("granted"):
            sync_sidebar_balance(wallet)
            st.success(t("holder.granted", credits=res["credits"], balance=res["balance"]))
            st.rerun()
        elif res.get("reason") == "budget_exhausted":
            st.warning(t("holder.budget"))
        elif res.get("reason") == "already":
            st.info(t("holder.claimed", period=res["period"]))
        elif res.get("reason") == "team_excluded":
            st.caption(t("holder.team_excluded"))
        else:
            st.caption(t("holder.not_holder"))


def render() -> None:
    st.markdown(t("bill.title"))
    _render_wallet_connect()
    wallet = connected_wallet()
    if not wallet:
        st.info(t("bill.connect_hint", welcome=payment_service.WELCOME_CREDITS))
        return
    st.divider()
    _render_holder_bonus(wallet)
    st.divider()
    _render_packages(wallet)
    st.divider()
    _render_transaction_history(wallet)
    st.divider()
    _render_costs_table()
