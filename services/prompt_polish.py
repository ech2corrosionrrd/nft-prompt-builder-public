"""LLM-полірування промптів матриці (ПЛАН_ЯКОСТІ.md § Q1.4).

Найвищий ROI плану якості: сирі comma-join промпти матриці
(`prompt_service.build_matrix`) проганяються через LLM, який переписує кожен у
узгоджений за стилем колекції англомовний промпт + короткий negative, зберігаючи
traits незмінними. Працює чанками (10–20) з режимами Light/Full.

Мережа ізольована за ін'єкцією `call(system, user, temperature) -> str`:
прод-обгортку дає `openai_call`, тести підставляють фейковий виклик. Парсинг і
зіставлення індексів перевикористовуємо з `batch` (та сама перевірена логіка,
що й Classic Batch).
"""

from __future__ import annotations

from typing import Callable

from batch import assign_chunk_positions, parse_batch_response, supports_temperature
from services.prompt_quality import DEFAULT_POLISH_TEMPERATURE

CHUNK_SIZE = 15
MODE_LIGHT = "light"
MODE_FULL = "full"
POLISH_MODES = (MODE_LIGHT, MODE_FULL)
DEFAULT_POLISH_MODEL = "gpt-4o-mini"

# Підказки polish за архетипом (ПЛАН_АБСТРАКЦІЯ AG2.7, landscape/event).
_POLISH_ARCHETYPE_HINTS: dict[str, str] = {
    "abstract_geometric": (
        "Abstract geometric collection — no characters, faces, or portraits; "
        "emphasize shape, symmetry, and color field."
    ),
    "landscape": (
        "Landscape collection — wide establishing views, atmospheric depth; "
        "no portrait framing, no people as subjects."
    ),
    "brand_icon": (
        "Brand icon collection — centered mark/mascot, clean negative space; "
        "no photorealistic faces, no trademarked brand names."
    ),
    "event_badge": (
        "Event badge collection — commemorative medallion layout; "
        "no real dates or trademarked event names."
    ),
    "fine_art": "Fine-art 1/1 — single cohesive art piece, gallery quality.",
}

# Структурований формат відповіді (index/prompt/negative); traits зберігаємо
# локально, тож моделі їх не повертаємо — менше токенів, менше дрейфу.
POLISH_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "polished_prompts",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "prompts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "prompt": {"type": "string"},
                            "negative": {"type": "string"},
                        },
                        "required": ["index", "prompt", "negative"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["prompts"],
            "additionalProperties": False,
        },
    },
}


def chunk_count(total: int, chunk_size: int = CHUNK_SIZE) -> int:
    """Кількість чанків для білінгу (1 кредит/чанк)."""
    if total <= 0:
        return 0
    size = max(chunk_size, 1)
    return (total + size - 1) // size


def build_polish_system(mode: str, style_bible: str = "", archetype: str = "pfp") -> str:
    depth = (
        "Lightly refine wording and grammar; keep the draft's intent and length."
        if mode == MODE_LIGHT
        else "Rewrite into a vivid, production-grade prompt with consistent collection style."
    )
    bible = f"\nCollection style bible (must hold across all): {style_bible.strip()}" if style_bible.strip() else ""
    arch_hint = _POLISH_ARCHETYPE_HINTS.get((archetype or "pfp").strip(), "")
    arch_line = f"\nArchetype rule: {arch_hint}" if arch_hint else ""
    return (
        "You are an AI Prompt Engineer for NFT collections.\n"
        "You receive numbered DRAFT image prompts, each with its fixed traits.\n"
        f"{depth}\n"
        "For EACH draft return a polished English prompt and a short English negative prompt.\n"
        "Keep the traits' meaning — do not drop or rename traits; do not add new subjects.\n"
        'Return JSON: {"prompts": [{"index": <n>, "prompt": "english", "negative": "english"}]}\n'
        "index — the draft number (from 1). One element per draft, same count."
        f"{bible}{arch_line}"
    )


def build_polish_user(items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(items, start=1):
        traits = item.get("traits") or {}
        traits_str = ", ".join(f"{k}: {v}" for k, v in traits.items()) or "(none)"
        lines.append(f"{i}. DRAFT: {item.get('prompt', '')}\n   TRAITS: {traits_str}")
    return "Drafts to polish:\n" + "\n".join(lines)


def merge_polished(originals: list[dict], parsed_items: list[dict]) -> list[dict]:
    """Зливає відповідь LLM назад в оригінали, зберігаючи traits/seed.

    Старий промпт зсувається в polish_history (Q1.5/Q2.6). Порожні поля від
    моделі ігноруємо (лишаємо оригінал). Індекси зіставляє assign_chunk_positions.
    """
    out = [dict(o) for o in originals]
    for pos, item in assign_chunk_positions(parsed_items, len(originals)):
        target = out[pos - 1]
        new_prompt = str(item.get("prompt", "")).strip()
        if new_prompt and new_prompt != target.get("prompt", ""):
            history = list(target.get("polish_history", []))
            if target.get("prompt"):
                history.append(target["prompt"])
            target["polish_history"] = history
            target["prompt"] = new_prompt
            target["version"] = int(target.get("version", 1)) + 1  # Q2.6: версіонування
        negative = str(item.get("negative", "")).strip()
        if negative:
            target["negative"] = negative
    return out


def openai_call(api_key: str, model: str = DEFAULT_POLISH_MODEL) -> Callable[[str, str, float], str]:
    """Прод-обгортка виклику OpenAI зі структурованим JSON-форматом."""
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
            response_format=POLISH_RESPONSE_FORMAT,
            **sampling,
        )
        return response.choices[0].message.content or "{}"

    return _call


def polish_prompts(
    prompts: list[dict],
    *,
    call: Callable[[str, str, float], str],
    mode: str = MODE_FULL,
    chunk_size: int = CHUNK_SIZE,
    style_bible: str = "",
    archetype: str = "pfp",
    temperature: float = DEFAULT_POLISH_TEMPERATURE,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], list[str]]:
    """Полірує всі промпти чанками. Повертає (нові_промпти, помилки_чанків).

    Збій чанку не валить процес: для нього лишаються оригінальні промпти, а
    причина додається в errors (так оператор не втрачає вже сплачені кредити
    решти чанків). Порядок результатів збігається з вхідним.
    """
    if not prompts:
        return [], []
    size = max(chunk_size, 1)
    system = build_polish_system(mode, style_bible, archetype=archetype)
    results: list[dict] = []
    errors: list[str] = []
    chunks = [prompts[i: i + size] for i in range(0, len(prompts), size)]
    for idx, chunk in enumerate(chunks):
        try:
            raw = call(system, build_polish_user(chunk), temperature)
            parsed = parse_batch_response(raw)
            results.extend(merge_polished(chunk, parsed))
        except Exception as exc:  # noqa: BLE001 — один поганий чанк не валить решту
            results.extend(dict(o) for o in chunk)
            if len(errors) < 5:
                errors.append(f"чанк {idx + 1}: {exc}")
        if on_progress:
            on_progress(idx + 1, len(chunks))
    return results, errors
