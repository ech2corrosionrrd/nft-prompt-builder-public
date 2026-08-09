"""Пакетна генерація зображень конвеєра (паралельно, A/B)."""

from __future__ import annotations

import concurrent.futures
import threading
from datetime import datetime, timezone
from typing import Callable

from pathlib import Path

import network_config
from batch import strip_platform_flags
from metadata_provenance import add_rarity_ranks
from services import ai_service, content_safety, freemium, payment_service, prompt_enhancer
from services.ai_service import AIService, AIServiceError
from services.prompt_quality import PromptQualityProfile

PARALLEL_WORKERS = 3

_WALLET_GEN_LOCKS: dict[str, threading.Lock] = {}
_WALLET_GEN_LOCKS_GUARD = threading.Lock()


def _generation_lock(wallet: str) -> threading.Lock:
    wallet = payment_service.normalize_wallet(wallet)
    with _WALLET_GEN_LOCKS_GUARD:
        if wallet not in _WALLET_GEN_LOCKS:
            _WALLET_GEN_LOCKS[wallet] = threading.Lock()
        return _WALLET_GEN_LOCKS[wallet]


def _make_image_record(
    item: dict, engine: str, path: str, ab_label: str = "",
    prompt: str | None = None, negative: str = "", final: bool = False,
) -> dict:
    rec = {
        "prompt": prompt if prompt is not None else item["prompt"],
        "traits": item.get("traits", {}),
        "style": item.get("style", ""),
        "engine": engine,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "model_version": engine,
        "rarity_score": item.get("rarity_score"),
        "path": str(path),
        "filename": path.name if hasattr(path, "name") else str(path).split("/")[-1],
        # Якість (Q1.5): negative/seed/історія зберігаються в записі зображення.
        "negative": negative or item.get("negative", ""),
        "seed": item.get("seed"),
        "polish_history": list(item.get("polish_history", [])),
        "quality_tier": "final" if final else "draft",
    }
    if ab_label:
        rec["ab_variant"] = ab_label
    return rec


def _reconcile_cost(wallet: str, reserved: int, used_engine: str, final: bool) -> None:
    """B2: вирівнює списання під двигун, що фактично згенерував (caскад перемкнувся).

    Зарезервували `reserved` кредитів за обраний двигун; фактичний коштує інакше:
    дешевший → повертаємо різницю; дорожчий → доплачуємо best-effort (зображення
    вже згенеровано, тож недоплату лишаємо, не скасовуючи результат)."""
    actual = payment_service.credit_cost(used_engine, final)
    if actual < reserved:
        payment_service.refund_credits(
            wallet, reserved - actual, engine=used_engine, note="cascade: переплату повернено",
        )
    elif actual > reserved:
        payment_service.deduct_credits(
            wallet, actual - reserved, engine=used_engine, note="cascade: доплата за двигун",
        )


def _save_image_bytes(image_bytes: bytes, project_assets_dir: Path | None) -> Path:
    if project_assets_dir is not None:
        from services import project_service
        return project_service.write_asset(project_assets_dir, image_bytes)
    return network_config.save_temp_asset(image_bytes)


def _generate_one(
    service: AIService,
    item: dict,
    engine: str,
    width: int,
    height: int,
    wallet: str,
    ab_label: str = "",
    profile: PromptQualityProfile | None = None,
    final: bool = False,
    project_assets_dir: Path | None = None,
) -> tuple[dict | None, str | None]:
    per_image_credits = payment_service.credit_cost(engine, final)
    # B1: content-safety ДО будь-якого платного виклику — відсіюємо недопустимий
    # промпт без списання кредитів і без звернення до AI-провайдера.
    safety = content_safety.check_prompt_safety(item.get("prompt", ""))
    if not safety.ok:
        content_safety.log_safety(safety)
        return None, content_safety.message(safety)
    with _generation_lock(wallet):
        rate_lim = payment_service.generation_rate_limit_per_minute(wallet)
        if rate_lim is not None and not payment_service.check_generation_rate(wallet, rate_lim):
            return None, f"перевищено ліміт генерацій ({rate_lim}/хв)"
        # B3: денна стеля лише для вітальних 5 cr без топ-апу. Поповнені звільнені;
        allowed, _ = freemium.check_available(wallet)
        if not allowed:
            return None, "перевищено денний ліміт безкоштовних генерацій"
        # Резервуємо кредити ДО платного виклику AI (атомарно): паралельні воркери
        # не зможуть перевитратити API-бюджет понад наявний баланс (без TOCTOU).
        if not payment_service.deduct_credits(
            wallet, per_image_credits, engine=engine, note="image generation",
        ):
            if not payment_service.is_wallet_verified(wallet):
                return None, "гаманець не підтверджено підписом"
            return None, "кредити вичерпано"
        freemium.record_generation(wallet)
    try:
        # Суфікс якості додаємо ПІСЛЯ strip_platform_flags (landmine: інакше
        # MJ-теги опиняться всередині промпту). Без профілю — поведінка незмінна.
        clean_prompt = strip_platform_flags(item["prompt"])
        positive, negative = prompt_enhancer.enhance(
            clean_prompt, profile, item_negative=item.get("negative", ""),
        )
        # B2: каскадний fallback. used_engine — двигун, що реально згенерував
        # (== engine, якщо каскад вимкнено або не довелося перемикатись).
        image_bytes, used_engine = service.generate_image_cascade(
            positive, engine, width, height, negative_prompt=negative, final=final,
            seed=item.get("seed"),
        )
        # Звіряємо кредити з фактичним двигуном: каскад міг перемкнутись на дешевший
        # (повертаємо різницю) або дорожчий (доплата best-effort — зображення вже є).
        if used_engine != engine:
            _reconcile_cost(wallet, per_image_credits, used_engine, final)
        path = _save_image_bytes(image_bytes, project_assets_dir)
        return _make_image_record(
            item, used_engine, path, ab_label, prompt=positive, negative=negative, final=final,
        ), None
    except AIServiceError as e:
        payment_service.refund_credits(wallet, per_image_credits, engine=engine, note="refund: generation failed")
        freemium.release_generation(wallet)  # невдала генерація не палить денний слот
        return None, str(e)
    except Exception as e:
        payment_service.refund_credits(wallet, per_image_credits, engine=engine, note="refund: generation failed")
        freemium.release_generation(wallet)
        return None, str(e)


def regenerate_one(
    service: AIService,
    item: dict,
    engine: str,
    orientation: str,
    wallet: str,
    profile: PromptQualityProfile | None = None,
    final: bool = False,
    project_assets_dir: Path | None = None,
) -> tuple[dict | None, str | None]:
    """Перегенерувати один кадр (куратор «Regenerate»)."""
    width, height = ai_service.SIZE_PRESETS[orientation]
    return _generate_one(
        service, item, engine, width, height, wallet, profile=profile, final=final,
        project_assets_dir=project_assets_dir,
    )


def run_parallel_batch(
    service: AIService,
    prompts: list[dict],
    engine: str,
    orientation: str,
    wallet: str,
    on_progress: Callable[[int, int], None] | None = None,
    profile: PromptQualityProfile | None = None,
    project_assets_dir: Path | None = None,
) -> tuple[list[dict], list[str]]:
    """Паралельна черга (до PARALLEL_WORKERS одночасно), хвилями по rate-limit."""
    width, height = ai_service.SIZE_PRESETS[orientation]
    generated: list[dict] = []
    errors: list[str] = []
    total = len(prompts)
    done = 0
    rate = payment_service.generation_rate_limit_per_minute(wallet)

    def task(args: tuple[int, dict]) -> tuple[int, dict | None, str | None]:
        idx, item = args
        final = profile.is_final_index(idx) if profile else False
        rec, err = _generate_one(
            service, item, engine, width, height, wallet, profile=profile, final=final,
            project_assets_dir=project_assets_dir,
        )
        return idx, rec, err

    def run_wave(wave: list[tuple[int, dict]]) -> None:
        nonlocal done
        with concurrent.futures.ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
            futures = [pool.submit(task, args) for args in wave]
            for fut in concurrent.futures.as_completed(futures):
                idx, rec, err = fut.result()
                done += 1
                if on_progress:
                    on_progress(done, total)
                if rec:
                    generated.append(rec)
                elif err:
                    errors.append(f"#{idx + 1}: {err}")

    indexed = list(enumerate(prompts))
    if rate is None:
        run_wave(indexed)
    else:
        for wave_start in range(0, total, rate):
            if wave_start > 0:
                if not payment_service.wait_for_generation_rate(wallet, rate):
                    for idx, _ in indexed[wave_start:]:
                        errors.append(f"#{idx + 1}: перевищено ліміт генерацій ({rate}/хв)")
                    break
            run_wave(indexed[wave_start:wave_start + rate])
    if len(generated) > 1:
        add_rarity_ranks(generated)
    return generated, errors


def run_ab_compare(
    service: AIService,
    item: dict,
    engine_a: str,
    engine_b: str,
    orientation: str,
    wallet: str,
    profile: PromptQualityProfile | None = None,
    project_assets_dir: Path | None = None,
) -> tuple[list[dict], list[str]]:
    """A/B: один промпт — два двигуни для порівняння."""
    width, height = ai_service.SIZE_PRESETS[orientation]
    out, errors = [], []
    final = profile.is_final_index(0) if profile else False
    for label, eng in (("A", engine_a), ("B", engine_b)):
        rec, err = _generate_one(
            service, item, eng, width, height, wallet, ab_label=label, profile=profile, final=final,
            project_assets_dir=project_assets_dir,
        )
        if rec:
            out.append(rec)
        elif err:
            errors.append(f"{label} ({eng}): {err}")
    return out, errors


def matrix_trait_distribution(categories: dict[str, list[str]]) -> list[dict]:
    """Очікуваний % появи кожного trait у декартовому добутку."""
    if not categories:
        return []
    total = 1
    for values in categories.values():
        total *= max(len(values), 1)
    rows = []
    for cat, values in categories.items():
        share = total // max(len(values), 1)
        for val in values:
            rows.append({
                "Категорія": cat,
                "Trait": val,
                "Очікувано %": round(100 * share / total, 1),
            })
    return rows
