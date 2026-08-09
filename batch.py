"""Утиліти для batch-генерації промтів: rarity, семплування, async-генерація, експорт."""

import asyncio
import csv
import io
import json
import random
import re
import zipfile
from collections import Counter
from typing import Any, Callable

from openai import AsyncOpenAI

try:
    from anthropic import AsyncAnthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    AsyncAnthropic = None  # type: ignore[assignment,misc]
    _ANTHROPIC_AVAILABLE = False

from i18n import mint_attributes
from metadata_provenance import add_rarity_ranks

CONCURRENT_REQUESTS = 4
JSON_RETRIES = 2
DEFAULT_CHUNK_SIZE = 10

# USD за 1M токенів: (input, output)
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "o4-mini": (1.10, 4.40),
    # Claude (Anthropic) — USD за 1M токенів
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
}


def is_claude_model(model: str) -> bool:
    return model.startswith("claude-")

BATCH_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "nft_prompts",
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
                            "attributes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "trait_type": {"type": "string"},
                                        "value": {"type": "string"},
                                    },
                                    "required": ["trait_type", "value"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["index", "prompt", "negative", "attributes"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["prompts"],
            "additionalProperties": False,
        },
    },
}


# ── Traits: парсинг, ваги, семплування ────────────────────────────────────────

def parse_trait_lines(raw: str) -> list[tuple[str, float]]:
    """Парсить traits із текстового поля. Формат рядка: «назва» або «назва | вага»."""
    items: list[tuple[str, float]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        name, weight = line, 1.0
        if "|" in line:
            left, _, right = line.rpartition("|")
            try:
                weight = float(right.strip().replace(",", "."))
                name = left.strip()
            except ValueError:
                pass
        if name:
            items.append((name, max(weight, 0.001)))
    return items


def _normalize(items: list) -> list[tuple[str, float]]:
    """Приводить список traits до вигляду [(назва, вага)]."""
    result = []
    for item in items:
        if isinstance(item, (tuple, list)):
            result.append((str(item[0]), float(item[1])))
        else:
            result.append((str(item), 1.0))
    return result


def count_combinations(traits: dict[str, list]) -> int:
    """Кількість унікальних комбінацій traits."""
    if not traits:
        return 0
    total = 1
    for items in traits.values():
        total *= max(len(items), 1)
    return total


def sample_trait_combinations(
    traits: dict[str, list], count: int, rng: random.Random | None = None,
) -> list[dict[str, str]]:
    """Генерує до `count` комбінацій traits зі зваженим семплуванням.

    Кожна комбінація бере рівно по одному значенню з КОЖНОЇ категорії — саме це
    дає айтем із повним набором шарів (убір + окуляри + одяг + …), на якому
    тримається rarity.

    Комбінації унікальні, доки не вичерпано весь простір варіантів;
    далі додаються дублікати. Повний itertools.product не матеріалізується.

    rng — власне джерело випадковості; без нього береться глобальний `random`
    (стара поведінка). Потрібне там, де результат має бути відтворюваним:
    підготовка промптів із шаблону не повинна давати різний набір на кожен
    rerun Streamlit.
    """
    if not traits:
        return [{} for _ in range(count)]

    rand = rng or random
    categories = list(traits.keys())
    normalized = {cat: _normalize(traits[cat]) for cat in categories}
    names = {cat: [n for n, _ in normalized[cat]] for cat in categories}
    weights = {cat: [w for _, w in normalized[cat]] for cat in categories}
    total = count_combinations(traits)

    seen: set[tuple[str, ...]] = set()
    result: list[dict[str, str]] = []
    attempts, max_attempts = 0, max(count * 50, 1000)

    while len(result) < count and attempts < max_attempts:
        attempts += 1
        combo = tuple(
            rand.choices(names[cat], weights=weights[cat], k=1)[0]
            for cat in categories
        )
        if combo in seen and len(seen) < total:
            continue
        seen.add(combo)
        result.append(dict(zip(categories, combo)))

    while len(result) < count:
        result.append(dict(result[rand.randrange(len(result))]))

    return result


def supports_temperature(model: str) -> bool:
    """Reasoning-моделі (o-серія: o1, o3, o4-mini…) приймають лише дефолтну temperature."""
    return re.match(r"^o\d", model) is None


# ── Промти ────────────────────────────────────────────────────────────────────

def build_batch_system_prompt(platform: str) -> str:
    return (
        "Ти — AI Prompt Engineer для NFT-колекцій.\n"
        f"Цільова платформа: {platform}.\n"
        "Отримуєш базовий концепт і нумерований список комбінацій traits.\n"
        "Для КОЖНОЇ комбінації створи фінальний англомовний промт.\n"
        'Поверни JSON: {"prompts": [{"index": <номер>, "prompt": "english", "negative": "english", '
        '"attributes": [{"trait_type": "english category", "value": "english value"}]}]}\n'
        "index — номер комбінації зі списку (з 1). Кількість елементів = кількості комбінацій.\n"
        "Промти узгоджені за стилем колекції, унікальні за traits. Negative — короткий.\n"
        "attributes — traits англійською для on-chain метаданих (ERC-721); одна пара на категорію з комбінації."
    )


def build_batch_user_prompt(
    base: dict[str, Any],
    combos: list[dict[str, str]],
    tech_params: str,
) -> str:
    combos_lines = [
        f"{i + 1}. {json.dumps(combo, ensure_ascii=False)}"
        for i, combo in enumerate(combos)
    ]
    notes = (base.get("extra_notes") or "").strip()
    notes_line = f"\n- Додаткові побажання: {notes}" if notes else ""
    return f"""
Базовий концепт:
- Об'єкт: {base['idea']}
- Стиль: {base['style']}
- Ракурс: {base['camera']}
- Освітлення: {base['lighting']}
- Фон: {base['background']}
- Якість: {base['quality']}
- Настрій: {base['mood']}{notes_line}
- Технічні параметри: {tech_params}

Комбінації traits ({len(combos)} шт.):
{chr(10).join(combos_lines)}
"""


def parse_batch_response(content: str) -> list[dict]:
    """Парсить JSON з відповіді GPT (об'єкт із ключем 'prompts' або масив)."""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()

    data = json.loads(text)
    if isinstance(data, dict) and "prompts" in data:
        items = data["prompts"]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Очікувався JSON з ключем 'prompts' або масив")

    if not all(isinstance(i, dict) and i.get("prompt") for i in items):
        raise ValueError("Кожен елемент має містити непорожній 'prompt'")
    return items


# ── Async-генерація ───────────────────────────────────────────────────────────

async def _call_openai(
    client: AsyncOpenAI,
    model: str,
    system: str,
    user: str,
    temperature: float,
):
    sampling = {"temperature": temperature} if supports_temperature(model) else {}
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=BATCH_RESPONSE_FORMAT,
        **sampling,
    )
    return response.choices[0].message.content or "{}", response.usage


async def _call_claude(client, model: str, system: str, user: str):
    from types import SimpleNamespace
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = next((b.text for b in response.content if hasattr(b, "text")), "{}")
    usage = SimpleNamespace(
        prompt_tokens=response.usage.input_tokens,
        completion_tokens=response.usage.output_tokens,
    )
    return text, usage


async def generate_chunk(
    client,  # AsyncOpenAI | AsyncAnthropic
    model: str,
    platform: str,
    base: dict,
    chunk: list[dict[str, str]],
    tech_params: str,
    temperature: float,
    semaphore: asyncio.Semaphore,
):
    async with semaphore:
        system = build_batch_system_prompt(platform)
        user = build_batch_user_prompt(base, chunk, tech_params)
        last_err: Exception = ValueError("Не вдалося отримати валідну відповідь")
        for _ in range(JSON_RETRIES + 1):
            try:
                if is_claude_model(model):
                    raw, usage = await _call_claude(client, model, system, user)
                else:
                    raw, usage = await _call_openai(client, model, system, user, temperature)
                return parse_batch_response(raw), usage
            except (json.JSONDecodeError, ValueError) as err:
                last_err = err
        raise last_err


def assign_chunk_positions(items: list[dict], size: int) -> list[tuple[int, dict]]:
    """Зіставляє елементи відповіді LLM з позиціями чанку (1..size) без дублікатів.

    Перевага — валідному й ще не зайнятому "index" від моделі;
    інакше елемент отримує найменшу вільну позицію.
    """
    used: set[int] = set()
    assigned: list[tuple[int, dict]] = []
    for item in items[:size]:
        raw = item.get("index") or 0
        if 1 <= raw <= size and raw not in used:
            pos = raw
        else:
            pos = next(p for p in range(1, size + 1) if p not in used)
        used.add(pos)
        assigned.append((pos, item))
    return assigned


async def generate_batch_async(
    api_key: str,
    model: str,
    platform: str,
    base: dict,
    combos: list[dict[str, str]],
    tech_params: str,
    temperature: float,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[dict], dict[str, int], list[str]]:
    """Паралельна batch-генерація. Повертає (результати, сумарні токени, помилки чанків).

    Якщо не вдався жоден чанк — кидає першу помилку, щоб користувач бачив причину.
    """
    if is_claude_model(model):
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError("Пакет anthropic не встановлено. Запустіть: pip install anthropic")
        client = AsyncAnthropic(api_key=api_key)
    else:
        client = AsyncOpenAI(api_key=api_key)
    chunks = [combos[i: i + chunk_size] for i in range(0, len(combos), chunk_size)]
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async def run_chunk(idx: int, chunk: list[dict[str, str]]):
        items, usage = await generate_chunk(
            client, model, platform, base, chunk, tech_params, temperature, semaphore
        )
        return idx, chunk, items, usage

    results: list[dict] = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0}
    errors: list[str] = []
    first_error: Exception | None = None
    try:
        tasks = [asyncio.create_task(run_chunk(i, c)) for i, c in enumerate(chunks)]
        done = 0
        for fut in asyncio.as_completed(tasks):
            try:
                idx, chunk, items, usage = await fut
                offset = idx * chunk_size
                for pos, item in assign_chunk_positions(items, len(chunk)):
                    row: dict = {
                        "id": offset + pos,
                        "traits": chunk[pos - 1],
                        "prompt": item.get("prompt", ""),
                        "negative": item.get("negative", ""),
                    }
                    if item.get("attributes"):
                        row["attributes"] = item["attributes"]
                    results.append(row)
                if usage:
                    usage_total["prompt_tokens"] += usage.prompt_tokens
                    usage_total["completion_tokens"] += usage.completion_tokens
            except Exception as err:
                if first_error is None:
                    first_error = err
                if len(errors) < 3:
                    errors.append(str(err))
            done += 1
            if on_progress:
                on_progress(done, len(chunks))
    finally:
        await client.close()

    if not results and first_error is not None:
        raise first_error

    results.sort(key=lambda r: r["id"])
    add_rarity_scores(results)
    return results, usage_total, errors


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = MODEL_PRICES.get(model, (0.50, 1.50))
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


# ── Rarity ────────────────────────────────────────────────────────────────────

def add_rarity_scores(rows: list[dict]) -> None:
    """Додає rarity_score кожному токену: сума n/частота за кожним trait."""
    if not rows:
        return
    counts: Counter = Counter()
    for row in rows:
        for cat, val in row.get("traits", {}).items():
            counts[(cat, val)] += 1
    n = len(rows)
    for row in rows:
        traits = row.get("traits", {})
        score = sum(n / counts[(cat, val)] for cat, val in traits.items())
        row["rarity_score"] = round(score, 2)


def trait_distribution(rows: list[dict], weighted_traits: dict[str, list]) -> list[dict]:
    """Порівнює очікуваний (за вагами) та фактичний розподіл traits у колекції."""
    n = len(rows)
    counts: Counter = Counter()
    for row in rows:
        for cat, val in row.get("traits", {}).items():
            counts[(cat, val)] += 1

    table = []
    for cat, items in weighted_traits.items():
        normalized = _normalize(items)
        total_weight = sum(w for _, w in normalized) or 1.0
        for name, weight in normalized:
            count = counts.get((cat, name), 0)
            table.append({
                "Категорія": cat,
                "Trait": name,
                "Очікувано %": round(100 * weight / total_weight, 1),
                "Фактично %": round(100 * count / n, 1) if n else 0.0,
                "К-сть": count,
            })
    return table


# ── Експорт ───────────────────────────────────────────────────────────────────

def to_csv(rows: list[dict]) -> str:
    """Конвертує batch-результати в CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["id", "prompt", "negative", "traits", "rarity_score"])
    for row in rows:
        writer.writerow([
            row.get("id", ""),
            row.get("prompt", ""),
            row.get("negative", ""),
            json.dumps(row.get("traits", {}), ensure_ascii=False),
            row.get("rarity_score", ""),
        ])
    return buf.getvalue()


def build_metadata(
    rows: list[dict],
    collection_name: str,
    description: str = "",
    image_base_uri: str = "",
) -> list[dict]:
    """Будує метадані ERC-721/OpenSea для кожного токена."""
    rows = list(rows)
    if len(rows) > 1 and any(r.get("traits") for r in rows):
        add_rarity_ranks(rows)
    base = image_base_uri.rstrip("/")
    metadata = []
    for row in rows:
        token_id = row.get("id")
        image = f"{base}/{token_id}.png" if base else f"{token_id}.png"
        metadata.append({
            "token_id": token_id,
            "name": f"{collection_name} #{token_id}",
            "description": description,
            "image": image,
            "attributes": mint_attributes(row),
        })
    return metadata


def build_metadata_metaplex(
    rows: list[dict],
    collection_name: str,
    symbol: str = "",
    description: str = "",
    image_base_uri: str = "",
    seller_fee_bps: int = 500,
    creator_address: str = "",
) -> list[dict]:
    """Будує метадані у форматі Metaplex Token Standard (Solana)."""
    rows = list(rows)
    if len(rows) > 1 and any(r.get("traits") for r in rows):
        add_rarity_ranks(rows)
    base = image_base_uri.rstrip("/")
    metadata = []
    for row in rows:
        token_id = row.get("id")
        image = f"{base}/{token_id}.png" if base else f"{token_id}.png"
        meta = {
            "token_id": token_id,
            "name": f"{collection_name} #{token_id}",
            "symbol": symbol,
            "description": description,
            "image": image,
            "seller_fee_basis_points": seller_fee_bps,
            "attributes": mint_attributes(row),
            "properties": {
                "files": [{"uri": image, "type": "image/png"}],
                "category": "image",
            },
        }
        if creator_address:
            meta["properties"]["creators"] = [{"address": creator_address, "share": 100}]
        metadata.append(meta)
    return metadata


def clean_metadata(metadata: list[dict]) -> list[dict]:
    """Повертає копії метаданих без внутрішніх полів (token_id) для експорту."""
    return [{k: v for k, v in m.items() if k != "token_id"} for m in metadata]


def metadata_zip(metadata: list[dict]) -> bytes:
    """ZIP-архів: окремий JSON на кожен токен + збірний _collection.json."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for meta in metadata:
            token_id = str(meta.get("token_id") or meta["name"].rsplit("#", 1)[-1].strip())
            zf.writestr(f"{token_id}.json", json.dumps(clean_metadata([meta])[0], ensure_ascii=False, indent=2))
        zf.writestr("_collection.json", json.dumps(clean_metadata(metadata), ensure_ascii=False, indent=2))
    return buf.getvalue()


def strip_platform_flags(prompt: str) -> str:
    """Прибирає Midjourney-теги (--ar, --s, --v тощо) для image-API."""
    cleaned = re.sub(r"--\w+(\s+[\w:.]+)?", "", prompt)
    return re.sub(r"\s{2,}", " ", cleaned).strip()
