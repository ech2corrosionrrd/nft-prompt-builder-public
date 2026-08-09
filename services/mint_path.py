"""Шлях CREATE→MINT для зовнішніх юзерів (R2): рекомендації + intent + concierge.

Чисті функції без Streamlit. Події воронки — fail-open через payment_service.
"""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Any

from services import payment_service
from services.notify import send_telegram

# Аудиторія → платформа Export Center + мітка для телеметрії.
PATH_OPTIONS: tuple[tuple[str, str, str], ...] = (
    ("evm_easy", "thirdweb", "evm_visual"),
    ("evm_opensea", "opensea", "evm_visual"),
    ("solana_dev", "sugar", "solana_cli"),
    ("concierge", "thirdweb", "concierge"),
)

PATH_IDS = frozenset(p[0] for p in PATH_OPTIONS)

# Платформа → рід шляху (для кліку по картці без path-chooser).
PLATFORM_PATH_KIND: dict[str, str] = {
    "thirdweb": "evm_visual",
    "opensea": "evm_visual",
    "generic": "generic",
    "metaplex": "solana_cli",
    "sugar": "solana_cli",
    "w3ir": "w3ir",
}

EVENT_MINT_PATH = "export_intent_mint_path"
EVENT_CONCIERGE = "concierge_request"


def resolve_path(path_id: str) -> tuple[str, str] | None:
    """Повертає (platform, path_kind) або None для невідомого path_id."""
    pid = (path_id or "").strip()
    for option_id, platform, kind in PATH_OPTIONS:
        if option_id == pid:
            return platform, kind
    return None


def path_kind_for_platform(platform: str) -> str:
    return PLATFORM_PATH_KIND.get((platform or "").strip(), "unknown")


def record_mint_path_intent(
    wallet: str,
    *,
    platform: str,
    path_kind: str | None = None,
    path_id: str | None = None,
    source: str = "platform_card",
) -> bool:
    """Подія вибору шляху/платформи мінту (для Solana vs EVM у адмінці)."""
    plat = (platform or "").strip()
    if not plat:
        return False
    kind = (path_kind or path_kind_for_platform(plat)).strip() or "unknown"
    payload: dict[str, Any] = {
        "platform": plat,
        "path_kind": kind,
        "source": (source or "platform_card").strip() or "platform_card",
    }
    if path_id:
        payload["path_id"] = path_id.strip()
    return payment_service.record_funnel_event(wallet, EVENT_MINT_PATH, payload)


def validate_concierge_request(
    *,
    email: str,
    preferred_chain: str = "solana",
    supply: int | None = None,
) -> str | None:
    """Повертає ключ помилки i18n або None якщо ок."""
    mail = (email or "").strip()
    if "@" not in mail or "." not in mail.split("@")[-1]:
        return "ec.concierge.err_email"
    chain = (preferred_chain or "").strip().lower()
    if chain not in ("solana", "base", "other"):
        return "ec.concierge.err_chain"
    if supply is not None and (supply < 1 or supply > 100_000):
        return "ec.concierge.err_supply"
    return None


def submit_concierge_request(
    wallet: str,
    *,
    email: str,
    collection_name: str = "",
    preferred_chain: str = "solana",
    supply: int | None = None,
    notes: str = "",
) -> tuple[bool, str | None]:
    """Зберігає заявку concierge + Telegram оператору.

    Повертає (ok, error_key). ok=False лише при валідації; збій БД/Telegram — fail-open
    (заявка може не зберегтись, але UX не падає з необробленим винятком).
    """
    err = validate_concierge_request(
        email=email, preferred_chain=preferred_chain, supply=supply,
    )
    if err:
        return False, err
    payload: dict[str, Any] = {
        "email": email.strip(),
        "collection": (collection_name or "").strip()[:120],
        "preferred_chain": preferred_chain.strip().lower(),
        "notes": (notes or "").strip()[:2000],
    }
    if supply is not None:
        payload["supply"] = int(supply)
    saved = payment_service.record_funnel_event(wallet, EVENT_CONCIERGE, payload)
    # Intent також — щоб path_kind=concierge потрапив у mint-path статистику.
    record_mint_path_intent(
        wallet,
        platform="concierge",
        path_kind="concierge",
        path_id="concierge",
        source="concierge_form",
    )
    short = (wallet or "")[:10] + ("…" if len(wallet or "") > 10 else "")
    send_telegram(
        "🛎️ Concierge mint request\n"
        f"Wallet: {short}\n"
        f"Email: {email.strip()}\n"
        f"Chain: {preferred_chain.strip().lower()}\n"
        f"Collection: {(collection_name or '—').strip() or '—'}\n"
        f"Supply: {supply if supply is not None else '—'}\n"
        f"Notes: {(notes or '—').strip()[:200] or '—'}\n"
        f"Saved: {'yes' if saved else 'no'}"
    )
    return True, None


def list_concierge_requests(*, limit: int = 20) -> list[dict[str, Any]]:
    """Останні заявки concierge для адмін-панелі (найновіші першими)."""
    lim = max(1, min(int(limit), 100))
    try:
        with closing(payment_service._connect()) as conn:
            rows = conn.execute(
                "SELECT wallet_address, created_at, payload FROM funnel_events "
                "WHERE event = ? ORDER BY rowid DESC LIMIT ?",
                (EVENT_CONCIERGE, lim),
            ).fetchall()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for wallet, created_at, payload_raw in rows:
        data: dict[str, Any] = {}
        if payload_raw:
            try:
                data = json.loads(payload_raw) or {}
            except (TypeError, ValueError, json.JSONDecodeError):
                data = {}
        out.append({
            "wallet": wallet,
            "created_at": created_at,
            "email": data.get("email") or "",
            "collection": data.get("collection") or "",
            "preferred_chain": data.get("preferred_chain") or "",
            "supply": data.get("supply"),
            "notes": data.get("notes") or "",
        })
    return out


def mint_path_intent_summary(*, days: int = 7) -> dict[str, Any]:
    """Агрегат export_intent_mint_path за вікно (path_kind + platform)."""
    d = max(1, min(int(days), 90))
    since = (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()
    by_kind: dict[str, int] = {}
    by_platform: dict[str, int] = {}
    total = 0
    try:
        with closing(payment_service._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM funnel_events "
                "WHERE event = ? AND created_at >= ?",
                (EVENT_MINT_PATH, since),
            ).fetchall()
    except Exception:
        return {"days": d, "total": 0, "by_kind": {}, "by_platform": {}}
    for (payload_raw,) in rows:
        total += 1
        data: dict[str, Any] = {}
        if payload_raw:
            try:
                data = json.loads(payload_raw) or {}
            except (TypeError, ValueError, json.JSONDecodeError):
                data = {}
        kind = str(data.get("path_kind") or "unknown")
        plat = str(data.get("platform") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_platform[plat] = by_platform.get(plat, 0) + 1
    return {"days": d, "total": total, "by_kind": by_kind, "by_platform": by_platform}
