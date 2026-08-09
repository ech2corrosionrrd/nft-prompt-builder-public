"""Streamlit-компоненти: MetaMask та Phantom — connect + sign в один клік."""

from __future__ import annotations

import os
import shutil
import tempfile

import streamlit.components.v1 as components

_EVM_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_PHANTOM_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend_phantom")


def _ascii_frontend_dir(src_dir: str, cache_name: str) -> str:
    """Копія frontend у ASCII-only шлях (Windows + кириличний cwd ламає /component/…)."""
    cache_root = os.path.join(
        os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
        "w3ir-nft-builder",
        cache_name,
    )
    src_index = os.path.join(src_dir, "index.html")
    dst_index = os.path.join(cache_root, "index.html")
    if not os.path.isfile(dst_index) or os.path.getmtime(src_index) > os.path.getmtime(dst_index):
        os.makedirs(cache_root, exist_ok=True)
        shutil.copy2(src_index, dst_index)
    return cache_root


_wallet_auth = components.declare_component(
    "wallet_auth", path=_ascii_frontend_dir(_EVM_SRC, "wallet_auth"),
)
_phantom_auth = components.declare_component(
    "phantom_wallet_auth", path=_ascii_frontend_dir(_PHANTOM_SRC, "wallet_auth_phantom"),
)


def metamask_sign_in(nonce: str = "", key: str | None = None) -> dict | None:
    """Викликає MetaMask: eth_requestAccounts + personal_sign.

    Повертає ``{address, message, signature}`` або ``{error: "..."}``.
    """
    if not nonce:
        return None
    result = _wallet_auth(nonce=nonce, key=key, default=None)
    return result if isinstance(result, dict) else None


def phantom_sign_in(nonce: str = "", key: str | None = None) -> dict | None:
    """Викликає Phantom: connect + signMessage (Solana ed25519).

    Повертає ``{address, message, signature, chain}`` або ``{error: "..."}``.
    """
    if not nonce:
        return None
    result = _phantom_auth(nonce=nonce, key=key, default=None)
    return result if isinstance(result, dict) else None
