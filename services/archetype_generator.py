"""P3.5 — генерація списку archetypes/motifs через LLM (Етап 1, матриця).

Замість ручного набору 50 персонажів або зовнішнього ChatGPT — один виклик
з темою колекції → унікальні англомовні імена для першої осі матриці.
Білінг: ~1 кредит / 15 імен (як prompt polish).
"""

from __future__ import annotations

import json
import re
from typing import Callable

from batch import supports_temperature
from services import prompt_polish

CHUNK_SIZE = 15
DEFAULT_MODEL = prompt_polish.DEFAULT_POLISH_MODEL

_ARCHETYPE_KIND: dict[str, str] = {
    "pfp": (
        "character archetypes for an NFT avatar collection — short English noun phrases "
        "(2–6 words), vivid and distinct, no duplicate concepts"
    ),
    "abstract_geometric": (
        "abstract geometric motifs — shapes, patterns, gradients; NO characters, faces, "
        "portraits, or human figures"
    ),
    "landscape": (
        "landscape scene descriptors — places, biomes, atmospheres; wide establishing views, "
        "no portrait framing, no people as subjects"
    ),
    "brand_icon": (
        "brand mark presentation contexts — icon layouts, merch mockups, social cards; "
        "no literal trademark names of real companies"
    ),
    "event_badge": (
        "event badge tier or visual style names — commemorative, collectible POAP-style; "
        "no real dates or trademarked event names"
    ),
    "fine_art": (
        "fine-art subject variations — one-of-a-kind art piece themes, poetic and distinct"
    ),
}

_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "archetype_names",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
            "required": ["names"],
            "additionalProperties": False,
        },
    },
}


def credit_cost(n: int, chunk_size: int = CHUNK_SIZE) -> int:
    """Кредити за генерацію N імен (~1 cr / chunk)."""
    return prompt_polish.chunk_count(n, chunk_size)


def build_system(archetype: str, style_bible: str = "") -> str:
    kind = _ARCHETYPE_KIND.get(archetype, _ARCHETYPE_KIND["pfp"])
    bible = (
        f"\nCollection style bible (stay consistent): {style_bible.strip()}"
        if style_bible.strip()
        else ""
    )
    return (
        "You are an NFT collection designer.\n"
        f"Generate unique English names for: {kind}.\n"
        "Each name must be unique within the batch — no near-duplicates.\n"
        "Return JSON: {\"names\": [\"name one\", \"name two\", ...]}\n"
        "Names only in English; no numbering prefixes; no quotes inside names."
        f"{bible}"
    )


def build_user(theme: str, n: int, *, existing: list[str] | None = None) -> str:
    theme = (theme or "NFT collection").strip()
    lines = [f"Theme / direction: {theme}", f"Count: {n} unique names."]
    if existing:
        sample = ", ".join(existing[:30])
        lines.append(f"Already used (do NOT repeat): {sample}")
    return "\n".join(lines)


def parse_names(raw: str) -> list[str]:
    """Розбір JSON-відповіді LLM → список імен."""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return []
    names = data.get("names") if isinstance(data, dict) else None
    if not isinstance(names, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in names:
        name = re.sub(r"\s+", " ", str(item).strip())
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def openai_call(api_key: str, model: str = DEFAULT_MODEL) -> Callable[[str, str, float], str]:
    """Прод-обгортка OpenAI зі структурованим JSON."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    def _call(system: str, user: str, temperature: float) -> str:
        sampling = {"temperature": temperature} if supports_temperature(model) else {}
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=_RESPONSE_FORMAT,
            **sampling,
        )
        return response.choices[0].message.content or "{}"

    return _call


def generate_archetypes(
    n: int,
    theme: str,
    *,
    archetype: str = "pfp",
    style_bible: str = "",
    call: Callable[[str, str, float], str],
    chunk_size: int = CHUNK_SIZE,
    temperature: float = 0.75,
) -> tuple[list[str], list[str]]:
    """Генерує до N унікальних імен. Повертає (names, errors)."""
    n = max(0, int(n))
    if n == 0:
        return [], []
    size = max(chunk_size, 1)
    system = build_system(archetype, style_bible)
    collected: list[str] = []
    seen: set[str] = set()
    errors: list[str] = []
    remaining = n

    while remaining > 0 and len(collected) < n:
        batch_n = min(remaining, size)
        try:
            raw = call(
                system,
                build_user(theme, batch_n, existing=collected or None),
                temperature,
            )
            batch = parse_names(raw)
        except Exception as exc:
            errors.append(str(exc))
            break
        if not batch:
            errors.append("empty batch")
            break
        for name in batch:
            key = name.casefold()
            if key not in seen:
                seen.add(key)
                collected.append(name)
                if len(collected) >= n:
                    break
        got = len(batch)
        remaining = n - len(collected)
        if got < batch_n and remaining > 0:
            errors.append(f"short batch ({got}/{batch_n})")

    return collected[:n], errors
