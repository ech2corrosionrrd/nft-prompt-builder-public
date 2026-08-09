"""Роутер Gremlins Passport API (holder verification + avatar generation)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

import api_server
from services import gremlin_generate, holder_rewards

router = APIRouter(tags=["gremlin"])


class GremlinGenerateBody(BaseModel):
    """Тіло /gremlin/generate — дзеркалить контракт Passport (server/generator.ts)."""
    traits: dict = {}
    seed: int = 0


@router.get("/gremlin/holder")
async def gremlin_holder(
    request: Request, wallet: str, chain: str = "solana",
) -> dict:
    """Верифікація володіння Genesis NFT для Gremlin Passport."""
    api_server._require_gremlin_key(request)
    api_server._rate_limit(request, "gremlin_holder", api_server._GREMLIN_HOLDER_LIMIT)

    wallet = (wallet or "").strip()
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet is required")
    chain = (chain or "solana").strip().lower()
    if chain != "solana":
        return {"wallet": wallet, "chain": chain, "isGenesisHolder": False, "genesisCount": 0}
    count = await asyncio.to_thread(holder_rewards.wallet_genesis_count, wallet)
    return {
        "wallet": wallet,
        "chain": chain,
        "isGenesisHolder": count > 0,
        "genesisCount": count,
    }


@router.post("/gremlin/generate")
async def gremlin_generate_endpoint(body: GremlinGenerateBody, request: Request) -> Response:
    """Генерація Gremlin-аватара (Flux.1) для Gremlin Passport."""
    api_server._require_gremlin_key(request)
    api_server._rate_limit(request, "gremlin_generate", api_server._GREMLIN_GENERATE_LIMIT)

    try:
        traits = gremlin_generate.validate_traits(body.traits)
        seed = gremlin_generate.validate_seed(body.seed)
    except gremlin_generate.TraitError as e:
        raise HTTPException(status_code=400, detail=str(e))

    prompt = gremlin_generate.build_prompt(traits)
    sem = api_server._gremlin_semaphore()
    try:
        async with sem:
            png = await asyncio.to_thread(api_server._gremlin_generate_png, prompt, seed)
    except RuntimeError as e:
        api_server.logger.warning("gremlin_generate unavailable: %s", e)
        raise HTTPException(status_code=503, detail="generator unavailable")

    return Response(content=png, media_type="image/png")
