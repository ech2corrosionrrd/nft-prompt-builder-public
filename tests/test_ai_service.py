"""Тести AIService: розбір відповіді OpenAI Images (b64_json або url)."""

import base64
import time

import pytest

import services.ai_service as ai_service
from services.ai_service import AIService, AIServiceError


class _Item:
    """Імітація елемента response.data[0] від OpenAI Images."""

    def __init__(self, b64=None, url=None):
        self.b64_json = b64
        self.url = url


def test_image_bytes_from_b64():
    raw = b"\x89PNG\r\n fake bytes"
    item = _Item(b64=base64.b64encode(raw).decode())
    assert AIService._openai_image_bytes(item) == raw


def test_image_bytes_from_url(monkeypatch):
    """dall-e-3 без response_format віддає URL → завантажуємо вміст."""
    raw = b"downloaded-image-bytes"

    class _Resp:
        content = raw

        def raise_for_status(self):
            pass

    monkeypatch.setattr(ai_service.httpx, "get", lambda *a, **k: _Resp())
    item = _Item(url="https://example.com/img.png")
    assert AIService._openai_image_bytes(item) == raw


def test_image_bytes_missing_raises():
    with pytest.raises(AIServiceError):
        AIService._openai_image_bytes(_Item())  # ні b64, ні url


# ── Q1.2: negative_prompt у двигунах ──────────────────────────────────────────

class _StabResp:
    status_code = 200
    content = b"png-bytes"
    text = ""


def _capture_stability_post(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["data"] = kwargs.get("data", {})
        return _StabResp()

    monkeypatch.setattr(ai_service.httpx, "post", fake_post)
    return captured


def test_stability_includes_negative_prompt(monkeypatch):
    captured = _capture_stability_post(monkeypatch)
    svc = AIService(stability_key="sk-test")
    out = svc.generate_image(
        "cyber fox", ai_service.ENGINE_STABILITY, negative_prompt="blurry, watermark",
    )
    assert out == b"png-bytes"
    assert captured["data"]["negative_prompt"] == "blurry, watermark"


def test_stability_omits_empty_negative(monkeypatch):
    captured = _capture_stability_post(monkeypatch)
    svc = AIService(stability_key="sk-test")
    svc.generate_image("cyber fox", ai_service.ENGINE_STABILITY, negative_prompt="   ")
    assert "negative_prompt" not in captured["data"]


def test_generate_image_accepts_negative_for_all_engines(monkeypatch):
    """OpenAI/Flux мовчки ігнорують negative — сигнатура єдина, без помилки."""
    captured = _capture_stability_post(monkeypatch)
    svc = AIService(stability_key="sk-test")
    # Достатньо переконатися, що виклик зі Stability проходить із negative.
    svc.generate_image("x", ai_service.ENGINE_STABILITY, negative_prompt="ugly")
    assert captured["data"]["negative_prompt"] == "ugly"


# ── Q3.0: seed / reproducibility ──────────────────────────────────────────────

def test_stability_includes_seed(monkeypatch):
    captured = _capture_stability_post(monkeypatch)
    svc = AIService(stability_key="sk-test")
    svc.generate_image("fox", ai_service.ENGINE_STABILITY, seed=12345)
    assert captured["data"]["seed"] == 12345


def test_stability_omits_seed_when_none(monkeypatch):
    captured = _capture_stability_post(monkeypatch)
    svc = AIService(stability_key="sk-test")
    svc.generate_image("fox", ai_service.ENGINE_STABILITY, seed=None)
    assert "seed" not in captured["data"]


def test_flux_via_replicate_http(monkeypatch):
    """Flux.1 без SDK replicate — прямий HTTP до api.replicate.com."""
    posted = {}

    class _CreateResp:
        status_code = 201
        text = ""

        @staticmethod
        def json():
            return {
                "status": "succeeded",
                "output": ["https://replicate.delivery/out.png"],
            }

    class _DownloadResp:
        content = b"flux-png"

        @staticmethod
        def raise_for_status():
            pass

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted["json"] = kwargs.get("json")
        posted["headers"] = kwargs.get("headers")
        return _CreateResp()

    monkeypatch.setattr(ai_service.httpx, "post", fake_post)
    monkeypatch.setattr(ai_service.httpx, "get", lambda *a, **k: _DownloadResp())
    svc = AIService(replicate_token="r8_test")
    out = svc.generate_image("neon cat", ai_service.ENGINE_FLUX, seed=42)
    assert out == b"flux-png"
    assert "black-forest-labs/flux-schnell" in posted["url"]
    assert posted["json"]["input"]["seed"] == 42
    assert posted["headers"]["Authorization"] == "Token r8_test"


def test_flux_requires_token():
    svc = AIService(replicate_token=None)
    with pytest.raises(AIServiceError, match="REPLICATE_API_TOKEN"):
        svc.generate_image("x", ai_service.ENGINE_FLUX)


def test_flux_model_empty_env_falls_back_to_default(monkeypatch):
    """Пастка `FLUX_MODEL_FINAL=` (присутній, але порожній): має дати дефолт, не ""."""
    monkeypatch.setenv("FLUX_MODEL_FINAL", "")
    monkeypatch.setenv("FLUX_MODEL", "")
    assert ai_service.flux_model(final=True) == "black-forest-labs/flux-dev"
    assert ai_service.flux_model(final=False) == ai_service.FLUX_MODEL


def test_flux_model_absent_env_uses_default(monkeypatch):
    monkeypatch.delenv("FLUX_MODEL_FINAL", raising=False)
    monkeypatch.delenv("FLUX_MODEL", raising=False)
    assert ai_service.flux_model(final=True) == "black-forest-labs/flux-dev"
    assert ai_service.flux_model(final=False) == "black-forest-labs/flux-schnell"


def test_flux_model_explicit_env_overrides(monkeypatch):
    monkeypatch.setenv("FLUX_MODEL_FINAL", "black-forest-labs/flux-1.1-pro")
    assert ai_service.flux_model(final=True) == "black-forest-labs/flux-1.1-pro"


# ── B2: каскадний fallback між провайдерами ───────────────────────────────────

def _svc_all_ready():
    """AIService з ключами для всіх трьох двигунів (engine_status усі готові)."""
    svc = AIService(openai_key="sk-o", stability_key="sk-s", replicate_token="r-t")
    return svc


def test_cascade_disabled_by_default(monkeypatch):
    monkeypatch.delenv("IMAGE_CASCADE_ENABLED", raising=False)
    assert ai_service.cascade_enabled() is False
    svc = _svc_all_ready()
    # без каскаду chain = лише обраний двигун
    assert svc.cascade_chain(ai_service.ENGINE_STABILITY) == [ai_service.ENGINE_STABILITY]


def test_cascade_chain_head_then_ready_tail(monkeypatch):
    monkeypatch.setenv("IMAGE_CASCADE_ENABLED", "1")
    svc = _svc_all_ready()
    chain = svc.cascade_chain(ai_service.ENGINE_STABILITY)
    status = svc.engine_status()
    # голова — обраний; у хвості — лише ГОТОВІ двигуни (status == ''), без дублю голови
    assert chain[0] == ai_service.ENGINE_STABILITY
    assert chain.count(ai_service.ENGINE_STABILITY) == 1
    assert all(status.get(e) == "" for e in chain[1:])
    # GPT_IMAGE готовий (є openai_key) → має бути у хвості
    assert ai_service.ENGINE_GPT_IMAGE in chain[1:]


def test_cascade_skips_unavailable_engine(monkeypatch):
    monkeypatch.setenv("IMAGE_CASCADE_ENABLED", "1")
    # лише Stability готовий (нема OpenAI/Replicate ключів)
    svc = AIService(openai_key=None, stability_key="sk-s", replicate_token=None)
    chain = svc.cascade_chain(ai_service.ENGINE_GPT_IMAGE)
    # голова — обраний (навіть якщо не готовий), але недоступні в хвіст не потрапляють
    assert chain[0] == ai_service.ENGINE_GPT_IMAGE
    assert chain[1:] == [ai_service.ENGINE_STABILITY]


def test_cascade_first_fails_second_succeeds(monkeypatch):
    monkeypatch.setenv("IMAGE_CASCADE_ENABLED", "1")
    svc = _svc_all_ready()

    def fake_run(engine, *a, **k):
        if engine == ai_service.ENGINE_GPT_IMAGE:
            raise AIServiceError("gpt-image down (503)")
        return b"img-from-" + engine.encode("utf-8")[:4]

    monkeypatch.setattr(svc, "_run_engine", fake_run)
    img, used = svc.generate_image_cascade("fox", ai_service.ENGINE_GPT_IMAGE)
    assert used == ai_service.ENGINE_STABILITY  # перемкнулись на наступний готовий
    assert img.startswith(b"img-from-")


def test_cascade_all_fail_raises(monkeypatch):
    monkeypatch.setenv("IMAGE_CASCADE_ENABLED", "1")
    svc = _svc_all_ready()
    monkeypatch.setattr(
        svc, "_run_engine",
        lambda *a, **k: (_ for _ in ()).throw(AIServiceError("down")),
    )
    with pytest.raises(AIServiceError):
        svc.generate_image_cascade("fox", ai_service.ENGINE_GPT_IMAGE)


def test_cascade_off_uses_only_requested(monkeypatch):
    monkeypatch.delenv("IMAGE_CASCADE_ENABLED", raising=False)
    svc = _svc_all_ready()
    calls = []

    def fake_run(engine, *a, **k):
        calls.append(engine)
        raise AIServiceError("down")

    monkeypatch.setattr(svc, "_run_engine", fake_run)
    with pytest.raises(AIServiceError):
        svc.generate_image_cascade("fox", ai_service.ENGINE_GPT_IMAGE)
    assert calls == [ai_service.ENGINE_GPT_IMAGE]  # без fallback на інші


def test_cascade_off_moderation_tries_other_engines(monkeypatch):
    monkeypatch.delenv("IMAGE_CASCADE_ENABLED", raising=False)
    svc = _svc_all_ready()
    mod_err = AIServiceError(
        "OpenAI gpt-image-1: Error code: 400 - moderation_blocked safety system"
    )

    def fake_run(engine, *a, **k):
        if engine == ai_service.ENGINE_GPT_IMAGE:
            raise mod_err
        return b"img-from-" + engine.encode("utf-8")[:4]

    monkeypatch.setattr(svc, "_run_engine", fake_run)
    img, used = svc.generate_image_cascade("fox", ai_service.ENGINE_GPT_IMAGE)
    assert used == ai_service.ENGINE_STABILITY
    assert img.startswith(b"img-from-")


def test_is_moderation_blocked_openai_output():
    err = Exception(
        "Error code: 400 - moderation_blocked rejected by the safety system"
    )
    assert ai_service.is_moderation_blocked(err) is True
    assert ai_service.is_moderation_blocked(Exception("503 temporarily unavailable")) is False


def test_friendly_error_moderation():
    err = Exception("moderation_blocked safety system")
    msg = ai_service._friendly_error(ai_service.ENGINE_GPT_IMAGE, err)
    assert "модерацією" in msg
    assert "Flux/Stability" in msg


# ── Q3.3: vision-модель для Image-to-Prompt ───────────────────────────────────

def test_vision_model_toggle():
    assert ai_service.vision_model(False) == ai_service.VISION_MODEL
    assert ai_service.vision_model(True) == ai_service.VISION_MODEL_DETAILED
    assert ai_service.vision_model(True) == "gpt-4o"


# ── Rate-limit стабільність: throttle + honor retry-after (OpenAI 429) ─────────

def test_retry_after_seconds_parses_hint():
    """Підказку «try again in Ns / Nms» із 429 беремо як паузу."""
    real = (
        "Error code: 429 - {'error': {'message': 'Rate limit reached for gpt-image-1 "
        "... on input-images per min: Limit 5, Used 5, Requested 1. "
        "Please try again in 12s. Visit https://...'}}"
    )
    assert ai_service._retry_after_seconds(RuntimeError(real)) == 12.0
    assert ai_service._retry_after_seconds(RuntimeError("try again in 800ms")) == 0.8
    assert ai_service._retry_after_seconds(RuntimeError("no hint")) is None


def test_gpt_image_min_interval_from_env(monkeypatch):
    monkeypatch.delenv("GPT_IMAGE_MAX_PER_MIN", raising=False)
    assert ai_service.gpt_image_min_interval() == 12.0   # дефолт 5/хв
    monkeypatch.setenv("GPT_IMAGE_MAX_PER_MIN", "10")
    assert ai_service.gpt_image_min_interval() == 6.0
    monkeypatch.setenv("GPT_IMAGE_MAX_PER_MIN", "0")     # 0 → троттл вимкнено
    assert ai_service.gpt_image_min_interval() == 0.0
    monkeypatch.setenv("GPT_IMAGE_MAX_PER_MIN", "bad")   # сміття → дефолт
    assert ai_service.gpt_image_min_interval() == 12.0


def test_rate_limiter_spaces_calls():
    """Перший acquire без паузи; другий чекає ~min_interval."""
    lim = ai_service._RateLimiter()
    t0 = time.monotonic()
    lim.acquire(0.05)
    lim.acquire(0.05)
    assert time.monotonic() - t0 >= 0.045
    # min_interval<=0 → миттєво (троттл вимкнено)
    lim0 = ai_service._RateLimiter()
    t1 = time.monotonic()
    lim0.acquire(0)
    lim0.acquire(0)
    assert time.monotonic() - t1 < 0.02


def test_run_engine_retries_then_succeeds_honoring_hint(monkeypatch):
    """429 двічі → retry поважає «12s» → 3-я спроба успішна, без AIServiceError."""
    svc = AIService(openai_key="sk-o")
    slept: list[float] = []
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def flaky(prompt, width, height, negative_prompt="", final=False, seed=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("Error code: 429 - rate limit. Please try again in 12s.")
        return b"PNG-OK"

    monkeypatch.setattr(svc, "_generate_gpt_image", flaky)
    out = svc.generate_image("fox", ai_service.ENGINE_GPT_IMAGE)
    assert out == b"PNG-OK"
    assert calls["n"] == 3
    assert slept == [12.0, 12.0]  # обидва retry за підказкою (під стелею 20s)


# ── Ретраї для двигунів, що самі обгортають HTTP у AIServiceError ─────────────
# Stability/Flux формують AIServiceError ще до _run_engine (з тексту HTTP-відповіді).
# Раніше така помилка йшла повз ретраї — тимчасові 429/503 від них падали з першої
# спроби (у проді Flux: 27.7% провалів проти 0.3% у gpt-image-1).

def test_run_engine_retries_wrapped_ai_error(monkeypatch):
    """AIServiceError із тимчасовим HTTP (503) ретраїться так само, як «сирий» виняток."""
    svc = AIService(replicate_token="r8-token")
    slept: list[float] = []
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def flaky(prompt, width, height, negative_prompt="", final=False, seed=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise AIServiceError("Flux.1 (Replicate): HTTP 503: upstream unavailable")
        return b"PNG-OK"

    monkeypatch.setattr(svc, "_generate_flux", flaky)
    assert svc.generate_image("fox", ai_service.ENGINE_FLUX) == b"PNG-OK"
    assert calls["n"] == 3
    assert slept == [1.5, 3.0]  # лінійний backoff: підказки «try again» немає


def test_run_engine_does_not_retry_fatal_ai_error(monkeypatch):
    """Недійсний ключ — не тимчасова помилка: жодного ретраю, повідомлення без дублю префікса."""
    svc = AIService(stability_key="sk-s")
    slept: list[float] = []
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def fatal(prompt, width, height, negative_prompt="", final=False, seed=None):
        calls["n"] += 1
        raise AIServiceError("Stability AI (Core / SD3): API-ключ недійсний або не має доступу. (HTTP 401)")

    monkeypatch.setattr(svc, "_generate_stability", fatal)
    with pytest.raises(AIServiceError) as exc:
        svc.generate_image("fox", ai_service.ENGINE_STABILITY)
    assert calls["n"] == 1
    assert slept == []
    # Готове повідомлення двигуна не переобгортається другим префіксом.
    assert str(exc.value).count("Stability AI (Core / SD3)") == 1


def test_run_engine_does_not_retry_moderation_block(monkeypatch):
    """Блок модерації — retry марний навіть якщо текст містить ретраябельне слово."""
    svc = AIService(openai_key="sk-o")
    slept: list[float] = []
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def blocked(prompt, width, height, negative_prompt="", final=False, seed=None):
        calls["n"] += 1
        raise AIServiceError("moderation_blocked: rejected by the safety system (timeout hint)")

    monkeypatch.setattr(svc, "_generate_gpt_image", blocked)
    with pytest.raises(AIServiceError):
        svc.generate_image("fox", ai_service.ENGINE_GPT_IMAGE)
    assert calls["n"] == 1
    assert slept == []


def test_exhausted_billing_is_not_retryable():
    """Вичерпаний білінг приходить як 429, але повтори марні — не тимчасова помилка."""
    assert ai_service._is_retryable(RuntimeError("Error code: 429 - rate limit reached")) is True
    assert ai_service._is_retryable(RuntimeError(
        "Error code: 429 - You exceeded your current quota, please check your plan and billing details"
    )) is False
    assert ai_service._is_retryable(RuntimeError("HTTP 402: insufficient_balance")) is False
    assert ai_service._is_retryable(RuntimeError("Monthly spend limit reached")) is False
    # «quota» саме по собі — ще не білінг: у rate-limit воно теж трапляється.
    assert ai_service._is_retryable(RuntimeError("429 quota exceeded for requests per minute")) is True


def test_run_engine_does_not_retry_exhausted_billing(monkeypatch):
    """Провайдер без коштів не отримує 5 марних спроб (і користувач не чекає на них)."""
    svc = AIService(replicate_token="r8-token")
    slept: list[float] = []
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def broke(prompt, width, height, negative_prompt="", final=False, seed=None):
        calls["n"] += 1
        raise AIServiceError(
            "Flux.1 (Replicate): ліміти API вичерпано або недостатньо кредитів. "
            "(HTTP 402: insufficient credit)"
        )

    monkeypatch.setattr(svc, "_generate_flux", broke)
    with pytest.raises(AIServiceError):
        svc.generate_image("fox", ai_service.ENGINE_FLUX)
    assert calls["n"] == 1
    assert slept == []


def test_run_engine_exhausts_retries_and_raises(monkeypatch):
    """Постійний 429 → рівно IMAGE_RETRIES повторів, далі AIServiceError."""
    svc = AIService(replicate_token="r8-token")
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def always_429(prompt, width, height, negative_prompt="", final=False, seed=None):
        calls["n"] += 1
        raise AIServiceError("Flux.1 (Replicate): HTTP 429: rate limit")

    monkeypatch.setattr(svc, "_generate_flux", always_429)
    with pytest.raises(AIServiceError):
        svc.generate_image("fox", ai_service.ENGINE_FLUX)
    assert calls["n"] == ai_service.IMAGE_RETRIES + 1
