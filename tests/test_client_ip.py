"""Security #2: _client_ip для rate-limit стійкий до підробки X-Forwarded-For.

Без довіри до XFF зловмисник ротував би фейкові IP → свіжий бакет на кожен запит
→ обхід ліміту + CPU-DoS на /auth/verify. CF-Connecting-IP ставить сам Cloudflare.
"""

import types


def _req(headers=None, client_host=None):
    return types.SimpleNamespace(
        headers={k.lower(): v for k, v in (headers or {}).items()},
        client=types.SimpleNamespace(host=client_host) if client_host else None,
    )


def test_client_ip_prefers_cf_connecting_ip(monkeypatch):
    import api_server
    monkeypatch.setenv("RATE_LIMIT_TRUST_XFF", "1")
    r = _req({"CF-Connecting-IP": "9.9.9.9", "X-Forwarded-For": "1.2.3.4"}, client_host="10.0.0.1")
    assert api_server._client_ip(r) == "9.9.9.9"


def test_client_ip_ignores_spoofed_xff_by_default(monkeypatch):
    import api_server
    monkeypatch.delenv("RATE_LIMIT_TRUST_XFF", raising=False)
    # Без CF-IP і без дозволу на XFF — беремо реальний peer, а НЕ підроблений XFF.
    r = _req({"X-Forwarded-For": "1.2.3.4"}, client_host="10.0.0.1")
    assert api_server._client_ip(r) == "10.0.0.1"


def test_client_ip_trusts_xff_only_when_enabled(monkeypatch):
    import api_server
    monkeypatch.setenv("RATE_LIMIT_TRUST_XFF", "1")
    r = _req({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}, client_host="10.0.0.1")
    assert api_server._client_ip(r) == "1.2.3.4"


def test_client_ip_fallback_unknown(monkeypatch):
    import api_server
    monkeypatch.delenv("RATE_LIMIT_TRUST_XFF", raising=False)
    r = _req({}, client_host=None)
    assert api_server._client_ip(r) == "unknown"
