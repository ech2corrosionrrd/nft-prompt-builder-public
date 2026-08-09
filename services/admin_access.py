"""Гейт адмін-доступу: гаманець зі списку ADMIN_WALLETS бачить адмін-панель.

Порівняння через auth_gateway.normalize_addr (EVM → нижній регістр, Solana як є),
щоб регістр EVM-адрес не впливав. Порожній ADMIN_WALLETS → адмінів немає.
"""

from __future__ import annotations

import os

from services.auth_gateway import normalize_addr


def admin_wallets() -> set[str]:
    raw = os.environ.get("ADMIN_WALLETS", "")
    return {normalize_addr(w) for w in raw.split(",") if w.strip()}


def is_admin(wallet: str | None) -> bool:
    """True, якщо гаманець у списку ADMIN_WALLETS."""
    if not wallet:
        return False
    return normalize_addr(wallet) in admin_wallets()
