"""Інтеграція якості в pipeline (ПЛАН_ЯКОСТІ.md § Q1.1 + Q1.5).

Перевіряє, що профіль якості додає суфікс до промпту генерації та записує
negative/seed/polish_history у запис зображення; без профілю — поведінка
конвеєра незмінна.
"""

import pytest

import network_config
from services import payment_service, pipeline_batch
from services.ai_service import ENGINE_FLUX
from services.prompt_quality import PromptQualityProfile
from services.prompt_service import PromptObject

EVM = "0x" + "a" * 40


class _FakeService:
    """Мінімальний двигун: фіксує промпт і negative, повертає PNG-байти."""

    def __init__(self):
        self.calls: list[str] = []
        self.negatives: list[str] = []
        self.finals: list[bool] = []
        self.seeds: list = []

    def generate_image(self, prompt, engine, width=1024, height=1024, negative_prompt="", final=False, seed=None):
        self.calls.append(prompt)
        self.negatives.append(negative_prompt)
        self.finals.append(final)
        self.seeds.append(seed)
        return b"\x89PNG\r\n"

    def generate_image_cascade(self, prompt, engine, width=1024, height=1024, negative_prompt="", final=False, seed=None):
        # Каскад вимкнено в тестах → поводимось як один обраний двигун.
        img = self.generate_image(prompt, engine, width, height, negative_prompt, final, seed)
        return img, engine


@pytest.fixture
def ready_wallet(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(network_config, "TEMP_ASSETS_DIR", tmp_path / "temp_assets")
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")
    payment_service.complete_wallet_sign_in(EVM)  # verified + welcome
    payment_service.grant_credits(EVM, 50, note="test")
    return EVM


def test_to_dict_includes_quality_keys():
    d = PromptObject("fox", negative="ugly", seed=42, polish_history=["v1"]).to_dict()
    assert d["negative"] == "ugly"
    assert d["seed"] == 42
    assert d["polish_history"] == ["v1"]


def test_to_dict_quality_defaults():
    d = PromptObject("fox").to_dict()
    assert d["negative"] == ""
    assert d["seed"] is None
    assert d["polish_history"] == []
    assert d["version"] == 1


def test_generate_one_without_profile_unchanged(ready_wallet):
    service = _FakeService()
    item = {"prompt": "cyber fox --ar 1:1", "traits": {}}
    rec, err = pipeline_batch._generate_one(
        service, item, ENGINE_FLUX, 1024, 1024, ready_wallet,
    )
    assert err is None
    # MJ-теги прибрано, суфікс НЕ додано (профілю немає), negative порожній.
    assert service.calls == ["cyber fox"]
    assert rec["prompt"] == "cyber fox"
    assert rec["negative"] == ""


def test_failed_generation_releases_freemium_slot(ready_wallet, monkeypatch):
    """Невдала генерація зображення: кредити повертаються І freemium-слот звільняється."""
    from services import ai_service, freemium

    monkeypatch.setenv("FREEMIUM_DAILY_LIMIT", "5")
    service = _FakeService()

    def boom(prompt, engine, *a, **k):
        raise ai_service.AIServiceError("provider down")

    service.generate_image_cascade = boom
    before = payment_service.get_balance(ready_wallet)
    rec, err = pipeline_batch._generate_one(
        service, {"prompt": "fox", "traits": {}}, ENGINE_FLUX, 1024, 1024, ready_wallet,
    )
    assert rec is None and err
    assert payment_service.get_balance(ready_wallet) == before   # кредити повернено
    assert freemium.usage_today(ready_wallet) == 0               # слот не спалено


def test_cascade_reconciles_credits_to_used_engine(ready_wallet):
    """B2: каскад перемкнувся на дешевший двигун → списано за фактичний, не зарезервований."""
    from services.ai_service import ENGINE_FLUX, ENGINE_GPT_IMAGE

    service = _FakeService()

    def switched(prompt, engine, width=1024, height=1024, negative_prompt="", final=False, seed=None):
        # обрали дорогий GPT_IMAGE (4 кр.), але згенерував дешевший FLUX (1 кр.)
        return service.generate_image(prompt, ENGINE_FLUX, width, height, negative_prompt, final, seed), ENGINE_FLUX

    service.generate_image_cascade = switched
    before = payment_service.get_balance(ready_wallet)
    rec, err = pipeline_batch._generate_one(
        service, {"prompt": "fox", "traits": {}}, ENGINE_GPT_IMAGE, 1024, 1024, ready_wallet,
    )
    assert err is None
    # зарезервували credit_cost(GPT_IMAGE)=4, повернули різницю → нетто = credit_cost(FLUX)=1
    spent = before - payment_service.get_balance(ready_wallet)
    assert spent == payment_service.credit_cost(ENGINE_FLUX)
    assert rec["engine"] == ENGINE_FLUX  # у записі — двигун, що реально згенерував


def test_generate_one_with_profile_adds_suffix_and_negative(ready_wallet):
    service = _FakeService()
    profile = PromptQualityProfile(suffix_preset="pfp", use_negative=True)
    item = {"prompt": "cyber fox --ar 1:1", "traits": {}}
    rec, err = pipeline_batch._generate_one(
        service, item, ENGINE_FLUX, 1024, 1024, ready_wallet, profile=profile,
    )
    assert err is None
    assert service.calls[0].startswith("cyber fox, ")
    assert "centered composition" in service.calls[0]
    assert rec["prompt"] == service.calls[0]
    assert "watermark" in rec["negative"]
    # Q1.2: negative прокидається у виклик двигуна.
    assert service.negatives[0] == rec["negative"]


def test_hybrid_tier_first_n_are_final(ready_wallet):
    """Hybrid: перші hybrid_final_n зображень — Final, решта — Draft (Q1.3)."""
    service = _FakeService()
    profile = PromptQualityProfile(quality_tier="hybrid", hybrid_final_n=2)
    prompts = [{"prompt": f"p{i}", "traits": {}} for i in range(4)]
    generated, errors = pipeline_batch.run_parallel_batch(
        service, prompts, ENGINE_FLUX, "Квадрат", ready_wallet, profile=profile,
    )
    assert errors == []
    # Порядок викликів недетермінований (пул), тож звіряємо за tier у записах.
    tiers = sorted(g["quality_tier"] for g in generated)
    assert tiers == ["draft", "draft", "final", "final"]


def test_seed_from_item_passed_and_recorded(ready_wallet):
    """Q3.0: seed з промпту йде у двигун і зберігається в записі."""
    service = _FakeService()
    item = {"prompt": "fox", "traits": {}, "seed": 777}
    rec, err = pipeline_batch._generate_one(
        service, item, ENGINE_FLUX, 1024, 1024, ready_wallet,
    )
    assert err is None
    assert service.seeds == [777]
    assert rec["seed"] == 777


def test_assign_seeds_deterministic():
    from services import prompt_service
    prompts = [{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}]
    out = prompt_service.assign_seeds(prompts, 100)
    assert [p["seed"] for p in out] == [100, 101, 102]
    assert prompts[0].get("seed") is None  # вхід не мутовано


def test_run_parallel_batch_threads_profile(ready_wallet):
    service = _FakeService()
    profile = PromptQualityProfile(suffix_preset="pfp", use_negative=True)
    prompts = [{"prompt": "fox", "traits": {}}, {"prompt": "owl", "traits": {}}]
    generated, errors = pipeline_batch.run_parallel_batch(
        service, prompts, ENGINE_FLUX, "Квадрат", ready_wallet, profile=profile,
    )
    assert errors == []
    assert len(generated) == 2
    assert all("centered composition" in g["prompt"] for g in generated)
    assert all(g["negative"] for g in generated)


def test_run_parallel_batch_waits_between_rate_waves(tmp_path, monkeypatch):
    """Welcome-only: партія > rate-limit чекає між хвилями."""
    from datetime import datetime, timedelta, timezone

    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(network_config, "TEMP_ASSETS_DIR", tmp_path / "temp_assets")
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")
    payment_service.complete_wallet_sign_in(EVM)
    payment_service.add_credits(EVM, 50)
    service = _FakeService()
    rate = payment_service._configured_generation_rate_limit()
    n = rate + 5
    prompts = [{"prompt": f"p{i}", "traits": {}} for i in range(n)]
    waits: list[str] = []

    def _wait(wallet: str, *args, **kwargs) -> bool:
        waits.append(wallet)
        old = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        with payment_service._connect() as conn, conn:
            conn.execute(
                "UPDATE transactions SET created_at = ?"
                " WHERE wallet_address = ? AND kind = 'debit'",
                (old, payment_service.normalize_wallet(wallet)),
            )
        return True

    monkeypatch.setattr(payment_service, "wait_for_generation_rate", _wait)
    generated, errors = pipeline_batch.run_parallel_batch(
        service, prompts, ENGINE_FLUX, "Квадрат", EVM,
    )
    assert errors == []
    assert len(generated) == n
    assert len(waits) == 1
