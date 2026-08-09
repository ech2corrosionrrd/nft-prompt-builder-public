"""Rarity rank/tier і provenance-атрибути для on-chain метаданих NFT."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

TRAIT_RARITY_SCORE = "Rarity Score"
TRAIT_RARITY_RANK = "Rarity Rank"
TRAIT_RARITY_TIER = "Rarity Tier"
TRAIT_GENERATION_ENGINE = "Generation Engine"
TRAIT_GENERATED_AT = "Generated At"
TRAIT_PROMPT_HASH = "Prompt Hash"
TRAIT_COLLECTION_ID = "Collection ID"
TRAIT_MODEL_VERSION = "Model Version"
TRAIT_REVEAL_STATUS = "Reveal Status"
TRAIT_CURATOR_RATING = "Curator Rating"

TIERS = (
    (0.01, "Legendary"),
    (0.05, "Epic"),
    (0.15, "Rare"),
    (0.40, "Uncommon"),
)


def rarity_tier(rank: int, total: int) -> str:
    """Рівень рідкості за позицією в колекції (1 = найрідкісніший)."""
    if total <= 1:
        return "Unique"
    pct = rank / total
    for threshold, label in TIERS:
        if pct <= threshold:
            return label
    return "Common"


def prompt_hash(prompt: str) -> str:
    """Короткий SHA-256 хеш промпту для верифікації provenance."""
    text = (prompt or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def add_rarity_ranks(rows: list[dict]) -> None:
    """Додає rarity_rank, rarity_tier і rarity_total (1 = найрідкісніший за score)."""
    if not rows:
        return
    from batch import add_rarity_scores

    if not all(r.get("rarity_score") is not None for r in rows):
        add_rarity_scores(rows)
    total = len(rows)
    for row in rows:
        row["rarity_total"] = total
    order = sorted(range(total), key=lambda i: rows[i].get("rarity_score", 0), reverse=True)
    for rank, idx in enumerate(order, start=1):
        rows[idx]["rarity_rank"] = rank
        rows[idx]["rarity_tier"] = rarity_tier(rank, total)


def provenance_attributes(row: dict) -> list[dict[str, str]]:
    """Додаткові on-chain атрибути: rarity, двигун, дата, хеш промпту."""
    attrs: list[dict[str, str]] = []
    if row.get("rarity_score") is not None:
        attrs.append({"trait_type": TRAIT_RARITY_SCORE, "value": str(row["rarity_score"])})
    rank = row.get("rarity_rank")
    total = row.get("rarity_total")
    if rank is not None:
        rank_val = f"{rank} of {total}" if total else str(rank)
        attrs.append({"trait_type": TRAIT_RARITY_RANK, "value": rank_val})
    if tier := row.get("rarity_tier"):
        attrs.append({"trait_type": TRAIT_RARITY_TIER, "value": str(tier)})
    if engine := row.get("engine"):
        attrs.append({"trait_type": TRAIT_GENERATION_ENGINE, "value": str(engine)})
    if generated_at := row.get("generated_at"):
        attrs.append({"trait_type": TRAIT_GENERATED_AT, "value": str(generated_at)})
    if ph := row.get("prompt_hash"):
        attrs.append({"trait_type": TRAIT_PROMPT_HASH, "value": ph})
    elif prompt := row.get("prompt"):
        if h := prompt_hash(prompt):
            attrs.append({"trait_type": TRAIT_PROMPT_HASH, "value": h})
    if cid := row.get("collection_id"):
        attrs.append({"trait_type": TRAIT_COLLECTION_ID, "value": str(cid)})
    if mv := row.get("model_version"):
        attrs.append({"trait_type": TRAIT_MODEL_VERSION, "value": str(mv)})
    if rs := row.get("reveal_status"):
        attrs.append({"trait_type": TRAIT_REVEAL_STATUS, "value": str(rs)})
    if rating := row.get("curator_rating"):
        if int(rating) > 0:
            attrs.append({"trait_type": TRAIT_CURATOR_RATING, "value": str(rating)})
    return attrs
