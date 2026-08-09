"""Тести правових сторінок: markdown→HTML рендер + маршрути /legal (UA/EN)."""

from services import legal_pages


# ── Чистий рендер markdown ────────────────────────────────────────────────────

def test_md_to_html_basics():
    html = legal_pages.md_to_html(
        "# Заголовок\n\n## Розділ\n\nТекст з **жирним** і `кодом`.\n\n- пункт\n\n> цитата\n\n---"
    )
    assert "<h1>Заголовок</h1>" in html
    assert "<h2>Розділ</h2>" in html
    assert "<strong>жирним</strong>" in html
    assert "<code>кодом</code>" in html
    assert "<ul><li>пункт</li></ul>" in html
    assert "<blockquote>цитата</blockquote>" in html
    assert "<hr/>" in html


def test_md_to_html_escapes_and_links():
    html = legal_pages.md_to_html("Подивіться [тут](https://w3ir.io) та <script>.")
    assert '<a href="https://w3ir.io"' in html
    assert ">тут</a>" in html
    assert "<script>" not in html  # екрановано
    assert "&lt;script&gt;" in html


def test_internal_md_links_rewritten_to_routes():
    # посилання між документами ведуть на маршрути, не на .md-файли
    assert '/legal/en' in legal_pages.md_to_html("[EN](LEGAL.md)")
    assert 'href="/legal"' in legal_pages.md_to_html("[UA](УМОВИ.md)")


def test_unsafe_link_schemes_stripped():
    # лише http(s)/mailto/внутрішні шляхи стають <a>; решта — простий текст
    out = legal_pages.md_to_html("Клік [тут](javascript:alert(1)) сюди")
    assert "javascript:" not in out
    assert "<a " not in out
    assert "тут" in out  # лейбл лишається текстом
    assert '<a href="mailto:w3ir@pm.me"' in legal_pages.md_to_html("[пошта](mailto:w3ir@pm.me)")


# ── render_legal_html (читає реальні файли репо) ──────────────────────────────

def test_render_uk_page():
    page = legal_pages.render_legal_html("uk")
    assert page and page.startswith("<!DOCTYPE html>")
    assert "Умови використання" in page
    assert "Політика конфіденційності" in page
    assert "/legal/en" in page  # перемикач мови


def test_render_en_page():
    page = legal_pages.render_legal_html("en")
    assert page and "Terms of Service" in page
    assert "Refund Policy" in page
    assert "/legal" in page


def test_unknown_lang_defaults_uk():
    assert "Умови використання" in legal_pages.render_legal_html("xx")


# ── Маршрути FastAPI ──────────────────────────────────────────────────────────

def test_legal_routes_served():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    r_uk = client.get("/legal")
    r_en = client.get("/legal/en")
    assert r_uk.status_code == 200 and "Умови використання" in r_uk.text
    assert r_en.status_code == 200 and "Terms of Service" in r_en.text
    assert "text/html" in r_uk.headers["content-type"]
