import hashlib
import hmac
import json

import pytest

from services.payment_service import process_helio_webhook_payload


def test_process_helio_webhook_unknown_paylink():
    credited, msg = process_helio_webhook_payload({"id": "tx1", "senderPublicKey": "0x" + "a" * 40})
    assert credited is False
    assert "Unknown paylink" in msg


def test_process_helio_webhook_credits_once(monkeypatch, tmp_path):
    monkeypatch.setenv("HELIO_PAYLINK_START", "plink-start")
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    wallet = "0x" + "b" * 40
    payload = {
        "id": "helio-tx-001",
        "paylinkId": "plink-start",
        "senderPublicKey": wallet,
        "status": "SUCCESS",
    }
    credited, msg = process_helio_webhook_payload(payload)
    assert credited is True
    assert "start" in msg

    credited2, _ = process_helio_webhook_payload(payload)
    assert credited2 is False


def test_api_health_endpoint():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_legal_endpoints():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    
    # Перевірка української версії правових документів
    r_uk = client.get("/legal")
    assert r_uk.status_code == 200
    assert "Умови використання" in r_uk.text
    assert "Політика конфіденційності" in r_uk.text
    assert "Політика повернення коштів" in r_uk.text
    
    # Перевірка англійської версії
    r_en = client.get("/legal/en")
    assert r_en.status_code == 200
    assert "Terms of Service" in r_en.text
    assert "Privacy Policy" in r_en.text
    assert "Refund Policy" in r_en.text


def test_pay_subdomain_blocks_auth_routes():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    addr = "0x" + "1" * 40
    r = client.get(f"/auth/nonce?address={addr}", headers={"host": "pay.w3ir.io"})
    assert r.status_code == 404
    r2 = client.get("/health", headers={"host": "pay.w3ir.io"})
    assert r2.status_code == 200


def test_ai_subdomain_allows_auth_routes():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    addr = "0x" + "2" * 40
    r = client.get(f"/auth/nonce?address={addr}", headers={"host": "ai.w3ir.io"})
    assert r.status_code == 200


def test_auth_nonce_evm_stamps_wallet_chain_id():
    """Клієнтський chain_id потрапляє у «Chain ID:» SIWE-повідомлення.

    Регресія: сервер завжди ставив AUTH_CHAIN_ID (8453/Base), і MetaMask на іншій
    мережі ховав екран підпису («chain ID does not match»). Тепер дзеркалимо
    активну мережу гаманця — підпис показується на будь-якій EVM-мережі.
    """
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    addr = "0x" + "3" * 40
    r = client.get(f"/auth/nonce?address={addr}&chain_id=1", headers={"host": "ai.w3ir.io"})
    assert r.status_code == 200
    assert "Chain ID: 1\n" in r.json()["message"]


def test_auth_nonce_evm_ignores_invalid_chain_id():
    """Невалідний/відсутній chain_id → дефолт із AUTH_CHAIN_ID, не падіння."""
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    addr = "0x" + "4" * 40
    # 0 — поза діапазоном (0 < id), має ігноруватися; запит все одно успішний
    r = client.get(f"/auth/nonce?address={addr}&chain_id=0", headers={"host": "ai.w3ir.io"})
    assert r.status_code == 200
    assert "Chain ID:" in r.json()["message"]


SOLANA_ADDR = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d"


def test_auth_nonce_accepts_solana_with_non_eip4361_message():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    r = client.get(f"/auth/nonce?address={SOLANA_ADDR}", headers={"host": "ai.w3ir.io"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["nonce"]) == 32
    # Solana — НЕ EIP-4361 («Ethereum account»), а chain-agnostic Sign-In
    assert "Ethereum account" not in body["message"]
    assert "NFT Prompt Builder — Sign-In" in body["message"]
    assert SOLANA_ADDR in body["message"]


def test_auth_nonce_rejects_garbage_address():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    r = client.get("/auth/nonce?address=not-a-wallet", headers={"host": "ai.w3ir.io"})
    assert r.status_code == 400


def test_auth_verify_solana_flow(monkeypatch):
    import api_server
    from fastapi.testclient import TestClient

    from services import wallet_auth

    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-secret-not-for-prod")
    # ed25519-підпис без реального ключа поза smoke — мокаємо як валідний.
    # Патчимо `services.wallet_auth` напряму, а не через `api_server.wallet_auth`:
    # після винесення роутерів у routers/ верифікацію викликає routers.auth, і
    # api_server більше не тримає цей реекспорт (ruff F401 його б і зняв).
    monkeypatch.setattr(wallet_auth, "verify_solana_signature", lambda a, m, s: True)

    client = TestClient(api_server.app)
    nonce = client.get(
        f"/auth/nonce?address={SOLANA_ADDR}", headers={"host": "ai.w3ir.io"}
    ).json()["nonce"]
    r = client.post(
        "/auth/verify",
        json={"address": SOLANA_ADDR, "nonce": nonce, "signature": "00" * 64},
        headers={"host": "ai.w3ir.io"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["address"] == SOLANA_ADDR  # base58 регістр збережено
    assert "w3ir_session" in r.headers.get("set-cookie", "")


def test_reconcile_loop_runs_then_sleeps(monkeypatch):
    """Фоновий цикл звіряє платежі одразу, потім засинає на інтервал."""
    import asyncio

    import api_server

    calls = []
    monkeypatch.setattr(api_server, "reconcile_payments_safe", lambda: (calls.append(1), (0, 0))[1])

    async def _stop(_seconds):
        raise asyncio.CancelledError  # обриваємо після першої ітерації

    monkeypatch.setattr(api_server.asyncio, "sleep", _stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(api_server._reconcile_loop())
    assert calls == [1]


def _webhook_client():
    from fastapi.testclient import TestClient
    from api_server import app

    return TestClient(app)


def test_webhook_rejected_without_secret_configured():
    # autouse-фікстура чистить HELIO_WEBHOOK_SECRET
    r = _webhook_client().post("/webhooks/helio", json={"id": "tx-x"})
    assert r.status_code == 503
    assert "HELIO_WEBHOOK_SECRET" in r.json()["detail"]


def test_webhook_accepts_valid_signature(monkeypatch, tmp_path):
    monkeypatch.setenv("HELIO_WEBHOOK_SECRET", "whsec-test")
    monkeypatch.setenv("HELIO_PAYLINK_START", "plink-start")
    monkeypatch.setattr("services.payment_service.DB_PATH", tmp_path / "users.db")
    body = json.dumps(
        {
            "id": "helio-tx-sig",
            "paylinkId": "plink-start",
            "senderPublicKey": "0x" + "c" * 40,
            "status": "SUCCESS",
        }
    ).encode()
    sig = hmac.new(b"whsec-test", body, hashlib.sha256).hexdigest()
    r = _webhook_client().post(
        "/webhooks/helio", content=body,
        headers={"x-helio-signature": sig, "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["credited"] is True


def test_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("HELIO_WEBHOOK_SECRET", "whsec-test")
    r = _webhook_client().post(
        "/webhooks/helio", json={"id": "tx-y"},
        headers={"x-helio-signature": "deadbeef"},
    )
    assert r.status_code == 401


# ── Маркетинговий лендінг (G1.1) ──────────────────────────────────────────────

def test_landing_served_at_root():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "NFT Prompt Builder" in body
    assert "https://ai.w3ir.io" in body  # CTA веде на застосунок


def test_landing_blocked_on_pay_subdomain():
    """Лендінг — НЕ на pay-субдомені (там лише webhook+health). Периметр недоторканий."""
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    r = client.get("/", headers={"host": "pay.w3ir.io"})
    assert r.status_code == 404


def test_landing_pricing_matches_packages():
    """Drift-guard: ціни/кредити на лендінгу збігаються з PACKAGES (статичний HTML)."""
    from pathlib import Path

    from services.payment_service import PACKAGES

    html = (Path(__file__).resolve().parent.parent / "ui" / "landing.html").read_text(encoding="utf-8")
    for p in PACKAGES.values():
        assert f"${p['usd']}" in html, f"ціна ${p['usd']} відсутня на лендінгу"
        assert f"{p['credits']} credits" in html, f"{p['credits']} credits відсутні на лендінгу"


def test_og_card_served():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    r = client.get("/og-card.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"  # валідний PNG-підпис


def test_sitemap_and_robots_served():
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    sm = client.get("/sitemap.xml")
    assert sm.status_code == 200
    assert "xml" in sm.headers["content-type"]
    assert "https://w3ir.io/" in sm.text

    rb = client.get("/robots.txt")
    assert rb.status_code == 200
    assert "Sitemap: https://w3ir.io/sitemap.xml" in rb.text


def test_landing_routes_have_stale_if_error_cache():
    """R3: лендінг+SEO-асети кешовні на краю зі `stale-if-error` — щоб рестарт
    Промта (тунель за CF) не ронив публічний w3ir.io. Webhook/health НЕ кешуються."""
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    for path in ("/", "/og-card.png", "/sitemap.xml", "/robots.txt", "/favicon.ico"):
        cc = client.get(path).headers.get("cache-control", "")
        assert "stale-if-error" in cc, f"{path}: немає stale-if-error ({cc!r})"
        assert "public" in cc, f"{path}: кеш не public ({cc!r})"
    # health не повинен мати публічного edge-кешу (динамічний readiness-сигнал)
    assert "stale-if-error" not in client.get("/health").headers.get("cache-control", "")


def test_login_page_has_og_tags():
    """login.html має OG-картку (G1.2), щоб шер ai.w3ir.io/login давав прев'ю."""
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "ui" / "login.html").read_text(encoding="utf-8")
    assert 'property="og:image"' in html
    assert "https://w3ir.io/og-card.png" in html


def test_api_docs_disabled():
    """Swagger/OpenAPI не світяться публічно (api_server віддає публічний лендінг)."""
    from fastapi.testclient import TestClient
    from api_server import app

    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_login_page_has_no_dead_links():
    """login.html не містить битих/застарілих посилань (нав-аудит 2026-06-18)."""
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "ui" / "login.html").read_text(encoding="utf-8")
    for dead in ("w3ir.io/beta", "w3ir.io/docs", "w3ir.io/status", '"https://discord.gg"'):
        assert dead not in html, f"битий лінк лишився: {dead}"


def test_favicon_route_served():
    """/favicon.ico віддає SVG-іконку — браузер авто-смикає її, без маршруту був 404."""
    from fastapi.testclient import TestClient
    from api_server import app

    resp = TestClient(app).get("/favicon.ico")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in resp.text


def test_landing_and_login_have_icon_link():
    """Обидві сторінки несуть <link rel="icon"> (інакше браузер шле зайвий /favicon.ico)."""
    from pathlib import Path

    ui = Path(__file__).resolve().parent.parent / "ui"
    for name in ("landing.html", "login.html"):
        html = (ui / name).read_text(encoding="utf-8")
        assert 'rel="icon"' in html, f"{name}: немає <link rel=icon>"


def test_landing_cta_carries_utm():
    """CTA «Launch app» лендінга несуть UTM — щоб міряти landing→app конверсію."""
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "ui" / "landing.html").read_text(encoding="utf-8")
    # усі переходи в застосунок розмічені джерелом; «голого» ai.w3.io без utm не лишилось
    assert html.count("utm_source=landing") >= 3, "не всі CTA лендінга розмічені UTM"
    assert 'href="https://ai.w3ir.io"' not in html, "лишився CTA без UTM"


def test_landing_forwards_ref_and_utm_to_app():
    """Лендінг пробрасывает ?ref= і вхідні utm_* у CTA до застосунку — інакше
    реферальна петля G3.3 рветься (`_capture_referral` читає query вже на
    ai.w3ir.io), а атрибуція каналів схлопується в utm_source=landing."""
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "ui" / "landing.html").read_text(encoding="utf-8")
    assert 'k === "ref"' in html, "скрипт не пробрасывает ?ref= у CTA"
    assert 'k.indexOf("utm_") === 0' in html, "скрипт не пробрасывает вхідні utm_*"
    assert 'a[href^="https://ai.w3ir.io"]' in html, "скрипт не цілить у CTA застосунку"


def test_landing_welcome_credits_copy_honest():
    """Анти-оверпроміс: welcome-кредити Sybil-гейтяться (мін. баланс на Base/Solana),
    тож копія лендінга мусить казати «up to N», не безумовне «get N free»."""
    from pathlib import Path

    from services.payment_service import WELCOME_CREDITS

    html = (Path(__file__).resolve().parent.parent / "ui" / "landing.html").read_text(encoding="utf-8")
    assert f"up to {WELCOME_CREDITS} welcome credits" in html
    assert f"up to {WELCOME_CREDITS} free credits" in html
    assert f"get {WELCOME_CREDITS} welcome credits free." not in html, "безумовна обіцянка welcome-кредитів"
