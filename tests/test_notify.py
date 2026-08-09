"""Тести спільного модуля сповіщень (Telegram) — без мережі."""

from services import notify


def test_not_configured_returns_false(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    calls = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: calls.append(1))

    assert notify.telegram_configured() is False
    assert notify.send_telegram("hi") is False
    assert calls == []  # без конфігу мережа не чіпається


def test_sends_when_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOK")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    calls = []
    monkeypatch.setattr(notify.httpx, "post", lambda url, **kw: calls.append((url, kw)))

    assert notify.telegram_configured() is True
    assert notify.send_telegram("привіт") is True
    assert "api.telegram.org/botTOK/sendMessage" in calls[0][0]
    assert calls[0][1]["json"] == {"chat_id": "42", "text": "привіт"}


def test_network_error_is_swallowed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOK")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(notify.httpx, "post", _boom)
    # Помилка мережі не має пробитися назовні — лише False.
    assert notify.send_telegram("x") is False
