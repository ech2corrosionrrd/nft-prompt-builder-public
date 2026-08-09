"""Роутер B2B API, Vault status та Launchpad Bundle inspector."""

from __future__ import annotations

import os

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

import api_server
from services import b2b_service, launchpad_service, vault_registry

router = APIRouter(tags=["b2b"])


@router.get("/api/vault/status")
async def get_vault_status(request: Request) -> dict:
    """Отримати статус сейфу: які індекси Дропу #2 вільні (є в сейфі), а які продані."""
    api_server._rate_limit(request, "vault_status", api_server._VAULT_STATUS_LIMIT)

    vault_address = (os.environ.get("VAULT_WALLET_ADDRESS") or "").strip()
    if not vault_address:
        raise HTTPException(status_code=500, detail="VAULT_WALLET_ADDRESS is not configured in environment")

    try:
        catalog = vault_registry.load_catalog(api_server._vault_catalog_path())
    except vault_registry.VaultError as e:
        api_server.logger.error("Vault status: каталог невалідний: %s", e)
        raise HTTPException(status_code=500, detail=f"vault catalog invalid: {e}")

    try:
        vault_mints = await vault_registry.vault_token_mints(
            vault_registry.rpc_url_from_env(), vault_address
        )
    except vault_registry.VaultError as e:
        api_server.logger.error("Vault status: RPC request failed: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

    available_indexes = []
    sold_indexes = []
    
    for item in catalog:
        idx = item.get("index")
        mint = item.get("mint")
        if mint in vault_mints:
            available_indexes.append(idx)
        else:
            sold_indexes.append(idx)
                
    return {
        "success": True,
        "vault_address": vault_address,
        "available_indexes": available_indexes,
        "sold_indexes": sold_indexes
    }


@router.post("/api/v1/launchpad/inspect-bundle")
async def launchpad_inspect_bundle(request: Request, file: UploadFile = File(...)) -> dict:
    """Інспектувати завантажений ZIP-бандл з білдера та повернути звіт про готовність."""
    key, _client = api_server._require_b2b_client(request)
    api_server._rate_limit(request, "launchpad_inspect", api_server._LAUNCHPAD_LIMIT)

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are supported")

    max_bytes = api_server._LAUNCHPAD_MAX_UPLOAD_MB * 1024 * 1024
    try:
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Bundle too large (limit {api_server._LAUNCHPAD_MAX_UPLOAD_MB} MB)",
            )
        res = launchpad_service.inspect_bundle_zip(content)
        if not res.get("valid"):
            raise HTTPException(status_code=400, detail=res.get("error", "Invalid bundle"))
    except HTTPException:
        raise
    except Exception as e:
        api_server.logger.error("Launchpad inspect bundle error: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to process bundle: {e}")

    b2b_service.record_b2b_usage(key, 1)
    return res


@router.get("/api/v1/b2b/status")
async def b2b_status(request: Request) -> dict:
    """Перевірка статусу B2B API-ключа та залишку квоти."""
    _key, client = api_server._require_b2b_client(request)
    return {
        "ok": True,
        "client_name": client.get("client_name"),
        "quota": client.get("quota"),
        "used": client.get("used"),
        "remaining": max(0, client.get("quota", 0) - client.get("used", 0))
    }
