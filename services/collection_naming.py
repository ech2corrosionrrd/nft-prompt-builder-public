"""Шаблони EN-назв і описів колекції для Export Center (CN-1)."""

from __future__ import annotations

import re

DEFAULT_HASHTAGS = ("#NFT", "#Web3", "#DigitalArt", "#Collectibles", "#w3ir")

_HASHTAG_RE = re.compile(r"#\w+")


def sanitize_brand(name: str) -> str:
    """Брендова назва колекції для token name (EN, без зайвих пробілів)."""
    cleaned = " ".join((name or "").strip().split())
    return cleaned or "Collection"


def token_name(brand: str, index: int) -> str:
    """Стандарт mint-ready: «Brand #12»."""
    return f"{sanitize_brand(brand)} #{index}"


def default_hashtags(brand: str) -> str:
    """3–5 hashtags одним рядком; бренд без # якщо короткий."""
    tags = list(DEFAULT_HASHTAGS)
    slug = re.sub(r"[^A-Za-z0-9]", "", sanitize_brand(brand))
    if slug and len(slug) >= 3:
        tags.insert(0, f"#{slug}")
    return " ".join(tags[:5])


def build_description(
    brand: str,
    supply: int,
    *,
    tagline: str = "",
    hashtags: str = "",
) -> str:
    """EN description template для всіх токенів колекції."""
    name = sanitize_brand(brand)
    n = max(1, int(supply or 1))
    lead = (tagline or "").strip()
    if not lead:
        lead = (
            f"{name} is a curated generative NFT collection of {n} unique pieces. "
            f"Each token includes on-chain-ready metadata with provenance."
        )
    tags = (hashtags or "").strip() or default_hashtags(name)
    if tags and not lead.endswith("\n"):
        return f"{lead}\n\n{tags}"
    return lead


def apply_naming(
    assets: list[dict],
    brand: str,
    description: str,
) -> list[dict]:
    """Копії активів з оновленими name/description (1-based індекс)."""
    desc = description.strip()
    out: list[dict] = []
    for i, item in enumerate(assets, start=1):
        row = dict(item)
        row["name"] = token_name(brand, i)
        if desc:
            row["description"] = desc
        out.append(row)
    return out


def parse_hashtags(text: str) -> list[str]:
    return _HASHTAG_RE.findall(text or "")
