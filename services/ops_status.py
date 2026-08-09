"""Операційний стан стека для адмін-панелі (ADM-C). Чисті функції, fail-soft.

Дзеркалить логіку `scripts/check_live.py` (health-ендпоінти + env-прапорці +
наявність секретів), але БЕЗ друку й побічних ефектів — придатне для рендеру в
`ui/admin_panel.py`. Мережеві проби проковтують помилки: `ok=None` означає
«не вдалося перевірити» (як valid=None у provider_status).

Не пробуємо webhook self-test із UI — це навантаження/шум у проді.
Маркер останнього звіряння Helio пише `payment_service.sync_helio_payments`
(єдина точка для cron-скрипта й фонового циклу api_server).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

TIMEOUT = 8.0
ROOT = Path(__file__).resolve().parent.parent
RECONCILE_MARKER = ROOT / "data" / "last_reconcile.txt"

# Тестовий HMAC-секрет зі smoke-скриптів — у проді категорично не можна.
TEST_SESSION_SECRET = "super-secret-hmac-key-for-testing-12345"
# Чексум-валідна EVM-адреса для безпечної проби /auth/nonce (nonce ефемерний).
PROBE_ADDR = "0x0000000000000000000000000000000000000001"


def _http_ok(url: str) -> bool | None:
    """GET → True (200) / False (інший код) / None (мережева помилка)."""
    try:
        return httpx.get(url, timeout=TIMEOUT).status_code == 200
    except Exception:
        return None


def _present(env: str) -> bool:
    return bool((os.environ.get(env) or "").strip())


def write_reconcile_marker(when: datetime | None = None) -> None:
    """Записати ISO-час успішного звіряння у data/last_reconcile.txt. Fail-soft."""
    try:
        RECONCILE_MARKER.parent.mkdir(parents=True, exist_ok=True)
        ts = (when or datetime.now(timezone.utc)).isoformat()
        RECONCILE_MARKER.write_text(ts, encoding="utf-8")
    except Exception:
        pass  # маркер — суто інформаційний, не валимо звіряння через диск


def last_reconcile() -> str | None:
    """ISO-час останнього звіряння або None (маркера ще немає / не читається)."""
    try:
        return RECONCILE_MARKER.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def health_items(app_url: str, pay_url: str) -> list[dict]:
    """Health-проби APP/API/SIWE. Кожен: {name, ok: bool|None, detail_key, detail_args}.

    Текст detail локалізується в UI через ui_strings.t(detail_key, **detail_args) —
    сервіс лишається чистим (без ui_lang/Streamlit), знає лише стан і дані (URL).
    """
    app_url, pay_url = app_url.rstrip("/"), pay_url.rstrip("/")
    enforced = (os.environ.get("AUTH_GATEWAY_ENFORCE") or "").strip() == "1"

    app_ok = _http_ok(f"{app_url}/_stcore/health")
    api_ok = _http_ok(f"{pay_url}/health")
    nonce_ok = _http_ok(f"{pay_url}/auth/nonce?address={PROBE_ADDR}")
    return [
        {"name": "Streamlit (APP)", "ok": app_ok,
         "detail_key": "ops.detail.url_only", "detail_args": {"url": f"{app_url}/_stcore/health"}},
        {"name": "API webhook", "ok": api_ok,
         "detail_key": "ops.detail.api", "detail_args": {"url": f"{pay_url}/health"}},
        {"name": "SIWE /auth/nonce", "ok": nonce_ok,
         "detail_key": "ops.detail.siwe_enforced" if enforced else "ops.detail.url_only",
         "detail_args": {"url": f"{pay_url}/auth/nonce"}},
    ]


def env_flags() -> list[dict]:
    """Прод-прапорці env (без значень секретів). {name, ok, detail_key, detail_args}."""
    app_env = (os.environ.get("APP_ENV") or "").strip().lower()
    enforce = (os.environ.get("AUTH_GATEWAY_ENFORCE") or "").strip()
    sim = (os.environ.get("ENABLE_SIM_PAYMENTS") or "").strip() == "1"
    secret = (os.environ.get("AUTH_SESSION_SECRET") or "").strip()

    if not enforce:
        enforce_detail = {"detail_key": "ops.detail.empty", "detail_args": {}}
    elif enforce.lower() == "true":
        enforce_detail = {"detail_key": "ops.detail.enforce_true", "detail_args": {"val": enforce}}
    else:
        enforce_detail = {"detail_key": "ops.detail.value", "detail_args": {"val": enforce}}

    items = [
        {"name": "APP_ENV", "ok": app_env in ("production", "prod"),
         "detail_key": "ops.detail.value" if app_env else "ops.detail.empty",
         "detail_args": {"val": app_env} if app_env else {}},
        {"name": "AUTH_GATEWAY_ENFORCE", "ok": enforce == "1", **enforce_detail},
        # ENABLE_SIM_PAYMENTS=1 у проді — небезпечно, тож ok = НЕ увімкнено.
        {"name": "ENABLE_SIM_PAYMENTS", "ok": not sim,
         "detail_key": "ops.detail.sim_off" if not sim else "ops.detail.sim_on", "detail_args": {}},
    ]
    if enforce == "1":
        # При увімкненому гарді секрет обов'язковий і не тестовий.
        if not secret:
            items.append({"name": "AUTH_SESSION_SECRET", "ok": False,
                          "detail_key": "ops.detail.secret_missing", "detail_args": {}})
        elif secret == TEST_SESSION_SECRET:
            items.append({"name": "AUTH_SESSION_SECRET", "ok": False,
                          "detail_key": "ops.detail.secret_test", "detail_args": {}})
        else:
            items.append({"name": "AUTH_SESSION_SECRET", "ok": True,
                          "detail_key": "ops.detail.set", "detail_args": {}})
    return items


def secret_flags() -> list[dict]:
    """Наявність ключових секретів (без значень). {name, ok, detail_key, detail_args}."""
    checks = [
        ("OPENAI_API_KEY", "ops.detail.sec_openai"),
        ("HELIO_WEBHOOK_SECRET", "ops.detail.sec_helio_webhook"),
        ("HELIO_API_KEY", "ops.detail.sec_helio_api"),
    ]
    return [{"name": k, "ok": _present(k), "detail_key": dk, "detail_args": {}} for k, dk in checks]


def readiness_summary(
    app_url: str = "http://127.0.0.1:8501",
    pay_url: str = "http://127.0.0.1:8000",
) -> dict:
    """Зведений операційний стан для адмін-панелі.

    Повертає {items: [{name, ok, detail_key, detail_args}], all_ok, last_reconcile}.
    `all_ok` True лише якщо жоден пункт не False (None — «не перевірено» — не валить).
    Текст detail рендериться в UI через t(detail_key, **detail_args).
    """
    items = health_items(app_url, pay_url) + env_flags() + secret_flags()
    all_ok = all(i["ok"] is not False for i in items)
    return {"items": items, "all_ok": all_ok, "last_reconcile": last_reconcile()}
