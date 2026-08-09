"""Browser smoke: login.html на staging."""

from __future__ import annotations

import pytest

from tests.e2e.conftest import _is_cloudflare_access


@pytest.mark.e2e
def test_login_page_connect_button(e2e_base_url: str, browser_context_args: dict):
    # importorskip УСЕРЕДИНІ тесту — інакше --collect-only на CI без playwright
    # викидає модуль і ламає канон doc_metrics (1535 замість 1536).
    pytest.importorskip("playwright.sync_api", reason="pip install -r requirements-e2e.txt")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(**browser_context_args)
        page = context.new_page()
        try:
            page.goto(f"{e2e_base_url}/login", wait_until="domcontentloaded", timeout=30_000)
            if _is_cloudflare_access(page):
                pytest.skip("Cloudflare Access — потрібен service token або тестерський cookie")
            assert page.locator("#connect").is_visible()
            assert "Connect" in page.title()
            assert "?ticket=" not in page.url
        finally:
            context.close()
            browser.close()
