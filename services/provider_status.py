"""Стан зовнішніх провайдерів проєкту: валідність ключів, баланс і посилання.

Усі провайдери, що використовуються:
  OpenAI, Anthropic, Stability AI, Replicate (Flux.1), Pinata (IPFS), Helio (оплати),
  Base RPC і Solana RPC (Sybil-перевірки балансу).

Реальність балансу через ключ:
  - Stability — `GET /v1/user/balance` повертає кредити (єдиний прямий баланс);
  - решта — балансу через API-ключ немає, тож даємо посилання на кабінет, де
    адмін бачить баланс/витрати й ставить ліміти/алерти, + перевірку валідності ключа.

Мережеві проби проковтують помилки (fail-soft): valid=None — «не вдалося перевірити».
Helio навмисне НЕ пробуємо (це зачепило б платіжні дані) — лише наявність ключа + лінк.
"""

from __future__ import annotations

import os

import httpx

from services.wallet_auth import BASE_RPC_DEFAULT, SOLANA_RPC_DEFAULT

TIMEOUT = 15.0
STABILITY_BALANCE_URL = "https://api.stability.ai/v1/user/balance"

# Базовий реєстр: name, env-ключ, посилання на кабінет, чи дефолт робить його
# «налаштованим», purpose_key — i18n-ключ опису (текст у ui_strings; сервіс чистий).
PROVIDERS = [
    {"name": "OpenAI", "env": "OPENAI_API_KEY", "url": "https://platform.openai.com/usage",
     "purpose_key": "prov.purpose.openai"},
    {"name": "Anthropic", "env": "ANTHROPIC_API_KEY", "url": "https://console.anthropic.com/settings/billing",
     "purpose_key": "prov.purpose.anthropic"},
    {"name": "Stability AI", "env": "STABILITY_API_KEY", "url": "https://platform.stability.ai/account/credits",
     "purpose_key": "prov.purpose.stability"},
    {"name": "Replicate", "env": "REPLICATE_API_TOKEN", "url": "https://replicate.com/account/billing",
     "purpose_key": "prov.purpose.replicate"},
    {"name": "Pinata", "env": "PINATA_JWT", "url": "https://app.pinata.cloud",
     "purpose_key": "prov.purpose.pinata"},
    {"name": "Helio", "env": "HELIO_API_KEY", "url": "https://app.hel.io",
     "purpose_key": "prov.purpose.helio"},
    {"name": "Base RPC", "env": "BASE_RPC_URL", "url": "https://www.base.org", "default": True,
     "purpose_key": "prov.purpose.base_rpc"},
    {"name": "Solana RPC", "env": "SOLANA_RPC_URL", "url": "https://solana.com", "default": True,
     "purpose_key": "prov.purpose.solana_rpc"},
]


def provider_links() -> list[dict]:
    """Реєстр без мережі: name, configured, url, purpose_key. Для показу з посиланнями."""
    out = []
    for p in PROVIDERS:
        configured = bool((os.environ.get(p["env"]) or "").strip()) or p.get("default", False)
        out.append({"name": p["name"], "configured": configured, "url": p["url"],
                    "purpose_key": p["purpose_key"]})
    return out


def _http_ok(url: str, headers: dict) -> bool | None:
    try:
        return httpx.get(url, headers=headers, timeout=TIMEOUT).status_code == 200
    except Exception:
        return None


def _rpc_ok(url: str, method: str) -> bool | None:
    try:
        r = httpx.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": []},
                       timeout=TIMEOUT)
        return r.status_code == 200
    except Exception:
        return None


def stability_balance() -> float | None:
    """Баланс кредитів Stability AI (None — ключа нема або помилка)."""
    key = (os.environ.get("STABILITY_API_KEY") or "").strip()
    if not key:
        return None
    try:
        r = httpx.get(STABILITY_BALANCE_URL, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
        r.raise_for_status()
        return float(r.json().get("credits"))
    except Exception:
        return None


# Рекомендований мінімальний флоат на акаунті провайдера ($) — обіговий буфер під
# генерацію (оцінка з вартості зображень ai_service._ENGINE_COSTS; деталі —
# АДМІН_ДОВІДКА.md § 5.1 «Скільки тримати»). Pinata — free-tier на час бети.
FLOAT_RECOMMENDED_USD: dict[str, float] = {
    "OpenAI": 30.0,
    "Anthropic": 5.0,
    "Stability AI": 20.0,
    "Replicate": 10.0,
    "Pinata": 0.0,
}
STABILITY_USD_PER_CREDIT = 0.01  # ≈ $10 за 1000 кредитів Stability


def _stability_hard_alert_credits() -> float:
    """Жорсткий поріг алерту балансу Stability (env STABILITY_LOW_BALANCE, дефолт 100)."""
    try:
        return float(os.environ.get("STABILITY_LOW_BALANCE") or "100")
    except ValueError:
        return 100.0


def provider_float_status() -> list[dict]:
    """Рекомендований флоат vs наявний баланс по провайдерах-генераторах.

    Прямий баланс лише в Stability (інші postpaid → balance_usd=None, перевіряти в
    кабінеті). status: 'ok'|'low'|'critical'|'unknown'. Чиста логіка (UI/тести).
    """
    out: list[dict] = []
    for name, rec in FLOAT_RECOMMENDED_USD.items():
        balance_usd: float | None = None
        status = "unknown"
        # note_key+note_args локалізуються в UI (t); сервіс лишається чистим.
        note_key, note_args = "prov.note.postpaid", {}
        if name == "Stability AI":
            credits = stability_balance()
            if credits is None:
                note_key, note_args = "prov.note.unavailable", {}
            else:
                balance_usd = round(credits * STABILITY_USD_PER_CREDIT, 2)
                hard = _stability_hard_alert_credits()
                if credits < hard:
                    status = "critical"
                elif balance_usd < rec:
                    status = "low"
                else:
                    status = "ok"
                note_key, note_args = "prov.note.stability", {"credits": int(credits), "hard": int(hard)}
        elif name == "Pinata":
            status = "ok"
            note_key, note_args = "prov.note.free_tier", {}
        out.append({
            "name": name, "recommended_usd": rec,
            "balance_usd": balance_usd, "status": status, "note_key": note_key, "note_args": note_args,
        })
    return out


def key_health() -> list[dict]:
    """Повний стан кожного провайдера з живими пробами (викликати за кнопкою).

    Поля: name, configured, checked (чи робилася проба), valid (True/False/None),
    balance (float|None), url. Порядок — як у PROVIDERS.
    """
    links = {p["name"]: p for p in provider_links()}

    def base(name: str) -> dict:
        p = links[name]
        return {"name": name, "configured": p["configured"], "checked": False,
                "valid": None, "balance": None, "url": p["url"], "purpose_key": p["purpose_key"]}

    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    replicate_key = (os.environ.get("REPLICATE_API_TOKEN") or "").strip()
    pinata_jwt = (os.environ.get("PINATA_JWT") or "").strip()
    stability_key = (os.environ.get("STABILITY_API_KEY") or "").strip()
    base_rpc = (os.environ.get("BASE_RPC_URL") or BASE_RPC_DEFAULT).strip()
    solana_rpc = (os.environ.get("SOLANA_RPC_URL") or SOLANA_RPC_DEFAULT).strip()

    results = []
    for name in (p["name"] for p in PROVIDERS):
        e = base(name)
        if name == "OpenAI" and openai_key:
            e["checked"] = True
            e["valid"] = _http_ok("https://api.openai.com/v1/models", {"Authorization": f"Bearer {openai_key}"})
        elif name == "Anthropic" and anthropic_key:
            e["checked"] = True
            e["valid"] = _http_ok("https://api.anthropic.com/v1/models",
                                  {"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"})
        elif name == "Stability AI" and stability_key:
            e["checked"] = True
            e["balance"] = stability_balance()
            e["valid"] = e["balance"] is not None
        elif name == "Replicate" and replicate_key:
            e["checked"] = True
            e["valid"] = _http_ok("https://api.replicate.com/v1/account", {"Authorization": f"Token {replicate_key}"})
        elif name == "Pinata" and pinata_jwt:
            e["checked"] = True
            e["valid"] = _http_ok("https://api.pinata.cloud/data/testAuthentication", {"Authorization": f"Bearer {pinata_jwt}"})
        elif name == "Helio":
            pass  # навмисне не пробуємо — лише наявність ключа + лінк
        elif name == "Base RPC":
            e["checked"] = True
            e["valid"] = _rpc_ok(base_rpc, "eth_chainId")
        elif name == "Solana RPC":
            e["checked"] = True
            e["valid"] = _rpc_ok(solana_rpc, "getHealth")
        results.append(e)
    return results
