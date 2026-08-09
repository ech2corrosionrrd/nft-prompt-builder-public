"""NFT Quality Checklist — SEO + Technical + Market Fit (рекомендації перед мінтом).

Детерміністична оцінка колекції + опційний LLM-шар (персональні поради).
Не блокує експорт — лише advisory для Export Center.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from services import export_bundle, image_qa

# ── Пороги (узгоджено з чек-листом w3ir) ────────────────────────────────────
IDEAL_RES_PX = 3000
GOOD_RES_PX = 2000
MIN_RES_PX = 1024
IDEAL_FILE_MB = 15
MAX_FILE_MB = 30
IDEAL_DESC_LEN = 150
GOOD_DESC_LEN = 100
MAX_DESC_LEN = 600
IDEAL_ROYALTY_BPS = 750
WARN_ROYALTY_BPS = 1000
LARGE_SUPPLY = 1000
MASS_SUPPLY = 10000
AUDIT_SUPPLY_THRESHOLD = 500

IDEAL_HASHTAGS = 3
MAX_HASHTAGS = 5
RARITY_SKEW_PCT = 50.0
MIN_NAME_LEN = 3
MAX_NAME_LEN = 60
METAPLEX_SYMBOL_MAX = 10
GENERIC_NAME_RE = re.compile(r"^Token #\d+$", re.IGNORECASE)
HASHTAG_RE = re.compile(r"#\w+", re.UNICODE)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

GENERIC_TRAIT_VALUES = frozenset({
    "blue", "red", "green", "black", "white", "gray", "grey", "brown",
    "background", "none", "normal", "common", "default",
})

CATEGORIES = ("visual", "metadata", "technical", "economics", "marketing", "legal")

CHECKLIST_KEYS = (
    "discord",
    "telegram",
    "twitter",
    "waitlist",
    "utility",
    "reveal_plan",
    "rights_attestation",
    "policy_review",
)
MARKETING_CHECKLIST_KEYS = CHECKLIST_KEYS[:6]
LEGAL_CHECKLIST_KEYS = CHECKLIST_KEYS[6:]

CATEGORY_WEIGHTS: dict[str, int] = {
    "visual": 25,
    "metadata": 25,
    "technical": 20,
    "economics": 15,
    "marketing": 10,
    "legal": 5,
}

AI_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "nft_quality_tips",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "tips": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "text": {"type": "string"},
                        },
                        "required": ["category", "text"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["tips"],
            "additionalProperties": False,
        },
    },
}

DEFAULT_AI_MODEL = "gpt-4o-mini"
DEFAULT_VISION_MODEL = "gpt-4o-mini"
CREDITS_AI_TIPS = 1
CREDITS_DEEP_DIVE = 5
VISION_SAMPLE_MAX = 5
STYLE_PAIR_MAX = 4

THUMBNAIL_VISION_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "thumbnail_readability",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "overall_score": {"type": "integer"},
                "readable_at_small_size": {"type": "boolean"},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "samples": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "token_index": {"type": "integer"},
                            "readable": {"type": "boolean"},
                            "note": {"type": "string"},
                        },
                        "required": ["token_index", "readable", "note"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["overall_score", "readable_at_small_size", "issues", "samples"],
            "additionalProperties": False,
        },
    },
}

STYLE_VISION_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "style_consistency",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "overall_score": {"type": "integer"},
                "consistent": {"type": "boolean"},
                "summary": {"type": "string"},
                "pairs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index_a": {"type": "integer"},
                            "index_b": {"type": "integer"},
                            "score": {"type": "integer"},
                            "note": {"type": "string"},
                        },
                        "required": ["index_a", "index_b", "score", "note"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["overall_score", "consistent", "summary", "pairs"],
            "additionalProperties": False,
        },
    },
}

ADVISOR_CHECKLIST_BRIEF = (
    "Abbreviated pre-mint checklist (skip items already marked pass in weak_checks):\n"
    "Visual: 2k+ resolution, file size, format, thumbnail readability at ~128px.\n"
    "Metadata: descriptions, hashtags, external URL, names, traits, rarity balance.\n"
    "Technical: metadata JSON, image fields, IPFS, platform, symbol.\n"
    "Economics: supply, royalty %, mint price, curation.\n"
    "Marketing: Discord/X, waitlist, utility, reveal plan, SEO keywords.\n"
    "Legal: content rights, platform policy.\n"
    "Platform: marketplace-specific steps (OpenSea/Blur EVM, ME/Tensor Solana).\n"
    "Give 3–6 actionable tips. Do not repeat deterministic pass items. "
    "Use ai_thumbnail and ai_style when provided."
)


@dataclass
class CheckItem:
    """Один пункт чек-листу. `code` → i18n `qc.item.{code}`."""

    category: str
    code: str
    severity: str  # pass | info | warn | fail
    points: int  # earned points (0..max for this item)
    max_points: int
    fmt: dict[str, Any] = field(default_factory=dict)


@dataclass
class QualityReport:
    score: int
    band: str  # ready | minor | major | risk
    items: list[CheckItem]
    category_scores: dict[str, int]
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class AiDeepDiveResult:
    thumbnail: dict[str, Any]
    style: dict[str, Any]
    tips: list[dict[str, str]]


def score_band(score: int) -> str:
    if score >= 90:
        return "ready"
    if score >= 75:
        return "minor"
    if score >= 60:
        return "major"
    return "risk"


def default_checklist() -> dict[str, bool]:
    return {key: False for key in CHECKLIST_KEYS}


def normalize_checklist(raw: dict | None) -> dict[str, bool]:
    base = default_checklist()
    if raw:
        for key in CHECKLIST_KEYS:
            base[key] = bool(raw.get(key))
    return base


def _image_bytes(item: dict) -> bytes | None:
    raw = item.get("image_bytes")
    if raw:
        return raw
    path = str(item.get("path") or "")
    if path:
        try:
            return Path(path).read_bytes()
        except OSError:
            return None
    return None


def _max_side(data: bytes) -> int:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        import struct
        w, h = struct.unpack(">II", data[16:24])
        return max(w, h)
    return 0


def _item(
    category: str,
    code: str,
    severity: str,
    earned: int,
    maximum: int,
    **fmt: Any,
) -> CheckItem:
    return CheckItem(category, code, severity, earned, maximum, fmt)


def _category_score(items: list[CheckItem], category: str) -> int:
    cat_items = [i for i in items if i.category == category]
    if not cat_items:
        return 0
    total_max = sum(i.max_points for i in cat_items)
    total_earned = sum(i.points for i in cat_items)
    weight = CATEGORY_WEIGHTS.get(category, 0)
    if total_max <= 0:
        return weight
    return round(weight * total_earned / total_max)


def analyze_collection(
    assets: list[dict],
    *,
    collection_name: str = "",
    platform: str = "generic",
    royalty_bps: int = 500,
    symbol: str = "",
    mint_price_sol: float | None = None,
    ipfs_pinned: bool = False,
    ipfs_result: dict | None = None,
    planned_count: int = 0,
    upscale_enabled: bool = False,
    upscale_available: bool = False,
    preflight_errors: list[tuple[str, int | None]] | None = None,
    preflight_warnings: list[tuple[str, int | None]] | None = None,
    checklist: dict[str, bool] | None = None,
) -> QualityReport:
    """Детерміністичний чек-лист. Повертає QualityReport (0–100)."""
    items: list[CheckItem] = []
    n = len(assets)
    preflight_errors = preflight_errors or []
    preflight_warnings = preflight_warnings or []
    solana_platform = platform in ("metaplex", "sugar")
    ipfs_result = ipfs_result or {}
    pinned = ipfs_pinned or bool(ipfs_result)
    image_base_uri = str(ipfs_result.get("image_base_uri") or "")
    checklist_state = normalize_checklist(checklist)

    if n == 0:
        items.append(_item("technical", "no_assets", "fail", 0, 10))
        return QualityReport(
            score=0,
            band="risk",
            items=items,
            category_scores={c: 0 for c in CATEGORIES},
            summary={"token_count": 0},
        )

    # ── 1. Visual (усі NFT) ─────────────────────────────────────────────────
    resolutions: list[int] = []
    sizes_mb: list[float] = []
    qa_bad = 0
    jpeg_count = 0
    webp_count = 0
    checked = 0
    for asset in assets:
        data = _image_bytes(asset)
        if not data:
            continue
        checked += 1
        side = _max_side(data)
        if side:
            resolutions.append(side)
        sizes_mb.append(len(data) / (1024 * 1024))
        qa = image_qa.analyze_image_bytes(data)
        if not qa.ok:
            qa_bad += 1
        if _is_webp(data):
            webp_count += 1
        elif data[:2] == b"\xff\xd8":
            jpeg_count += 1

    avg_res = round(sum(resolutions) / len(resolutions)) if resolutions else 0
    min_res = min(resolutions) if resolutions else 0
    max_mb = max(sizes_mb) if sizes_mb else 0

    if avg_res >= GOOD_RES_PX:
        items.append(_item("visual", "resolution_good", "pass", 8, 8, px=avg_res))
    elif avg_res >= MIN_RES_PX:
        items.append(_item("visual", "resolution_ok", "warn", 4, 8, px=avg_res, target=GOOD_RES_PX))
    elif avg_res > 0:
        items.append(_item("visual", "resolution_low", "warn", 2, 8, px=avg_res, target=GOOD_RES_PX))
    else:
        items.append(_item("visual", "resolution_unknown", "info", 5, 8))

    if min_res and min_res < MIN_RES_PX:
        items.append(_item("visual", "resolution_min_low", "warn", 2, 5, px=min_res))

    if upscale_available and avg_res < GOOD_RES_PX and not upscale_enabled:
        items.append(_item("visual", "upscale_hint", "info", 3, 3, px=avg_res, target=GOOD_RES_PX))
    elif upscale_enabled and avg_res < GOOD_RES_PX:
        items.append(_item("visual", "upscale_on", "pass", 3, 3))

    if max_mb <= IDEAL_FILE_MB:
        items.append(_item("visual", "filesize_good", "pass", 5, 5))
    elif max_mb <= MAX_FILE_MB:
        items.append(_item("visual", "filesize_high", "warn", 2, 5, mb=round(max_mb, 1)))
    else:
        items.append(_item("visual", "filesize_too_large", "fail", 0, 5, mb=round(max_mb, 1)))

    if qa_bad == 0:
        items.append(_item("visual", "qa_clean", "pass", 7, 7))
    else:
        items.append(_item("visual", "qa_issues", "warn", 2, 7, count=qa_bad, checked=checked))

    if webp_count > 0 and jpeg_count == 0 and webp_count == checked:
        items.append(_item("visual", "format_webp", "info", 4, 5, count=webp_count))
    elif webp_count > 0:
        items.append(_item("visual", "format_webp_mixed", "info", 3, 5, webp=webp_count, other=checked - webp_count))
    elif jpeg_count == 0:
        items.append(_item("visual", "format_png", "pass", 5, 5))
    else:
        items.append(_item("visual", "format_jpeg", "info", 3, 5, count=jpeg_count))

    # ── 2. Metadata ─────────────────────────────────────────────────────────
    desc_lens = [
        len(str(a.get("description") or a.get("prompt") or "").strip())
        for a in assets
    ]
    avg_desc = round(sum(desc_lens) / len(desc_lens)) if desc_lens else 0
    empty_desc = sum(1 for d in desc_lens if d < 20)

    if avg_desc >= IDEAL_DESC_LEN:
        items.append(_item("metadata", "description_good", "pass", 8, 8, chars=avg_desc))
    elif avg_desc >= GOOD_DESC_LEN:
        items.append(_item("metadata", "description_ok", "warn", 5, 8, chars=avg_desc, target=IDEAL_DESC_LEN))
    else:
        items.append(_item("metadata", "description_short", "warn", 2, 8, chars=avg_desc, target=GOOD_DESC_LEN))

    if empty_desc == 0:
        items.append(_item("metadata", "description_filled", "pass", 5, 5))
    else:
        items.append(_item("metadata", "description_empty", "warn", 1, 5, count=empty_desc))

    max_desc = max(desc_lens) if desc_lens else 0
    long_desc = sum(1 for d in desc_lens if d > MAX_DESC_LEN)
    if long_desc:
        items.append(_item(
            "metadata", "description_long", "warn", 0, 3,
            count=long_desc, max=MAX_DESC_LEN, chars=max_desc,
        ))
    else:
        items.append(_item("metadata", "description_length_ok", "pass", 3, 3, max=MAX_DESC_LEN))

    hashtag_counts = [_count_hashtags(str(a.get("description") or a.get("prompt") or "")) for a in assets]
    avg_tags = round(sum(hashtag_counts) / len(hashtag_counts), 1) if hashtag_counts else 0
    if avg_tags >= IDEAL_HASHTAGS:
        items.append(_item("metadata", "hashtags_good", "pass", 4, 4, count=avg_tags))
    elif avg_tags >= 1:
        items.append(_item("metadata", "hashtags_ok", "info", 3, 4, count=avg_tags, target=IDEAL_HASHTAGS))
    else:
        items.append(_item("metadata", "hashtags_missing", "warn", 1, 4, target=IDEAL_HASHTAGS))

    url_hits = _external_url_hits(assets, collection_name)
    if url_hits:
        items.append(_item("metadata", "external_url_ok", "pass", 4, 4, count=len(url_hits)))
    else:
        items.append(_item("metadata", "external_url_missing", "warn", 1, 4))

    short_names = sum(
        1 for a in assets
        if 0 < len(str(a.get("name") or "").strip()) < MIN_NAME_LEN
    )
    long_names = sum(1 for a in assets if len(str(a.get("name") or "")) > MAX_NAME_LEN)
    generic_names = sum(
        1 for a in assets if GENERIC_NAME_RE.match(str(a.get("name") or "").strip())
    )
    if short_names == 0 and long_names == 0:
        items.append(_item("metadata", "name_length_ok", "pass", 4, 4))
    else:
        if short_names:
            items.append(_item("metadata", "name_too_short", "warn", 1, 4, count=short_names, min=MIN_NAME_LEN))
        if long_names:
            items.append(_item("metadata", "name_too_long", "warn", 1, 4, count=long_names, max=MAX_NAME_LEN))
    if generic_names == n and n > 0:
        items.append(_item("metadata", "name_generic_template", "info", 2, 3))
    elif generic_names == 0:
        items.append(_item("metadata", "name_branded", "pass", 3, 3))
    else:
        items.append(_item("metadata", "name_mixed_template", "info", 2, 3, count=generic_names))

    has_traits = any(a.get("traits") for a in assets)
    if has_traits:
        items.append(_item("metadata", "traits_present", "pass", 5, 5))
        generic = _count_generic_traits(assets)
        if generic == 0:
            items.append(_item("metadata", "traits_specific", "pass", 5, 5))
        else:
            items.append(_item("metadata", "traits_generic", "info", 3, 5, count=generic))
    else:
        items.append(_item("metadata", "traits_missing", "warn", 1, 5))

    if collection_name.strip():
        items.append(_item("metadata", "collection_named", "pass", 3, 3, name=collection_name[:40]))
    else:
        items.append(_item("metadata", "collection_unnamed", "warn", 0, 3))

    dup_warn = sum(1 for c, _ in preflight_warnings if c == "duplicate_prompt")
    if dup_warn == 0:
        items.append(_item("metadata", "prompts_unique", "pass", 5, 5))
    else:
        items.append(_item("metadata", "prompts_duplicate", "warn", 2, 5, count=dup_warn))

    skewed = _rarity_skewed_traits(assets)
    if not skewed:
        items.append(_item("metadata", "rarity_balanced", "pass", 4, 4))
    else:
        top = skewed[0]
        items.append(_item(
            "metadata", "rarity_skewed", "warn", 1, 4,
            trait=top["trait"], trait_cat=top["category"], pct=top["pct"],
            extra=max(0, len(skewed) - 1),
        ))

    # ── 3. Technical ────────────────────────────────────────────────────────
    meta_audit = _validate_all_metadata(
        assets,
        collection_name=collection_name,
        platform=platform,
        symbol=symbol,
        royalty_bps=royalty_bps,
        image_base_uri=image_base_uri,
    )
    json_errors = meta_audit["json_errors"]
    image_mismatches = meta_audit["image_mismatches"]
    tokens_checked = meta_audit["tokens_checked"]

    if not json_errors:
        items.append(_item("technical", "json_all_valid", "pass", 8, 8, count=tokens_checked))
    else:
        sample = json_errors[0]
        items.append(_item(
            "technical", "json_errors", "fail", 0, 8,
            count=len(json_errors), total=tokens_checked,
            token=sample.get("token"), error=sample.get("error", "")[:80],
        ))

    if not image_mismatches:
        items.append(_item("technical", "image_field_ok", "pass", 5, 5, count=tokens_checked))
    else:
        sample = image_mismatches[0]
        items.append(_item(
            "technical", "image_field_mismatch", "warn", 1, 5,
            count=len(image_mismatches), token=sample.get("token"),
            expected=sample.get("expected", ""), got=sample.get("got", ""),
        ))

    if pinned and ipfs_result.get("metadata_cid"):
        items.append(_item(
            "technical", "ipfs_pinned", "pass", 5, 7,
            cid=str(ipfs_result.get("metadata_cid", ""))[:16],
        ))
        probe = _probe_ipfs_sample(assets, platform, ipfs_result)
        if probe["skipped"]:
            items.append(_item("technical", "ipfs_probe_skipped", "info", 2, 2))
        elif probe["ok"]:
            items.append(_item("technical", "ipfs_reachable", "pass", 2, 2))
        else:
            items.append(_item(
                "technical", "ipfs_probe_failed", "warn", 0, 2,
                detail=probe.get("detail", "")[:120],
            ))
    elif platform in ("metaplex", "sugar"):
        items.append(_item("technical", "ipfs_sugar_ok", "info", 6, 7))
    elif pinned:
        items.append(_item("technical", "ipfs_pinned", "pass", 7, 7, cid="—"))
    else:
        items.append(_item("technical", "ipfs_local_zip", "warn", 2, 7))

    if platform in ("metaplex", "sugar", "opensea", "thirdweb", "w3ir"):
        items.append(_item("technical", "platform_selected", "pass", 5, 5, platform=platform))
    else:
        items.append(_item("technical", "platform_generic", "info", 4, 5))

    items.extend(_platform_hint_items(platform, token_count=n, ipfs_pinned=pinned))

    err_count = len(preflight_errors)
    if err_count == 0:
        items.append(_item("technical", "preflight_clean", "pass", 5, 5))
    else:
        items.append(_item("technical", "preflight_errors", "warn", 0, 5, count=err_count))

    sym = symbol.strip()
    if solana_platform:
        if not sym:
            items.append(_item("technical", "symbol_missing", "warn", 0, 4))
        elif len(sym) > METAPLEX_SYMBOL_MAX:
            items.append(_item("technical", "symbol_too_long", "warn", 1, 4, chars=len(sym)))
        else:
            items.append(_item("technical", "symbol_ok", "pass", 4, 4, symbol=sym))

    # ── 4. Economics ────────────────────────────────────────────────────────
    if n <= LARGE_SUPPLY:
        items.append(_item("economics", "supply_ok", "pass", 6, 6, count=n))
    elif n <= MASS_SUPPLY:
        items.append(_item("economics", "supply_large", "warn", 3, 6, count=n))
    else:
        items.append(_item("economics", "supply_huge", "warn", 1, 6, count=n))

    if 500 <= royalty_bps <= IDEAL_ROYALTY_BPS:
        items.append(_item("economics", "royalty_ideal", "pass", 5, 5, pct=royalty_bps / 100))
    elif royalty_bps < 500:
        items.append(_item("economics", "royalty_low", "info", 4, 5, pct=royalty_bps / 100))
    elif royalty_bps <= WARN_ROYALTY_BPS:
        items.append(_item("economics", "royalty_ok", "pass", 4, 5, pct=royalty_bps / 100))
    else:
        items.append(_item("economics", "royalty_high", "warn", 1, 5, pct=royalty_bps / 100))

    if planned_count and n < planned_count:
        items.append(_item("economics", "drop_incomplete", "warn", 2, 4, approved=n, planned=planned_count))
    else:
        items.append(_item("economics", "drop_complete", "pass", 4, 4))

    # Curator ratings
    low_ratings = sum(1 for a in assets if int(a.get("curator_rating") or 0) < 3)
    if low_ratings == 0:
        items.append(_item("economics", "curation_strong", "pass", 5, 5))
    else:
        items.append(_item("economics", "curation_weak", "info", 3, 5, count=low_ratings))

    if platform == "sugar" and mint_price_sol is not None:
        if mint_price_sol <= 0:
            items.append(_item("economics", "mint_price_free", "info", 3, 4))
        elif mint_price_sol <= 1.0:
            items.append(_item("economics", "mint_price_set", "pass", 4, 4, price=mint_price_sol))
        else:
            items.append(_item("economics", "mint_price_high", "warn", 2, 4, price=mint_price_sol))

    if n > AUDIT_SUPPLY_THRESHOLD:
        items.append(_item("economics", "supply_audit_hint", "info", 3, 3, count=n))

    # ── 5–6. Marketing & Legal (інтерактивні чекбокси) ───────────────────────
    items.extend(_marketing_legal_items(checklist_state))

    summary = {
        "token_count": n,
        "images_checked": checked,
        "avg_resolution": avg_res,
        "avg_description_len": avg_desc,
        "avg_hashtags": avg_tags,
        "platform": platform,
        "royalty_bps": royalty_bps,
        "symbol": symbol.strip(),
        "mint_price_sol": mint_price_sol,
        "ipfs_pinned": pinned,
        "webp_count": webp_count,
        "metadata_json_errors": len(json_errors),
        "metadata_image_mismatches": len(image_mismatches),
        "metadata_tokens_checked": tokens_checked,
        "checklist": checklist_state,
    }
    if pinned and ipfs_result:
        summary["ipfs_metadata_cid"] = ipfs_result.get("metadata_cid", "")
        summary["ipfs_images_cid"] = ipfs_result.get("images_cid", "")
    return _finalize(items, summary)


def _finalize(items: list[CheckItem], summary: dict[str, Any]) -> QualityReport:
    cat_scores = {cat: _category_score(items, cat) for cat in CATEGORIES}
    total_weight = sum(CATEGORY_WEIGHTS.values())
    score = round(sum(cat_scores.values()) / total_weight * 100) if total_weight else 0
    score = max(0, min(100, score))
    return QualityReport(
        score=score,
        band=score_band(score),
        items=items,
        category_scores=cat_scores,
        summary=summary,
    )


def _platform_hint_items(
    platform: str,
    *,
    token_count: int,
    ipfs_pinned: bool,
) -> list[CheckItem]:
    """Marketplace-specific advisory hints (OpenSea, ME, Blur, Tensor, …)."""
    _ = token_count
    items: list[CheckItem] = []
    if platform == "opensea":
        items.append(_item("technical", "platform_hint_opensea", "info", 4, 4))
        items.append(_item("technical", "platform_hint_blur", "info", 3, 3))
        if not ipfs_pinned:
            items.append(_item("technical", "platform_hint_opensea_ipfs", "warn", 1, 2))
    elif platform == "thirdweb":
        items.append(_item("technical", "platform_hint_thirdweb", "info", 4, 4))
        items.append(_item("technical", "platform_hint_blur", "info", 3, 3))
    elif platform == "metaplex":
        items.append(_item("technical", "platform_hint_magic_eden", "info", 4, 4))
        items.append(_item("technical", "platform_hint_tensor", "info", 3, 3))
    elif platform == "sugar":
        items.append(_item("technical", "platform_hint_sugar_me", "info", 4, 4))
        items.append(_item("technical", "platform_hint_tensor", "info", 3, 3))
    elif platform == "w3ir":
        items.append(_item("technical", "platform_hint_w3ir", "info", 4, 4))
    else:
        items.append(_item("technical", "platform_hint_generic", "info", 3, 3))
    return items


def _marketing_legal_items(checklist: dict[str, bool]) -> list[CheckItem]:
    """Оцінка marketing/legal за self-reported чекбоксами (не блокує експорт)."""
    items: list[CheckItem] = []
    for key, code_ok, code_miss, maximum in (
        ("discord", "social_discord_ok", "social_discord_missing", 2),
        ("telegram", "social_telegram_ok", "social_telegram_missing", 2),
        ("twitter", "social_twitter_ok", "social_twitter_missing", 2),
        ("waitlist", "social_waitlist_ok", "social_waitlist_missing", 2),
        ("utility", "utility_done", "utility_missing", 2),
        ("reveal_plan", "reveal_done", "reveal_missing", 2),
    ):
        if checklist.get(key):
            items.append(_item("marketing", code_ok, "pass", maximum, maximum))
        else:
            items.append(_item("marketing", code_miss, "warn", 0, maximum))
    items.append(_item("marketing", "seo_keywords", "info", 5, 5))
    if checklist.get("rights_attestation"):
        items.append(_item("legal", "rights_attested", "pass", 5, 5))
    else:
        items.append(_item("legal", "rights_unattested", "warn", 0, 5))
    if checklist.get("policy_review"):
        items.append(_item("legal", "policy_reviewed", "pass", 5, 5))
    else:
        items.append(_item("legal", "policy_unreviewed", "info", 2, 5))
    return items


def _count_generic_traits(assets: list[dict]) -> int:
    count = 0
    for asset in assets:
        for val in (asset.get("traits") or {}).values():
            if str(val).strip().lower() in GENERIC_TRAIT_VALUES:
                count += 1
    return count


def _count_hashtags(text: str) -> int:
    return len(HASHTAG_RE.findall(text))


def _external_url_hits(assets: list[dict], collection_name: str) -> list[str]:
    found: list[str] = []
    for asset in assets:
        for fld in ("description", "prompt"):
            for url in URL_RE.findall(str(asset.get(fld) or "")):
                if url not in found:
                    found.append(url)
    return found


def _rarity_skewed_traits(assets: list[dict]) -> list[dict]:
    from services import rarity_report

    return rarity_report.skewed_traits(assets, threshold_pct=RARITY_SKEW_PCT)


def _is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _metadata_platform(platform: str) -> str:
    if platform in export_bundle.PLATFORMS:
        return platform
    if platform == "sugar":
        return "metaplex"
    return "generic"


def _validate_all_metadata(
    assets: list[dict],
    *,
    collection_name: str,
    platform: str,
    symbol: str = "",
    royalty_bps: int = 500,
    creator: str = "",
    image_base_uri: str = "",
) -> dict[str, Any]:
    """Перевірка metadata JSON для кожного токена + звірка image field з бандлом."""
    plat = _metadata_platform(platform)
    rows = export_bundle._ordered(assets)
    image_names, numbers = export_bundle._filenames(plat, rows)
    base = image_base_uri.rstrip("/")
    metadata_list = export_bundle.build_metadata_list(
        plat, assets, collection_name,
        image_base_uri=image_base_uri, symbol=symbol, royalty_bps=royalty_bps, creator=creator,
    )

    json_errors: list[dict[str, Any]] = []
    image_mismatches: list[dict[str, Any]] = []

    for idx, (meta, img_name, number) in enumerate(zip(metadata_list, image_names, numbers), start=1):
        expected_image = f"{base}/{img_name}" if base else img_name
        try:
            json.dumps(meta, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            json_errors.append({"index": idx, "token": number, "error": str(exc)})
            continue
        if not str(meta.get("name") or "").strip():
            json_errors.append({"index": idx, "token": number, "error": "missing name"})
        if not str(meta.get("image") or "").strip():
            json_errors.append({"index": idx, "token": number, "error": "missing image"})
        elif meta.get("image") != expected_image:
            image_mismatches.append({
                "index": idx,
                "token": number,
                "expected": expected_image,
                "got": meta.get("image"),
            })

    return {
        "json_errors": json_errors,
        "image_mismatches": image_mismatches,
        "tokens_checked": len(metadata_list),
    }


def _ipfs_to_https(uri: str) -> str:
    if uri.startswith("ipfs://"):
        return f"https://gateway.pinata.cloud/ipfs/{uri[7:].lstrip('/')}"
    return uri


def _probe_http_url(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 400:
                return True, ""
            return False, f"HTTP {resp.status}"
    except Exception:
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 400:
                    return True, ""
                return False, f"HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            return False, f"HTTP {exc.code}"
        except Exception as exc:
            return False, str(exc)[:120]


def _probe_ipfs_sample(
    assets: list[dict],
    platform: str,
    ipfs_result: dict,
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """HEAD/fetch першого metadata JSON і зображення після Pinata."""
    base_uri = str(ipfs_result.get("base_uri") or "").strip()
    image_base = str(ipfs_result.get("image_base_uri") or "").strip()
    if not base_uri or not image_base or not assets:
        return {"skipped": True, "ok": False, "detail": ""}

    plat = _metadata_platform(platform)
    rows = export_bundle._ordered(assets)
    image_names, numbers = export_bundle._filenames(plat, rows)
    if not numbers or not image_names:
        return {"skipped": True, "ok": False, "detail": ""}

    meta_url = _ipfs_to_https(f"{base_uri.rstrip('/')}/{numbers[0]}.json")
    img_url = _ipfs_to_https(f"{image_base.rstrip('/')}/{image_names[0]}")
    failures: list[str] = []
    for label, url in (("metadata", meta_url), ("image", img_url)):
        ok, detail = _probe_http_url(url, timeout=timeout)
        if not ok:
            failures.append(f"{label}: {detail or url}")
    if failures:
        return {"skipped": False, "ok": False, "detail": "; ".join(failures)}
    return {"skipped": False, "ok": True, "detail": ""}


def report_to_dict(report: QualityReport) -> dict[str, Any]:
    return {
        "version": 1,
        "score": report.score,
        "band": report.band,
        "summary": report.summary,
        "category_scores": report.category_scores,
        "items": [
            {
                "category": item.category,
                "code": item.code,
                "severity": item.severity,
                "points": item.points,
                "max_points": item.max_points,
                "fmt": item.fmt,
            }
            for item in report.items
        ],
    }


def format_markdown(
    report: QualityReport,
    collection_name: str = "",
    *,
    item_label: Callable[[CheckItem], str] | None = None,
) -> str:
    """Markdown-звіт для завантаження (як rarity-report)."""
    title = collection_name or "Collection"

    def _line(item: CheckItem) -> str:
        if item_label:
            return item_label(item)
        return f"[{item.severity}] {item.category}/{item.code} {item.fmt}"

    lines = [
        f"# NFT Quality Report — {title}",
        "",
        f"**Score:** {report.score}/100 ({report.band})",
        f"**Tokens:** {report.summary.get('token_count', '—')}",
        "",
        "## Category scores",
    ]
    for cat in CATEGORIES:
        lines.append(f"- **{cat}:** {report.category_scores.get(cat, 0)}")
    lines.extend(["", "## Checks"])
    for cat in CATEGORIES:
        cat_items = [i for i in report.items if i.category == cat]
        if not cat_items:
            continue
        lines.append(f"### {cat}")
        for item in cat_items:
            lines.append(f"- {_line(item)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def openai_call(api_key: str, model: str = DEFAULT_AI_MODEL) -> Callable[[str, str, float], str]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    def _call(system: str, user: str, temperature: float) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=AI_RESPONSE_FORMAT,
            temperature=temperature,
        )
        return response.choices[0].message.content or "{}"

    return _call


def openai_vision_json_call(
    api_key: str,
    model: str = DEFAULT_VISION_MODEL,
) -> Callable[[str, str, list[tuple[str, bytes]], dict, float], str]:
    """Vision callable: (system, user_text, images[(mime, bytes)], response_format, temperature)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    def _call(
        system: str,
        user_text: str,
        images: list[tuple[str, bytes]],
        response_format: dict,
        temperature: float,
    ) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for mime, raw in images:
            b64 = base64.b64encode(raw).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            response_format=response_format,
            temperature=temperature,
        )
        return response.choices[0].message.content or "{}"

    return _call


def _mime_for_bytes(data: bytes) -> str:
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if _is_webp(data):
        return "image/webp"
    return "image/png"


def _sample_indices(n: int, *, cap: int = VISION_SAMPLE_MAX) -> list[int]:
    if n <= 0:
        return []
    count = min(n, cap)
    if count == 1:
        return [0]
    return sorted({
        int(round(i * (n - 1) / (count - 1)))
        for i in range(count)
    })


def _style_pairs(n: int, *, cap: int = STYLE_PAIR_MAX) -> list[tuple[int, int]]:
    if n < 2:
        return []
    pairs: list[tuple[int, int]] = [(0, n - 1)]
    if n >= 4:
        pairs.append((1, n - 2))
    if n >= 6:
        pairs.append((n // 3, (2 * n) // 3))
    if n >= 8:
        pairs.append((n // 4, (3 * n) // 4))
    out: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for a, b in pairs:
        key = (min(a, b), max(a, b))
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out[:cap]


def analyze_thumbnail_readability(
    assets: list[dict],
    *,
    call: Callable[[str, str, list[tuple[str, bytes]], dict, float], str] | None = None,
    lang: str = "en",
) -> dict[str, Any]:
    """Vision: читабельність NFT у thumbnail (~128px). 3–5 зразків."""
    if call is None:
        return {"skipped": True, "reason": "no_call"}

    indices = _sample_indices(len(assets))
    images: list[tuple[str, bytes]] = []
    index_map: list[int] = []
    for idx in indices:
        data = _image_bytes(assets[idx])
        if not data:
            continue
        images.append((_mime_for_bytes(data), data))
        index_map.append(idx)

    if not images:
        return {"skipped": True, "reason": "no_images"}

    lang_hint = "Ukrainian" if lang == "uk" else "English"
    labels = ", ".join(f"image {i + 1} = token index {index_map[i]}" for i in range(len(index_map)))
    system = (
        "You are an NFT marketplace UX reviewer. Judge if each image stays recognizable "
        "at small marketplace thumbnail size (~128px): subject clarity, contrast, clutter. "
        f"Respond in JSON only. Notes in {lang_hint}."
    )
    user_text = (
        f"Collection thumbnail readability check. Sample mapping: {labels}. "
        "Score overall 1–10. Flag issues that hurt discoverability at small size."
    )
    try:
        raw = call(system, user_text, images, THUMBNAIL_VISION_FORMAT, 0.2)
        data = json.loads(raw)
        data["samples_checked"] = len(images)
        data["token_indices"] = index_map
        return data
    except Exception as exc:
        return {"skipped": True, "reason": str(exc)[:120]}


def analyze_style_consistency(
    assets: list[dict],
    *,
    call: Callable[[str, str, list[tuple[str, bytes]], dict, float], str] | None = None,
    lang: str = "en",
) -> dict[str, Any]:
    """Vision: style consistency across 2–4 пар зображень."""
    if call is None:
        return {"skipped": True, "reason": "no_call"}

    pairs = _style_pairs(len(assets))
    if not pairs:
        return {"skipped": True, "reason": "need_two_assets"}

    images: list[tuple[str, bytes]] = []
    pair_labels: list[str] = []
    for a, b in pairs:
        da = _image_bytes(assets[a])
        db = _image_bytes(assets[b])
        if not da or not db:
            continue
        images.append((_mime_for_bytes(da), da))
        images.append((_mime_for_bytes(db), db))
        pair_labels.append(f"pair {len(pair_labels) + 1}: indices {a} vs {b}")

    if not images:
        return {"skipped": True, "reason": "no_images"}

    lang_hint = "Ukrainian" if lang == "uk" else "English"
    system = (
        "You are an NFT art director. Compare generative collection style consistency: "
        "palette, lighting, line work, rendering, mood. Respond JSON only. "
        f"Notes in {lang_hint}."
    )
    user_text = (
        "Images arrive in pairs (A then B). " + "; ".join(pair_labels) + ". "
        "Score each pair 1–10 and overall consistency."
    )
    try:
        raw = call(system, user_text, images, STYLE_VISION_FORMAT, 0.2)
        data = json.loads(raw)
        data["pairs_checked"] = len(pair_labels)
        return data
    except Exception as exc:
        return {"skipped": True, "reason": str(exc)[:120]}


def run_ai_deep_dive(
    report: QualityReport,
    assets: list[dict],
    *,
    collection_name: str,
    vision_call: Callable[[str, str, list[tuple[str, bytes]], dict, float], str] | None = None,
    tips_call: Callable[[str, str, float], str] | None = None,
    lang: str = "en",
) -> AiDeepDiveResult:
    """Vision thumbnail + style + текстові поради (один пакет)."""
    thumbnail = analyze_thumbnail_readability(assets, call=vision_call, lang=lang)
    style = analyze_style_consistency(assets, call=vision_call, lang=lang)
    tips = generate_ai_tips(
        report,
        collection_name=collection_name,
        call=tips_call,
        lang=lang,
        thumbnail=thumbnail if not thumbnail.get("skipped") else None,
        style=style if not style.get("skipped") else None,
    )
    return AiDeepDiveResult(thumbnail=thumbnail, style=style, tips=tips)


def generate_ai_tips(
    report: QualityReport,
    *,
    collection_name: str,
    call: Callable[[str, str, float], str] | None = None,
    lang: str = "en",
    thumbnail: dict[str, Any] | None = None,
    style: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """LLM-поради (3–6 пунктів). Повертає [{category, text}, …]."""
    if call is None:
        return []

    weak = [
        f"{i.category}/{i.code} ({i.severity})"
        for i in report.items
        if i.severity in ("warn", "fail") and i.points < i.max_points
    ][:12]
    lang_hint = "Ukrainian" if lang == "uk" else "English"
    system = (
        "You are an NFT launch advisor. Give concise, actionable pre-mint recommendations "
        f"in {lang_hint}. Output JSON only. Do not promise financial returns. "
        "This is advisory only — the user may still export.\n"
        f"{ADVISOR_CHECKLIST_BRIEF}"
    )
    payload: dict[str, Any] = {
        "collection": collection_name or "Unnamed",
        "score": report.score,
        "band": report.band,
        "summary": report.summary,
        "weak_checks": weak,
        "checklist": report.summary.get("checklist") or {},
        "categories": list(CATEGORIES),
    }
    if thumbnail:
        payload["ai_thumbnail"] = thumbnail
    if style:
        payload["ai_style"] = style
    user = json.dumps(payload, ensure_ascii=False)

    try:
        raw = call(system, user, 0.4)
        data = json.loads(raw)
        tips = data.get("tips") or []
        return [
            {"category": str(t.get("category", "marketing")), "text": str(t.get("text", "")).strip()}
            for t in tips if t.get("text")
        ][:6]
    except Exception:
        return []
