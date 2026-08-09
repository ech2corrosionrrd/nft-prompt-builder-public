"""Повна генерація колекції: чекпоінти, batch-зображення з бюджетом, збірний експорт."""

import asyncio
import base64
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from openai import AsyncOpenAI

from batch import (
    CONCURRENT_REQUESTS,
    DEFAULT_CHUNK_SIZE,
    _ANTHROPIC_AVAILABLE,
    assign_chunk_positions,
    generate_chunk,
    add_rarity_scores,
    add_rarity_ranks,
    is_claude_model,
    strip_platform_flags,
)
from storage import DATA_DIR, safe_name

CHECKPOINTS_DIR = DATA_DIR / "checkpoints"
IMAGES_BASE_DIR = DATA_DIR / "images"
EXPORTS_DIR = DATA_DIR / "exports"
IMAGE_CONCURRENCY = 2

# USD за одне зображення gpt-image-1
IMAGE_COSTS: dict[str, dict[str, float]] = {
    "low": {"1024x1024": 0.011, "1536x1024": 0.016, "1024x1536": 0.016},
    "medium": {"1024x1024": 0.042, "1536x1024": 0.063, "1024x1536": 0.063},
    "high": {"1024x1024": 0.167, "1536x1024": 0.25, "1024x1536": 0.25},
}


def image_cost(quality: str, size: str) -> float:
    return IMAGE_COSTS.get(quality, {}).get(size, 0.05)


def image_size_for_aspect(aspect_ratio: str) -> str:
    """Розмір gpt-image-1, що відповідає aspect ratio з Конструктора."""
    if "16:9" in aspect_ratio:
        return "1536x1024"
    if any(ratio in aspect_ratio for ratio in ("4:5", "9:16", "3:4")):
        return "1024x1536"
    return "1024x1024"


# ── Чекпоінти ─────────────────────────────────────────────────────────────────

def checkpoint_path(name: str) -> Path:
    return CHECKPOINTS_DIR / f"{safe_name(name)}.json"


def list_checkpoints() -> list[str]:
    if not CHECKPOINTS_DIR.exists():
        return []
    return sorted(p.stem for p in CHECKPOINTS_DIR.glob("*.json"))


def load_checkpoint(name: str) -> dict | None:
    path = checkpoint_path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_checkpoint(cp: dict) -> None:
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path(cp["name"]).write_text(
        json.dumps(cp, ensure_ascii=False), encoding="utf-8"
    )


def delete_checkpoint(name: str) -> None:
    path = checkpoint_path(name)
    if path.exists():
        path.unlink()


def create_checkpoint(
    name: str,
    target: int,
    model: str,
    platform: str,
    base: dict,
    tech_params: str,
    combos: list[dict[str, str]],
) -> dict:
    cp = {
        "name": safe_name(name),
        "created": datetime.now().isoformat(timespec="seconds"),
        "target": target,
        "model": model,
        "platform": platform,
        "base": base,
        "tech_params": tech_params,
        "combos": combos,
        "results": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0},
    }
    save_checkpoint(cp)
    return cp


def pending_combos(cp: dict) -> list[tuple[int, dict[str, str]]]:
    """Комбінації (token_id, traits), для яких ще немає промтів."""
    done_ids = {r["id"] for r in cp["results"]}
    return [
        (i + 1, combo)
        for i, combo in enumerate(cp["combos"])
        if (i + 1) not in done_ids
    ]


# ── Генерація промтів із чекпоінтами ─────────────────────────────────────────

async def run_collection_async(
    api_key: str,
    cp: dict,
    temperature: float,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Догенеровує відсутні промти, зберігаючи чекпоінт після кожного блоку."""
    pending = pending_combos(cp)
    if not pending:
        return cp

    chunks = [pending[i: i + chunk_size] for i in range(0, len(pending), chunk_size)]
    if is_claude_model(cp["model"]):
        if not _ANTHROPIC_AVAILABLE:
            raise ImportError("Пакет anthropic не встановлено. Запустіть: pip install anthropic")
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
    else:
        client = AsyncOpenAI(api_key=api_key)
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async def run_chunk(chunk: list[tuple[int, dict[str, str]]]):
        ids = [tid for tid, _ in chunk]
        combos = [combo for _, combo in chunk]
        items, usage = await generate_chunk(
            client, cp["model"], cp["platform"], cp["base"],
            combos, cp["tech_params"], temperature, semaphore,
        )
        return ids, combos, items, usage

    try:
        tasks = [asyncio.create_task(run_chunk(c)) for c in chunks]
        for fut in asyncio.as_completed(tasks):
            ids, combos, items, usage = await fut
            for pos, item in assign_chunk_positions(items, len(ids)):
                row = {
                    "id": ids[pos - 1],
                    "traits": combos[pos - 1],
                    "prompt": item.get("prompt", ""),
                    "negative": item.get("negative", ""),
                }
                if item.get("attributes"):
                    row["attributes"] = item["attributes"]
                cp["results"].append(row)
            if usage:
                cp["usage"]["prompt_tokens"] += usage.prompt_tokens
                cp["usage"]["completion_tokens"] += usage.completion_tokens
            save_checkpoint(cp)
            if on_progress:
                on_progress(len(cp["results"]), cp["target"])
    finally:
        await client.close()

    cp["results"].sort(key=lambda r: r["id"])
    add_rarity_scores(cp["results"])
    if len(cp["results"]) > 1:
        add_rarity_ranks(cp["results"])
    save_checkpoint(cp)
    return cp


# ── Batch-зображення ──────────────────────────────────────────────────────────

def images_dir(name: str) -> Path:
    return IMAGES_BASE_DIR / safe_name(name)


def existing_image_ids(name: str) -> set[int]:
    folder = images_dir(name)
    if not folder.exists():
        return set()
    ids = set()
    for path in folder.glob("*.png"):
        try:
            ids.add(int(path.stem))
        except ValueError:
            continue
    return ids


async def generate_images_async(
    api_key: str,
    name: str,
    rows: list[dict],
    size: str = "1024x1024",
    quality: str = "medium",
    budget_usd: float = 0.0,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Генерує зображення для токенів без наявного файлу (чекпоінт = файлова система).

    budget_usd > 0 обмежує кількість зображень за оцінкою вартості.
    Повертає підсумок: generated/failed/skipped_existing/spent/errors.
    """
    out_dir = images_dir(name)
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = existing_image_ids(name)

    todo = [r for r in rows if r.get("id") not in existing and r.get("prompt")]
    skipped = len(rows) - len(todo)
    per_image = image_cost(quality, size)
    if budget_usd > 0:
        todo = todo[: int(budget_usd / per_image)]

    client = AsyncOpenAI(api_key=api_key)
    semaphore = asyncio.Semaphore(IMAGE_CONCURRENCY)
    generated, failed = 0, 0
    errors: list[str] = []

    async def gen(row: dict) -> None:
        async with semaphore:
            response = await client.images.generate(
                model="gpt-image-1",
                prompt=strip_platform_flags(row["prompt"]),
                size=size,
                quality=quality,
                n=1,
            )
            image_bytes = base64.b64decode(response.data[0].b64_json)
            (out_dir / f"{row['id']}.png").write_bytes(image_bytes)

    try:
        tasks = [asyncio.create_task(gen(r)) for r in todo]
        done = 0
        for fut in asyncio.as_completed(tasks):
            try:
                await fut
                generated += 1
            except Exception as err:
                failed += 1
                if len(errors) < 3:
                    errors.append(str(err))
            done += 1
            if on_progress:
                on_progress(done, len(tasks))
    finally:
        await client.close()

    return {
        "generated": generated,
        "failed": failed,
        "skipped_existing": skipped,
        "spent": round(generated * per_image, 4),
        "errors": errors,
    }


# ── Збірний експорт ───────────────────────────────────────────────────────────

def build_collection_zip(
    name: str,
    results: list[dict],
    metadata: list[dict],
    csv_text: str,
) -> Path:
    """ZIP на диску: images/ + metadata/ + collection.json + prompts.csv."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = EXPORTS_DIR / f"{safe_name(name)}.zip"
    img_dir = images_dir(name)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("prompts.csv", csv_text)
        zf.writestr("collection.json", json.dumps(
            [{k: v for k, v in m.items() if k != "token_id"} for m in metadata],
            ensure_ascii=False, indent=2,
        ))
        for row, meta in zip(results, metadata):
            clean = {k: v for k, v in meta.items() if k != "token_id"}
            zf.writestr(f"metadata/{row['id']}.json", json.dumps(clean, ensure_ascii=False, indent=2))
        if img_dir.exists():
            for row in results:
                img_path = img_dir / f"{row['id']}.png"
                if img_path.exists():
                    zf.write(img_path, f"images/{row['id']}.png")
    return zip_path
