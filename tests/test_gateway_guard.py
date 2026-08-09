"""Тести gateway_guard — парсинг кукі сесії та читання токена."""

import types

from services import gateway_guard
from services.gateway_guard import SESSION_COOKIE, parse_cookie_value


def test_parse_cookie_value_found():
    raw = "foo=1; w3ir_session=abc.def; bar=2"
    assert parse_cookie_value(raw, "w3ir_session") == "abc.def"


def test_parse_cookie_value_missing():
    assert parse_cookie_value("other=1", "w3ir_session") is None
    assert parse_cookie_value("", "w3ir_session") is None


def _fake_st(*, cookies=None, ticket=None):
    """Мінімальний фейк streamlit для _read_session_token (без ScriptRunContext)."""
    return types.SimpleNamespace(
        query_params={"ticket": ticket} if ticket is not None else {},
        context=types.SimpleNamespace(cookies=cookies if cookies is not None else {}),
    )


def test_read_session_token_from_context_cookies(monkeypatch):
    # Основний шлях для Streamlit ≥1.42: токен береться зі st.context.cookies,
    # БЕЗ старого streamlit.web.server.websocket_headers (його видалено).
    monkeypatch.setattr(
        gateway_guard, "st", _fake_st(cookies={SESSION_COOKIE: "abc.def"})
    )
    assert gateway_guard._read_session_token() == "abc.def"


def test_read_session_token_ignores_ticket(monkeypatch):
    # Безпека: ?ticket= БІЛЬШЕ не приймається (токен у URL тече в історію/логи).
    # Кукі поряд із ticket → береться кукі; токен з URL ігнорується повністю.
    monkeypatch.setattr(
        gateway_guard,
        "st",
        _fake_st(cookies={SESSION_COOKIE: "cookie.tok"}, ticket="ticket.tok"),
    )
    assert gateway_guard._read_session_token() == "cookie.tok"


def test_read_session_token_ticket_alone_rejected(monkeypatch):
    # Лише ?ticket=, без кукі → None (URL-токен не дає доступу).
    monkeypatch.setattr(gateway_guard, "st", _fake_st(ticket="ticket.tok"))
    assert gateway_guard._read_session_token() is None


def test_read_session_token_absent(monkeypatch):
    # Немає ні ticket, ні кукі → None (фолбек на старий API теж нічого не дає).
    monkeypatch.setattr(gateway_guard, "st", _fake_st())
    assert gateway_guard._read_session_token() is None
