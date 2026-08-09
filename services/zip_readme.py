"""Локалізований README.txt для ZIP-експорту (без Streamlit-сесії)."""

from __future__ import annotations

import re

from ui_strings import LANG_EN, translate

_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_INLINE_CODE = re.compile(r"`([^`]+)`")

_GUIDE_KEYS: dict[str, str] = {
    "opensea": "ec.guide.opensea",
    "metaplex": "ec.guide.metaplex",
    "thirdweb": "ec.guide.thirdweb",
    "generic": "ec.guide.generic",
    "w3ir": "ec.guide.w3ir",
    "sugar": "ec.guide.sugar",
}


def markdown_to_plain(text: str) -> str:
    """Спрощує markdown-гайд до plain text для README.txt у ZIP."""
    out: list[str] = []
    for raw in text.splitlines():
        line = _BOLD.sub(r"\1", raw)
        line = _LINK.sub(r"\1", line)
        line = _INLINE_CODE.sub(r"\1", line)
        if line.startswith("### "):
            title = line[4:].strip()
            if out and out[-1] != "":
                out.append("")
            out.append(title)
            out.append("")
        else:
            out.append(line)
    result = "\n".join(out)
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    return result.strip()


def zip_readme(
    platform: str,
    lang: str | None = None,
    *,
    ipfs_result: dict | None = None,
    has_allowlist: bool = False,
    attribution_line: str | None = None,
) -> str:
    """Текст README.txt — та сама мова, що UI під час збірки ZIP."""
    lang = lang or LANG_EN
    guide_key = _GUIDE_KEYS.get(platform, _GUIDE_KEYS["generic"])
    parts = [
        translate("ec.zip.readme.header", lang),
        "",
        markdown_to_plain(translate("ec.guide_intro", lang)),
        "",
        markdown_to_plain(translate(guide_key, lang)),
    ]
    if platform == "w3ir":
        parts.extend(["", translate("ec.zip.readme.w3ir_technical", lang)])
    if platform == "sugar":
        parts.extend(["", translate("ec.zip.readme.sugar_technical", lang)])
        if has_allowlist:
            parts.extend(["", translate("ec.zip.readme.sugar_allowlist", lang)])
    if ipfs_result:
        parts.extend([
            "",
            translate(
                "ec.zip.readme.ipfs",
                lang,
                base_uri=ipfs_result.get("base_uri", ""),
                image_base_uri=ipfs_result.get("image_base_uri", ""),
            ),
        ])
    if attribution_line:
        parts.extend(["", attribution_line])
    return "\n".join(parts)
