"""Роутер для обробки Webhook-повідомлень Helio."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, HTTPException, Request

import api_server
from services import payment_service, vault_registry, wallet_auth

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/helio")
async def helio_webhook(request: Request) -> dict[str, str | bool]:
    api_server._rate_limit(request, "helio_webhook", api_server._WEBHOOK_RATE_LIMIT)
    body = await request.body()
    sig = request.headers.get("x-helio-signature") or request.headers.get("x-signature")
    if not api_server._verify_helio_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], dict):
        payload = payload["data"]

    paylink_id = str(
        payload.get("paylinkId") or payload.get("paylink")
        or (payload.get("meta") or {}).get("paylinkId") or ""
    )
    
    mint_paylink_id = os.environ.get("HELIO_MINT_PAYLINK_ID")
    
    if mint_paylink_id and paylink_id == mint_paylink_id:
        customer_wallet = payload.get("meta", {}).get("customerWallet")
        if not customer_wallet:
            api_server.logger.error("Helio NFT transfer: відсутня адреса customerWallet у метаданих")
            return {"ok": False, "error": "missing customerWallet"}
        if not wallet_auth.is_solana_wallet(customer_wallet):
            api_server.logger.error("Helio NFT: некоректна Solana-адреса customerWallet: %r", customer_wallet)
            return {"ok": False, "error": "invalid customerWallet"}

        tx_id = str(
            payload.get("id") or payload.get("transactionId") or payload.get("transaction")
            or (payload.get("meta") or {}).get("id") or ""
        ).strip()
        if not tx_id:
            api_server.logger.error("Helio NFT: відсутній ідентифікатор транзакції — фулфілмент відхилено (ідемпотентність не гарантована)")
            return {"ok": False, "error": "missing transaction id"}

        selected_index = payload.get("meta", {}).get("selectedIndex")
        if selected_index is None:
            api_server.logger.error("Helio NFT: відсутній selectedIndex у метаданих для Дропу #2")
            return {"ok": False, "error": "missing selectedIndex"}

        try:
            idx = int(selected_index)
        except (TypeError, ValueError):
            api_server.logger.error("Helio NFT transfer: selectedIndex не є цілим числом: %r", selected_index)
            return {"ok": False, "error": "invalid selectedIndex parameter"}

        try:
            catalog = vault_registry.load_catalog(api_server._vault_catalog_path())
            mint_address = vault_registry.resolve_mint(catalog, idx)

            vault_address = (os.environ.get("VAULT_WALLET_ADDRESS") or "").strip()
            if not vault_address:
                raise vault_registry.VaultError("VAULT_WALLET_ADDRESS is not configured")
            vault_mints = await vault_registry.vault_token_mints(
                vault_registry.rpc_url_from_env(), vault_address
            )
            if mint_address not in vault_mints:
                raise vault_registry.VaultError(
                    f"mint {mint_address} (index {idx}) is not held by the vault"
                )
        except vault_registry.VaultError as e:
            api_server.logger.error("Helio NFT transfer ВІДХИЛЕНО (індекс %s): %s", selected_index, e)
            return {"ok": False, "error": "vault item unavailable"}

        try:
            if not payment_service.claim_nft_fulfillment(tx_id, customer_wallet, "transfer", mint_address):
                api_server.logger.info("Helio NFT transfer: транзакція %s уже оброблена — трансфер пропущено (ідемпотентність)", tx_id)
                return {"ok": True, "message": "already processed"}

            api_server.logger.info("Helio NFT transfer: запущено фоновий трансфер NFT %s для гаманця %s (індекс %d)", mint_address, customer_wallet, idx)
            asyncio.create_task(api_server._run_fulfillment(tx_id, customer_wallet, "transfer", mint_address))
            return {"ok": True, "message": f"Transfer task queued for index {idx}"}
        except Exception as e:
            api_server.logger.error("Helio NFT transfer: помилка постановки трансферу: %s", e)
            return {"ok": False, "error": "transfer could not be queued"}

    credited, message = payment_service.process_helio_webhook_payload(payload if isinstance(payload, dict) else {})
    api_server.logger.info("Helio webhook: credited=%s — %s", credited, message)
    return {"ok": True, "credited": credited, "message": message}
