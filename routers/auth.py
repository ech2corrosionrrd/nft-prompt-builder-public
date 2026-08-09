"""Роутер SIWE авторизації, генерації nonce та верифікації підписів."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

import api_server
from services import auth_gateway, wallet_auth

router = APIRouter(tags=["auth"])


class VerifyBody(BaseModel):
    address: str
    nonce: str
    signature: str


@router.get("/login")
def login_page() -> FileResponse:
    if not api_server._LOGIN_HTML.is_file():
        raise HTTPException(status_code=404, detail="login.html не знайдено")
    return FileResponse(api_server._LOGIN_HTML, media_type="text/html")


@router.get("/auth/nonce")
def auth_nonce(address: str, request: Request, chain_id: int | None = None) -> dict[str, str]:
    api_server._rate_limit(request, "auth_nonce", api_server._AUTH_NONCE_LIMIT)
    nonce = auth_gateway.new_nonce()
    if wallet_auth.is_evm_wallet(address):
        override = chain_id if (isinstance(chain_id, int) and 0 < chain_id <= 0xFFFFFFFFFFFFFFFF) else None
        message = auth_gateway.build_siwe_message(address, nonce, chain_id=override)
    elif wallet_auth.is_solana_wallet(address):
        message = wallet_auth.build_sign_message(address, nonce)
    else:
        raise HTTPException(status_code=400, detail="Очікується EVM-адреса 0x… або Solana-адреса")
    api_server._NONCE_STORE.issue(nonce, address, message)
    return {"nonce": nonce, "message": message}


@router.post("/auth/verify")
def auth_verify(body: VerifyBody, response: Response, request: Request) -> dict[str, str | bool]:
    api_server._rate_limit(request, "auth_verify", api_server._AUTH_VERIFY_LIMIT)
    is_evm = wallet_auth.is_evm_wallet(body.address)
    is_solana = wallet_auth.is_solana_wallet(body.address)
    if not (is_evm or is_solana):
        raise HTTPException(status_code=400, detail="Невалідна адреса (EVM 0x… або Solana)")
    entry = api_server._NONCE_STORE.consume(body.nonce)
    if not entry:
        raise HTTPException(status_code=401, detail="Nonce недійсний або протух — оновіть сторінку")
    stored_addr, message = entry
    if stored_addr != auth_gateway.normalize_addr(body.address):
        raise HTTPException(status_code=401, detail="Адреса не збігається з nonce")
    verified = (
        wallet_auth.verify_evm_signature(body.address, message, body.signature)
        if is_evm
        else wallet_auth.verify_solana_signature(body.address, message, body.signature)
    )
    if not verified:
        raise HTTPException(status_code=401, detail="Підпис не пройшов перевірку")

    token = auth_gateway.issue_session_token(body.address)
    response.set_cookie(
        api_server.SESSION_COOKIE, token,
        max_age=auth_gateway.SESSION_TTL_SECONDS,
        httponly=True, secure=True, samesite="lax", path="/",
    )
    return {"ok": True, "address": auth_gateway.normalize_addr(body.address)}
