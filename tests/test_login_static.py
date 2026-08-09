"""Статичні перевірки login.html — CI, без мережі."""

from __future__ import annotations

from pathlib import Path

LOGIN = Path(__file__).resolve().parents[1] / "ui" / "login.html"


def test_login_html_has_connect():
    html = LOGIN.read_text(encoding="utf-8")
    assert 'id="connect"' in html
    assert "Connect Wallet" in html


def test_login_html_english_default():
    html = LOGIN.read_text(encoding="utf-8")
    assert 'lang="en"' in html
    assert "Mint collections" in html
    assert "Мінти колекції" not in html


def test_login_html_no_ticket_in_redirect():
    html = LOGIN.read_text(encoding="utf-8")
    assert "?ticket=" not in html
