"""Тести футера (legal URL)."""

from ui import footer


def test_legal_url_en_default(monkeypatch):
    # Дефолт — w3ir.io (FastAPI-origin, де /legal реально працює; на ai.w3ir.io
    # тунель /legal не роутить на FastAPI).
    monkeypatch.delenv("LEGAL_BASE_URL", raising=False)
    monkeypatch.setattr(footer, "ui_lang", lambda: "en")
    assert footer._legal_url() == "https://w3ir.io/legal/en"


def test_legal_url_uk_default(monkeypatch):
    monkeypatch.delenv("LEGAL_BASE_URL", raising=False)
    monkeypatch.setattr(footer, "ui_lang", lambda: "uk")
    assert footer._legal_url() == "https://w3ir.io/legal"


def test_legal_url_override(monkeypatch):
    # Оператор може перекрити базу (напр. якщо додасть /legal-правило в тунель ai.w3ir.io).
    monkeypatch.setenv("LEGAL_BASE_URL", "https://ai.w3ir.io")
    monkeypatch.setattr(footer, "ui_lang", lambda: "en")
    assert footer._legal_url() == "https://ai.w3ir.io/legal/en"
