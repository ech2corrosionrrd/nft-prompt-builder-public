"""Streamlit-гард входу: перевіряє HMAC-сесію з SIWE-гейтвея перед застосунком.

Вмикається лише за AUTH_GATEWAY_ENFORCE=1 (дефолт — вимкнено, щоб не змінювати
поточний периметр на Cloudflare Access). Потік: login.html (FastAPI) видає
HttpOnly-кукі w3ir_session → редірект на застосунок без токена в URL.
Зворотна сумісність: ?ticket= лишається на один реліз (deprecated).
"""

from __future__ import annotations

import json
import os

import streamlit as st

from services import auth_gateway
from ui_strings import t

SESSION_WALLET = "gateway_wallet"
SESSION_COOKIE = "w3ir_session"
GATEWAY_URL = os.environ.get("AUTH_GATEWAY_URL") or "https://ai.w3ir.io/login"


def _enabled() -> bool:
    return os.environ.get("AUTH_GATEWAY_ENFORCE") == "1"


def parse_cookie_value(cookie_header: str, name: str) -> str | None:
    """Витягує значення кукі з заголовка Cookie (для тестів і runtime)."""
    prefix = f"{name}="
    for part in (cookie_header or "").split(";"):
        part = part.strip()
        if part.startswith(prefix):
            val = part[len(prefix) :]
            return val or None
    return None


def _read_session_token() -> str | None:
    # Токен НЕ приймаємо з URL (?ticket=): query-параметри течуть в історію браузера,
    # реферери й логи, тож посилання з ?ticket= = передана сесія. Лише HttpOnly-кукі.
    # Стале ?ticket= зі старих посилань прибирає _consume_session (нижче).
    # Сучасний API (Streamlit ≥1.42): st.context.cookies. Це штатний шлях —
    # старий streamlit.web.server.websocket_headers видалено у новіших релізах,
    # тож покладатися лише на нього не можна (кукі тоді не читається взагалі).
    try:
        cookies = getattr(st.context, "cookies", None)
        if cookies is not None:
            val = cookies.get(SESSION_COOKIE)
            if val:
                return val
    except Exception:
        pass
    # Фолбек для старих версій Streamlit (<1.42), де ще немає st.context.cookies.
    try:
        from streamlit.web.server.websocket_headers import _get_websocket_headers

        cookie_header = _get_websocket_headers().get("Cookie", "")
    except Exception:
        return None
    return parse_cookie_value(cookie_header, SESSION_COOKIE)


def _consume_session() -> None:
    if st.session_state.get(SESSION_WALLET):
        return
    token = _read_session_token()
    if not token:
        return
    try:
        address = auth_gateway.verify_session_token(token)
    except RuntimeError:  # AUTH_SESSION_SECRET не налаштовано — гейтвей мертвий
        address = None
    if address:
        st.session_state[SESSION_WALLET] = address
    # Прибрати ticket з URL, якщо залишився від старого потоку.
    try:
        del st.query_params["ticket"]
    except KeyError:
        pass


def enforce() -> None:
    """Гейтить рендер: пускає лише з валідною сесією. Викликати раз на старті.

    Без сесії — одразу веде на багатий екран входу (login.html), де новачок
    бачить що це за продукт і чому підпис безпечний. Голого проміжного екрана
    не показуємо: JS-редірект на вікно верхнього рівня (компонент в iframe),
    а видиме посилання-фолбек спрацьовує, якщо редірект заблоковано.
    """
    if not _enabled():
        return
    _consume_session()
    if st.session_state.get(SESSION_WALLET):
        return

    import streamlit.components.v1 as components

    components.html(
        f"<script>window.top.location.href = {json.dumps(GATEWAY_URL)};</script>",
        height=0,
    )
    # Перший екран для нового відвідувача — має слухатись мови UI, а не бути
    # захардкодженим українською (дефолт продукту — англійська, UI_DEFAULT_LANG).
    st.markdown(
        "<div style='max-width:420px;margin:10vh auto;text-align:center'>"
        f"<h2 style='font-weight:800'>{t('gateway.opening')}</h2>"
        f"<p style='color:#9ba1ae'>{t('gateway.fallback')}</p></div>",
        unsafe_allow_html=True,
    )
    st.link_button(t("gateway.connect"), GATEWAY_URL, width='stretch')
    st.stop()


def current_wallet() -> str | None:
    return st.session_state.get(SESSION_WALLET)


# Зворотна сумісність зі старим ім'ям приватної функції.
_consume_ticket = _consume_session
