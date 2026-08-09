"""Звіт рідкості колекції для Export Center (без Streamlit)."""

from __future__ import annotations

from collections import Counter

from i18n import trait_type_en
from metadata_provenance import add_rarity_ranks


def _trait_frequency(rows: list[dict]) -> list[dict]:
    n = len(rows)
    if n == 0:
        return []
    counts: Counter = Counter()
    for row in rows:
        for cat, val in (row.get("traits") or {}).items():
            counts[(trait_type_en(str(cat)), str(val))] += 1
    out = []
    for (cat, val), count in sorted(counts.items(), key=lambda x: (-x[1], x[0][0], x[0][1])):
        out.append({
            "category": cat,
            "trait": val,
            "count": count,
            "pct": round(100 * count / n, 1),
        })
    return out


def summarize_collection(assets: list[dict]) -> dict | None:
    """Підсумок rarity для UI. None — якщо в колекції немає traits."""
    rows = [dict(a) for a in assets]
    if not rows or not any(r.get("traits") for r in rows):
        return None
    add_rarity_ranks(rows)
    rank_rows = []
    for i, row in enumerate(rows, start=1):
        rank_rows.append({
            "token": row.get("name") or f"#{i}",
            "rank": row.get("rarity_rank", "—"),
            "score": row.get("rarity_score", "—"),
            "tier": row.get("rarity_tier", "—"),
        })
    rank_rows.sort(key=lambda r: r["rank"] if isinstance(r["rank"], int) else 9999)
    tiers = Counter(r["tier"] for r in rank_rows if r["tier"] != "—")
    return {
        "total": len(rows),
        "rank_rows": rank_rows,
        "trait_rows": _trait_frequency(rows),
        "tier_counts": dict(tiers),
    }


def skewed_traits(assets: list[dict], *, threshold_pct: float = 50.0) -> list[dict]:
    """Трейти з часткою > threshold_pct supply (для QC і rarity UX)."""
    summary = summarize_collection(assets)
    if not summary:
        return []
    return [
        tr for tr in summary.get("trait_rows", [])
        if float(tr.get("pct") or 0) > threshold_pct
    ]


def format_markdown(summary: dict, collection_name: str = "") -> str:
    """Markdown-звіт для завантаження."""
    title = collection_name or "Collection"
    lines = [f"# Rarity Report — {title}", "", f"**Tokens:** {summary['total']}", ""]
    if summary.get("tier_counts"):
        lines.append("## Tier distribution")
        for tier, n in sorted(summary["tier_counts"].items(), key=lambda x: x[0]):
            lines.append(f"- **{tier}:** {n}")
        lines.append("")
    lines.append("## Rankings (1 = rarest)")
    lines.append("| Token | Rank | Score | Tier |")
    lines.append("|-------|------|-------|------|")
    for r in summary["rank_rows"]:
        lines.append(f"| {r['token']} | {r['rank']} | {r['score']} | {r['tier']} |")
    lines.append("")
    lines.append("## Trait frequency")
    lines.append("| Category | Trait | Count | % |")
    lines.append("|----------|-------|-------|---|")
    for tr in summary["trait_rows"]:
        lines.append(f"| {tr['category']} | {tr['trait']} | {tr['count']} | {tr['pct']}% |")
    lines.append("")
    return "\n".join(lines)
