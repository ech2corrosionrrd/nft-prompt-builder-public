"""Фікстури E2E проти staging (ai.w3ir.io / pay.w3ir.io).

Запуск (локально, з Access-cookie або без CF Access на dev):
  set E2E_BASE_URL=https://ai.w3ir.io
  set E2E_PAY_URL=https://pay.w3ir.io
  pip install -r requirements-e2e.txt && playwright install chromium
  pytest tests/e2e -m e2e -v

У CI ці тести пропускаються без E2E_BASE_URL.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.e2e


def _url(name: str, default: str = "") -> str:
    return os.environ.get(name, default).rstrip("/")


@pytest.fixture(scope="session")
def e2e_base_url() -> str:
    url = _url("E2E_BASE_URL")
    if not url:
        pytest.skip("E2E_BASE_URL не задано — browser E2E пропущено")
    return url


@pytest.fixture(scope="session")
def e2e_pay_url(e2e_base_url: str) -> str:
    return _url("E2E_PAY_URL", f"{e2e_base_url.replace('://ai.', '://pay.')}")


@pytest.fixture(scope="session")
def browser_context_args():
    """Headless Chromium; viewport як десктоп."""
    return {"viewport": {"width": 1280, "height": 720}}


def _is_cloudflare_access(page) -> bool:
    url = (page.url or "").lower()
    title = (page.title() or "").lower()
    return "cloudflareaccess.com" in url or "cloudflare access" in title
