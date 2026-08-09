"""ШІ-сервіси конвеєра: мультидвигунна генерація зображень (Етап 2)
та Image-to-Prompt (Етап 1).

AIService — незалежний сервіс із єдиним методом generate_image(prompt, engine,
width, height), що повертає PNG-байти. Двигуни: OpenAI (gpt-image-1; DALL-E 2/3
вилучено з API 2026-05-12 → зводяться до gpt-image-1 через normalize_engine),
Stability AI (Stable Image Core, REST) та Flux.1 (Replicate HTTP API, REPLICATE_API_TOKEN).
Ключі читаються зі змінних середовища або st.secrets.

Пакетну чергу (послідовний цикл із прогрес-баром) веде UI-шар;
збереження результатів на диск — network_config.save_temp_asset.
"""

import base64
import json
import os
import re
import threading
import time

import httpx
from openai import OpenAI

from services.prompt_service import PromptObject
from secrets_env import get_secret

# ── Двигуни та розміри ────────────────────────────────────────────────────────

ENGINE_DALLE3 = "OpenAI DALL-E 3"  # ВИВЕДЕНО: OpenAI прибрала dall-e-2/3 з API 2026-05-12
ENGINE_GPT_IMAGE = "OpenAI gpt-image-1"
ENGINE_STABILITY = "Stability AI (Core / SD3)"
ENGINE_FLUX = "Flux.1 (Replicate)"
# DALL-E 3 більше НЕ в списку доступних: модель вилучено з OpenAI Images API
# (2026-05-12). Її роль для OpenAI-генерації покриває gpt-image-1. Константа й
# історичні ціни лишаються для звітів за старими списаннями та міграції сесій.
ENGINES = [ENGINE_GPT_IMAGE, ENGINE_STABILITY, ENGINE_FLUX]

# B2 — порядок каскадного fallback (ПЛАН_ЗАПОЗИЧЕНЬ.md): від найвищої якості до
# найдешевшого. Якщо обраний користувачем двигун недоступний/падає — пробуємо
# наступний ГОТОВИЙ двигун із цього переліку. DALL-E 3 не включено (вилучено з API).
ENGINE_CASCADE = [ENGINE_GPT_IMAGE, ENGINE_STABILITY, ENGINE_FLUX]


def cascade_enabled() -> bool:
    """Каскадний fallback вмикається рівно `IMAGE_CASCADE_ENABLED=1` (default off).

    Вимкнено за замовчуванням, щоб не міняти поведінку/вартість без явної згоди:
    при падінні провайдера каскад може згенерувати ІНШИМ (можливо дорожчим) двигуном.
    """
    return os.environ.get("IMAGE_CASCADE_ENABLED") == "1"


# Двигуни OpenAI, вилучені з API 2026-05-12 — зводимо до gpt-image-1.
_RETIRED_ENGINES = {ENGINE_DALLE3, "OpenAI DALL-E 2", "dall-e-3", "dall-e-2"}


def normalize_engine(engine: str) -> str:
    """Зводить ВИЛУЧЕНИЙ двигун (DALL-E 2/3) до gpt-image-1; решту лишає як є.

    Захищає старі сесії, збережені проєкти та pipeline-стан, де ще лежить
    'OpenAI DALL-E 3' — інакше генерація впала б із 'model does not exist'.
    Невідомі (типографічні) двигуни НЕ маскуємо — хай далі дають ValueError.
    """
    return ENGINE_GPT_IMAGE if engine in _RETIRED_ENGINES else engine

# Орієнтація → (width, height)
SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "Квадрат": (1024, 1024),
    "Портрет": (1024, 1536),
    "Альбом": (1536, 1024),
}

# Орієнтовна вартість одного зображення, $ (square, portrait/landscape)
_ENGINE_COSTS: dict[str, tuple[float, float]] = {
    ENGINE_GPT_IMAGE: (0.042, 0.063),
    ENGINE_STABILITY: (0.030, 0.030),
    ENGINE_FLUX: (0.003, 0.003),
}

STABILITY_URL = "https://api.stability.ai/v2beta/stable-image/generate/core"
FLUX_MODEL = "black-forest-labs/flux-schnell"


def flux_model(final: bool = False) -> str:
    """Модель Flux за рівнем якості: Draft=schnell, Final=flux-dev (env-перевизначна).

    `or default`, а не `get(key, default)`: порожнє значення в env (`FLUX_MODEL_FINAL=`)
    робить ключ присутнім зі значенням "", тож `get` віддав би "" замість дефолту →
    Final-Flux отримав би порожній слаг і впав. `or` трактує і відсутній, і порожній
    ключ як дефолт.
    """
    if final:
        return os.environ.get("FLUX_MODEL_FINAL") or "black-forest-labs/flux-dev"
    return os.environ.get("FLUX_MODEL") or FLUX_MODEL


# Якість OpenAI за рівнем (ПЛАН_ЯКОСТІ.md § Q1.3): Draft → дешевше, Final → вище.
_GPT_IMAGE_QUALITY = {False: "medium", True: "high"}

GENERATE_TIMEOUT = 180.0
REPLICATE_API = "https://api.replicate.com/v1"
IMAGE_RETRIES = 4          # достатньо, щоб пережити вікно rate-limit (honor retry-after)
RETRY_BACKOFF_SEC = 1.5
RETRY_MAX_SLEEP_SEC = 20.0  # стеля паузи на один retry (захист від хибної величезної підказки)

# OpenAI gpt-image-1: org-ліміт «5 input-images/хв» на низьких тарифах. Темпуємо
# виклики проактивно (1 на 60/N с), щоб не ловити 429 на паралельному батчі.
# 0 → троттл вимкнено. Інші двигуни (Stability/Flux) мають вищі ліміти й не темпуються.
def gpt_image_min_interval() -> float:
    """Мінімальний інтервал між викликами gpt-image-1 (с) з GPT_IMAGE_MAX_PER_MIN."""
    raw = os.environ.get("GPT_IMAGE_MAX_PER_MIN", "5")
    try:
        per_min = float(raw)
    except ValueError:
        per_min = 5.0
    return 60.0 / per_min if per_min > 0 else 0.0


class _RateLimiter:
    """Потокобезпечний інтервальний троттл: гарантує ≥ min_interval між acquire().

    Спільний на всі ThreadPool-воркери батчу, тож сумарний темп викликів двигуна
    не перевищує 60/min_interval за хвилину (без 429 від провайдера).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def acquire(self, min_interval: float) -> None:
        if min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
                now = time.monotonic()
            self._next_allowed = now + min_interval


_GPT_IMAGE_LIMITER = _RateLimiter()

_RETRY_AFTER_RE = re.compile(r"try again in\s+([\d.]+)\s*(ms|s)\b", re.IGNORECASE)


def _retry_after_seconds(error: Exception) -> float | None:
    """Витягує підказку «try again in Ns / Nms» з тексту 429 (None, якщо немає)."""
    m = _RETRY_AFTER_RE.search(str(error))
    if not m:
        return None
    value = float(m.group(1))
    return value / 1000.0 if m.group(2).lower() == "ms" else value


class AIServiceError(RuntimeError):
    """Зрозуміла помилка генерації (недійсний ключ, ліміти, мережа) — без падіння додатка."""


def estimate_cost(engine: str, orientation: str) -> float:
    square, wide = _ENGINE_COSTS.get(engine, (0.05, 0.08))
    return square if orientation == "Квадрат" else wide


def closest_aspect(width: int, height: int) -> str:
    """Маппінг розміру на aspect ratio для Stability/Flux."""
    if width > height:
        return "16:9"
    if height > width:
        return "9:16"
    return "1:1"


def dalle_size(width: int, height: int) -> str:
    """Допустимі розміри DALL-E 3: 1024x1024, 1792x1024, 1024x1792."""
    if width > height:
        return "1792x1024"
    if height > width:
        return "1024x1792"
    return "1024x1024"


def gpt_image_size(width: int, height: int) -> str:
    """Допустимі розміри gpt-image-1: 1024x1024, 1536x1024, 1024x1536."""
    if width > height:
        return "1536x1024"
    if height > width:
        return "1024x1536"
    return "1024x1024"


def _read_key(name: str) -> str | None:
    """Ключ з .env / os.environ / st.secrets."""
    return get_secret(name)


# Вичерпаний білінг провайдера теж приходить як 429 (OpenAI: «You exceeded your
# current quota…»), але це не тимчасова помилка — повтори лише марно тримають
# користувача в очікуванні й довбають чужий API. Одиноке «quota» сюди НЕ беремо:
# воно буває і в rate-limit («quota exceeded for requests per minute»), який
# ретраїти якраз треба.
_PERMANENT_MARKERS = (
    "insufficient",
    "billing",
    "exceeded your current quota",
    "spend limit",
    "payment required",
)


def _is_retryable(error: Exception) -> bool:
    text = str(error).lower()
    if any(x in text for x in _PERMANENT_MARKERS):
        return False
    return any(x in text for x in ("429", "rate limit", "timeout", "503", "502", "temporarily"))


def is_moderation_blocked(error: Exception) -> bool:
    """Чи помилка — блок модерації провайдера (output/input), не технічний збій."""
    return _is_moderation_blocked(error)


def _is_moderation_blocked(error: Exception) -> bool:
    """Output/input moderation від OpenAI тощо — retry марний, потрібен інший двигун."""
    text = str(error).lower()
    return any(x in text for x in (
        "moderation_blocked", "safety system", "content_policy",
        "content policy", "rejected by the safety", "moderation_details",
    ))


def _friendly_error(engine: str, error: Exception) -> str:
    text = str(error).lower()
    if _is_moderation_blocked(error):
        return (
            f"{engine}: відхилено модерацією провайдера (зображення). "
            f"Regenerate з Flux/Stability або змініть промпт. ({error})"
        )
    if "429" in text or "rate limit" in text or "quota" in text or "insufficient" in text:
        return f"{engine}: ліміти API вичерпано або недостатньо кредитів. ({error})"
    if "401" in text or "403" in text or "invalid api key" in text or "unauthorized" in text or "authentication" in text:
        return f"{engine}: API-ключ недійсний або не має доступу. ({error})"
    return f"{engine}: {error}"


def _replicate_run(model: str, model_input: dict, token: str):
    """Запуск моделі Replicate через REST (httpx; без SDK replicate — сумісно з Python 3.14+)."""
    auth = {"Authorization": f"Token {token}"}
    headers = {**auth, "Content-Type": "application/json", "Prefer": "wait=60"}
    create = httpx.post(
        f"{REPLICATE_API}/models/{model}/predictions",
        headers=headers,
        json={"input": model_input},
        timeout=GENERATE_TIMEOUT,
    )
    if create.status_code >= 400:
        raise AIServiceError(_friendly_error(
            ENGINE_FLUX, RuntimeError(f"HTTP {create.status_code}: {create.text[:200]}"),
        ))
    data = create.json()
    status = data.get("status")
    poll_url = (data.get("urls") or {}).get("get")
    while status in ("starting", "processing") and poll_url:
        time.sleep(1.0)
        poll = httpx.get(poll_url, headers=auth, timeout=30.0)
        if poll.status_code >= 400:
            raise AIServiceError(_friendly_error(
                ENGINE_FLUX, RuntimeError(f"HTTP {poll.status_code}: {poll.text[:200]}"),
            ))
        data = poll.json()
        status = data.get("status")
    if status != "succeeded":
        detail = data.get("error") or status or "unknown"
        raise AIServiceError(f"Flux.1 (Replicate): {detail}")
    return data.get("output")


class AIService:
    """Універсальний генератор зображень для трьох платформ."""

    def __init__(
        self,
        openai_key: str | None = None,
        stability_key: str | None = None,
        replicate_token: str | None = None,
    ):
        self.openai_key = openai_key or _read_key("OPENAI_API_KEY")
        self.stability_key = stability_key or _read_key("STABILITY_API_KEY")
        self.replicate_token = replicate_token or _read_key("REPLICATE_API_TOKEN")

    def engine_status(self) -> dict[str, str]:
        """Для кожного двигуна: '' якщо готовий, інакше — що бракує."""
        return {
            ENGINE_GPT_IMAGE: "" if self.openai_key else "потрібен OPENAI_API_KEY",
            ENGINE_STABILITY: "" if self.stability_key else "потрібен STABILITY_API_KEY",
            ENGINE_FLUX: "" if self.replicate_token else "потрібен REPLICATE_API_TOKEN",
        }

    def generate_image(
        self, prompt: str, engine: str, width: int = 1024, height: int = 1024,
        negative_prompt: str = "", final: bool = False, seed: int | None = None,
    ) -> bytes:
        """Єдина точка входу: генерує зображення обраним двигуном, повертає PNG-байти.

        negative_prompt застосовується лише двигунами з нативною підтримкою
        (наразі Stability AI); OpenAI/Flux-schnell його не мають і тихо ігнорують.
        final=True вмикає вищий рівень якості (Q1.3): DALL-E hd, gpt-image high,
        Flux flux-dev. Вартість у кредитах рахує payment_service.credit_cost(engine, final).
        seed (Q3.0) фіксує генерацію для відтворюваності: Stability/Flux приймають
        його нативно; OpenAI seed не підтримує і ігнорує.
        """
        return self._run_engine(
            normalize_engine(engine), prompt, width, height, negative_prompt, final, seed,
        )

    def _run_engine(
        self, engine: str, prompt: str, width: int, height: int,
        negative_prompt: str, final: bool, seed: int | None,
    ) -> bytes:
        """Один двигун із ретраями. Падіння → AIServiceError (термінально для двигуна)."""
        handlers = {
            ENGINE_GPT_IMAGE: self._generate_gpt_image,
            ENGINE_STABILITY: self._generate_stability,
            ENGINE_FLUX: self._generate_flux,
        }
        handler = handlers.get(engine)
        if handler is None:
            raise ValueError(f"Невідомий двигун: {engine}. Доступні: {', '.join(ENGINES)}")
        last_err: Exception | None = None
        for attempt in range(IMAGE_RETRIES + 1):
            try:
                return handler(prompt, width, height, negative_prompt, final, seed)
            except Exception as e:
                last_err = e
                # AIServiceError теж ретраїмо, якщо помилка тимчасова. Раніше вона
                # йшла повз ретраї (`except AIServiceError: raise`), а Stability/Flux
                # обгортають HTTP-відповідь у AIServiceError ЩЕ ДО цього циклу —
                # тож 429/502/503 від них не переживали жодної спроби, і
                # IMAGE_RETRIES працював лише для двигунів із «сирими» винятками
                # (OpenAI SDK). Наслідок у проді: Flux падав на 27.7% генерацій
                # проти 0.3% у gpt-image-1 (той має ще й проактивний троттл).
                if (
                    attempt < IMAGE_RETRIES
                    and _is_retryable(e)
                    and not _is_moderation_blocked(e)
                ):
                    # Поважаємо явну підказку провайдера («try again in Ns»); інакше
                    # лінійний backoff. Стеля — щоб хибна величезна величина не зависла.
                    hint = _retry_after_seconds(e)
                    delay = hint if hint is not None else RETRY_BACKOFF_SEC * (attempt + 1)
                    time.sleep(min(delay, RETRY_MAX_SLEEP_SEC))
                    continue
                # Готове повідомлення двигуна не переобгортаємо (не дублюємо префікс).
                if isinstance(e, AIServiceError):
                    raise
                raise AIServiceError(_friendly_error(engine, e)) from e
        raise AIServiceError(_friendly_error(engine, last_err or RuntimeError("unknown")))

    def cascade_chain(self, requested: str) -> list[str]:
        """B2: порядок двигунів для спроби. Голова — обраний користувачем; хвіст —
        решта ГОТОВИХ двигунів із ENGINE_CASCADE (engine_status == ''). Без каскаду —
        лише обраний двигун."""
        requested = normalize_engine(requested)
        if not cascade_enabled():
            return [requested]
        status = self.engine_status()
        chain = [requested]
        for e in ENGINE_CASCADE:
            if e != requested and status.get(e, "n/a") == "":
                chain.append(e)
        return chain

    def generate_image_cascade(
        self, prompt: str, engine: str, width: int = 1024, height: int = 1024,
        negative_prompt: str = "", final: bool = False, seed: int | None = None,
    ) -> tuple[bytes, str]:
        """Як generate_image, але з B2-каскадом. Повертає (PNG-байти, двигун-що-спрацював).

        Перебирає cascade_chain: перший успіх повертається разом із фактичним двигуном
        (важливо для білінгу — списати за той, що згенерував). Усі впали → AIServiceError.

        Якщо IMAGE_CASCADE вимкнено, але OpenAI (або інший) відхилив output-moderation —
        одноразово пробуємо інші готові двигуни (Flux/Stability), щоб не втрачати кадр.
        """
        chain = self.cascade_chain(engine)
        status = self.engine_status()
        tried: set[str] = set()
        last_err: Exception | None = None
        moderation_hit = False

        def _try(eng: str) -> tuple[bytes, str]:
            return self._run_engine(eng, prompt, width, height, negative_prompt, final, seed), eng

        for eng in chain:
            tried.add(eng)
            try:
                return _try(eng)
            except AIServiceError as e:
                last_err = e
                if _is_moderation_blocked(e):
                    moderation_hit = True
                continue

        if moderation_hit and not cascade_enabled():
            for eng in ENGINE_CASCADE:
                if eng in tried or status.get(eng, "n/a") != "":
                    continue
                tried.add(eng)
                try:
                    return _try(eng)
                except AIServiceError as e:
                    last_err = e
                    continue

        raise AIServiceError(str(last_err) if last_err else "усі двигуни недоступні")

    # ── OpenAI ──
    def _require_openai(self) -> str:
        if not self.openai_key:
            raise AIServiceError("OpenAI: API-ключ не знайдено (OPENAI_API_KEY або бічна панель).")
        return self.openai_key

    def _generate_gpt_image(self, prompt: str, width: int, height: int, negative_prompt: str = "", final: bool = False, seed: int | None = None) -> bytes:
        client = OpenAI(api_key=self._require_openai())
        # Проактивний троттл під org-ліміт gpt-image-1 (5/хв) — спільний на всі
        # воркери батчу, тож паралельна черга не вистрілює 429 (на відміну від
        # самого лише retry, що не встигав за вікном ліміту).
        _GPT_IMAGE_LIMITER.acquire(gpt_image_min_interval())
        response = client.images.generate(
            model="gpt-image-1", prompt=prompt, size=gpt_image_size(width, height),
            quality=_GPT_IMAGE_QUALITY[final], n=1,
        )
        return self._openai_image_bytes(response.data[0])

    @staticmethod
    def _openai_image_bytes(item) -> bytes:
        """Байти зображення з елемента відповіді OpenAI Images, незалежно від формату.

        Ендпоінт більше не приймає response_format: gpt-image-1 завжди повертає
        b64_json, а dall-e-3 — URL. Підтримуємо обидва: b64 декодуємо, інакше
        завантажуємо за url.
        """
        b64 = getattr(item, "b64_json", None)
        if b64:
            return base64.b64decode(b64)
        url = getattr(item, "url", None)
        if url:
            resp = httpx.get(url, timeout=GENERATE_TIMEOUT)
            resp.raise_for_status()
            return resp.content
        raise AIServiceError("OpenAI: відповідь без зображення (немає b64_json/url).")

    # ── Stability AI (REST) ──
    def _generate_stability(self, prompt: str, width: int, height: int, negative_prompt: str = "", final: bool = False, seed: int | None = None) -> bytes:
        # Stability Core не має tier-параметра якості; final поки не диференціюється
        # (майбутній SD3-ендпоінт — Q3). negative_prompt і seed підтримуються нативно.
        if not self.stability_key:
            raise AIServiceError("Stability AI: API-ключ не знайдено (STABILITY_API_KEY).")
        data = {
            "prompt": prompt,
            "output_format": "png",
            "aspect_ratio": closest_aspect(width, height),
        }
        if negative_prompt.strip():
            data["negative_prompt"] = negative_prompt.strip()
        if seed is not None:
            data["seed"] = int(seed)
        response = httpx.post(
            STABILITY_URL,
            headers={"Authorization": f"Bearer {self.stability_key}", "Accept": "image/*"},
            files={"none": ""},  # API вимагає multipart/form-data
            data=data,
            timeout=GENERATE_TIMEOUT,
        )
        if response.status_code != 200:
            raise AIServiceError(_friendly_error(
                ENGINE_STABILITY, RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}"),
            ))
        return response.content

    # ── Flux.1 (Replicate) ──
    def _generate_flux(self, prompt: str, width: int, height: int, negative_prompt: str = "", final: bool = False, seed: int | None = None) -> bytes:
        # flux-schnell не приймає negative_prompt — ігноруємо. Final-tier обирає
        # flux-dev (вищі деталі); модель — flux_model(final), env FLUX_MODEL_FINAL.
        # seed (Q3.0) підтримується нативно для відтворюваності.
        if not self.replicate_token:
            raise AIServiceError("Flux.1: API-токен не знайдено (REPLICATE_API_TOKEN).")
        flux_input = {"prompt": prompt, "aspect_ratio": closest_aspect(width, height), "output_format": "png"}
        if seed is not None:
            flux_input["seed"] = int(seed)
        output = _replicate_run(flux_model(final), flux_input, self.replicate_token)
        first = output[0] if isinstance(output, (list, tuple)) else output
        url = str(first)
        download = httpx.get(url, timeout=GENERATE_TIMEOUT)
        download.raise_for_status()
        return download.content


# ── Етап 1: Image-to-Prompt (зворотний інжиніринг) ────────────────────────────

VISION_MODEL = "gpt-4o-mini"
VISION_MODEL_DETAILED = "gpt-4o"  # детальніший аналіз (Q3.3)


def vision_model(detailed: bool = False) -> str:
    """Vision-модель для Image-to-Prompt: швидка gpt-4o-mini або детальна gpt-4o."""
    return VISION_MODEL_DETAILED if detailed else VISION_MODEL


VISION_SYSTEM_PROMPT = (
    "You are a reverse prompt engineer. Analyze the image and reconstruct a generation "
    "prompt formula for it. Respond with JSON only, in English, with exactly these keys: "
    '"core" (string: the main subject/character), '
    '"style" (string: visual style/art direction), '
    '"details" (array of strings: lighting, camera angle, colors, notable details), '
    '"tags" (string: technical engine tags like aspect ratio, may be empty).'
)


def parse_prompt_formula(raw_json: str) -> dict:
    """Розбирає JSON-відповідь vision-моделі у словник, сумісний із Етапом 1.

    Толерантний до часткових відповідей: відсутні ключі → порожні значення.
    Кидає ValueError, якщо це не JSON-об'єкт або немає core.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Модель повернула некоректний JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Модель повернула не JSON-об'єкт.")

    core = str(data.get("core", "")).strip()
    if not core:
        raise ValueError("У відповіді моделі відсутній головний об'єкт (core).")

    details_raw = data.get("details", [])
    if isinstance(details_raw, str):
        details_raw = [details_raw]
    details = [str(d).strip() for d in details_raw if str(d).strip()]

    return PromptObject(
        core=core,
        style=str(data.get("style", "")).strip(),
        details=details,
        tags=str(data.get("tags", "")).strip(),
    ).to_dict()


def image_to_prompt(api_key: str, image_bytes: bytes, mime: str = "image/png", detailed: bool = False) -> dict:
    """Завантажена картинка → структурована формула промпту (core/style/details/tags).

    detailed=True (Q3.3) використовує детальнішу vision-модель (gpt-4o).
    """
    client = OpenAI(api_key=api_key)
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    response = client.chat.completions.create(
        model=vision_model(detailed),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Reconstruct the prompt formula for this image."},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    )
    return parse_prompt_formula(response.choices[0].message.content or "")
