"""Гейт білінгу для платних API-викликів у production.

У dev (APP_ENV != production) — пропускає без гаманця (операторські ключі).
У production — вимагає підтверджений гаманець + кредити + rate limit.
"""

from __future__ import annotations

import os

from services import freemium, payment_service

# 1 кредит ≈ один LLM-запит (batch/collection/build); vision дорожче.
CREDIT_COST_LLM = 1
CREDIT_COST_VISION = 2


def enforcement_enabled() -> bool:
    env = os.environ.get("APP_ENV", os.environ.get("ENVIRONMENT", "")).strip().lower()
    if env in ("production", "prod"):
        return True
    return os.environ.get("BILLING_ENFORCE_LLM", "0") == "1"


def try_reserve(
    wallet: str | None,
    cost: int,
    *,
    engine: str,
    note: str,
) -> tuple[bool, str | None]:
    """Резервує кредити. Повертає (ok, error_code).

    error_code: wallet | unverified | freemium | rate | credits
    """
    if cost <= 0 or not enforcement_enabled():
        return True, None
    if not wallet:
        return False, "wallet"
    try:
        wallet = payment_service.normalize_wallet(wallet)
    except ValueError:
        return False, "wallet"
    if not payment_service.is_wallet_verified(wallet):
        return False, "unverified"
    # B3: денна стеля лише для вітальних без топ-апу. Поповнені звільнені;
    allowed, _ = freemium.check_available(wallet)
    if not allowed:
        return False, "freemium"
    if not payment_service.check_generation_rate(wallet):
        return False, "rate"
    if payment_service.get_balance(wallet) < cost:
        return False, "credits"
    if not payment_service.deduct_credits(wallet, cost, engine=engine, note=note):
        return False, "credits"
    freemium.record_generation(wallet)
    return True, None


def refund(wallet: str | None, cost: int, *, engine: str, note: str) -> None:
    """Повертає зарезервовані кредити (після збою API) + звільняє freemium-слот."""
    if cost <= 0 or not wallet or not enforcement_enabled():
        return
    try:
        norm = payment_service.normalize_wallet(wallet)
    except ValueError:
        return
    payment_service.refund_credits(norm, cost, engine=engine, note=note)
    freemium.release_generation(norm)  # дзеркало record у try_reserve: невдача не палить слот
