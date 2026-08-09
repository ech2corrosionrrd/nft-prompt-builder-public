"""HTTP smoke проти staging API (без браузера)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.e2e
def test_pay_health(e2e_pay_url: str):
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        r = client.get(f"{e2e_pay_url}/health")
    assert r.status_code == 200, r.text[:200]


@pytest.mark.e2e
def test_pay_subdomain_blocks_auth_nonce(e2e_pay_url: str):
    """pay.w3ir.io не повинен віддавати /auth/nonce (middleware restrict_pay_subdomain)."""
    addr = "0x0000000000000000000000000000000000000001"
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        r = client.get(f"{e2e_pay_url}/auth/nonce", params={"address": addr})
    assert r.status_code in (404, 403), f"очікували блок, отримали {r.status_code}"


@pytest.mark.e2e
def test_app_streamlit_health(e2e_base_url: str):
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        r = client.get(f"{e2e_base_url}/_stcore/health")
    # Access може дати 302/403 — тоді skip, не fail CI локально
    if r.status_code in (401, 403):
        pytest.skip(f"Streamlit health за Access: HTTP {r.status_code}")
    assert r.status_code == 200, r.text[:200]
