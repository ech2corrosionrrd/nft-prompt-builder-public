"""provider_probe.py — чи двигун узагалі ще існує на боці постачальника.

Побратим [provider_health.py](provider_health.py), але вісь відмови інша.
`provider_health` рахує частку збоїв у `transactions` — тобто мовчить, поки
ніхто не генерує. Прод стоїть без трафіку з 19.07.2026, і саме тоді ця
перевірка сліпа: `PROVIDER_MIN_ATTEMPTS=5` не набереться ніколи.

Тут — активна проба: питаємо постачальника напряму, ще до того, як користувач
натисне «Генерувати».

**Чому metadata-запит, а не тестова генерація.** DALL-E 3 помер не тому, що
генерація ламалась — OpenAI **вилучила модель з API** 12.05.2026, і виклик почав
віддавати помилку. Перевірено наживо 08.08.2026:

    GET /v1/models/gpt-image-1  → 200 {"id": "gpt-image-1", ...}
    GET /v1/models/dall-e-3     → 404 "The model 'dall-e-3' does not exist"

Тобто рівно той історичний випадок ловиться **безкоштовним GET-ом**. Щоденна
тестова генерація коштувала б ~$0.10/добу (~$3/міс) і давала б той самий сигнал
про мертву модель — при виторгу $44.93 за весь час це погана угода. Платна
генерація лишається, але **opt-in** (`PROVIDER_PROBE_GENERATE=1`) для глибокої
перевірки раз на N — див. `probe_generation`.

**Класифікація навмисно асиметрична.** 401/403 (ключ мертвий) і 404 (моделі
немає) — це FAIL: стан не самополагодиться, потрібна людина. Таймаут, 5xx і
мережеві помилки — WARN: постачальники моргають, а перевірка ходить раз на добу,
тож ескалювати кожен блимок означає привчити оператора ігнорувати алерти.

Баланс, де постачальник його віддає (Stability), теж сигнал: вичерпаний баланс
приходить як 429, а 429 ретраї не лікують (див. `ai_service._is_retryable`) —
краще дізнатись до того, як користувач упреться.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

# Двигуни називаємо так само, як ai_service.ENGINE_* — щоб алерти обох
# перевірок сходились в одну назву й оператор не звіряв синоніми.
ENGINE_GPT_IMAGE = "OpenAI gpt-image-1"
ENGINE_STABILITY = "Stability AI (Core / SD3)"
ENGINE_FLUX = "Flux.1 (Replicate)"

DEFAULT_TIMEOUT = 15.0

# Поріг «мало кредитів» у Stability. Дефолт низький: це попередження про
# наближення до нуля, а не приводу для паніки.
DEFAULT_MIN_CREDITS = 50.0

# Статуси проби
OK = "ok"
FAIL = "fail"        # ключ/модель — людина потрібна
WARN = "warn"        # тимчасове (таймаут, 5xx) або низький баланс
SKIPPED = "skipped"  # двигун не налаштовано — не наша справа


@dataclass(frozen=True)
class EngineProbe:
    engine: str
    status: str
    detail: str
    balance: float | None = None

    @property
    def failed(self) -> bool:
        return self.status == FAIL


@dataclass(frozen=True)
class ProbeStatus:
    ok: bool
    engines: tuple[EngineProbe, ...]

    @property
    def checked(self) -> bool:
        """Чи була бодай одна реальна проба (не всі skipped)."""
        return any(e.status != SKIPPED for e in self.engines)


def min_credits() -> float:
    raw = os.environ.get("PROVIDER_PROBE_MIN_CREDITS") or ""
    try:
        val = float(raw)
    except ValueError:
        return DEFAULT_MIN_CREDITS
    return val if val >= 0 else DEFAULT_MIN_CREDITS


def probe_enabled() -> bool:
    """Увімкнено за замовчуванням: проби безкоштовні. Вимикач — рівно "0"."""
    return (os.environ.get("PROVIDER_PROBE_ENABLED") or "1") != "0"


def _classify_http(code: int) -> tuple[str, str]:
    if code == 200:
        return OK, "200"
    if code in (401, 403):
        return FAIL, f"{code} — ключ відхилено"
    if code == 404:
        return FAIL, f"{code} — моделі немає в API"
    if code == 429:
        return WARN, f"{code} — ліміт запитів"
    if 500 <= code < 600:
        return WARN, f"{code} — збій на боці постачальника"
    return WARN, str(code)


def _get(url: str, token: str, timeout: float):
    import httpx

    return httpx.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)


# Одна безкоштовна повторна спроба на тимчасовий результат. Спостережено
# 08.08.2026 на проді: `GET /v1/models/gpt-image-1` віддав ReadTimeout, а
# наступні чотири спроби — 200 за 0.4–0.5 с. Без повтору такий блимок щодня
# лишав би в логу WARN-рядок, і оператор звик би його гортати.
PROBE_ATTEMPTS = 2


def _probe_with_retry(url: str, token: str, timeout: float, getter: Callable):
    """(status, detail, resp). Повторюємо лише WARN: FAIL (401/404) остаточний.

    Віддаємо й саму відповідь — щоб той, кому потрібне тіло (баланс Stability),
    не робив другого запиту.
    """
    status = detail = None
    resp = None
    for _ in range(max(1, PROBE_ATTEMPTS)):
        try:
            resp = getter(url, token, timeout)
            status, detail = _classify_http(resp.status_code)
        except Exception as e:  # мережа/таймаут — WARN, не FAIL (див. докстрінг)
            resp, status, detail = None, WARN, f"{type(e).__name__}: {str(e)[:80]}"
        if status != WARN:
            break
    return status, detail, resp


def _probe_simple(engine: str, url: str, token: str, timeout: float, getter: Callable) -> EngineProbe:
    if not token:
        return EngineProbe(engine, SKIPPED, "ключ не задано")
    status, detail, _ = _probe_with_retry(url, token, timeout, getter)
    return EngineProbe(engine, status, detail)


def probe_openai(timeout: float = DEFAULT_TIMEOUT, getter: Callable = _get) -> EngineProbe:
    """Модель має існувати — саме її зникнення вбило DALL-E 3."""
    model = os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-1"
    return _probe_simple(
        ENGINE_GPT_IMAGE,
        f"https://api.openai.com/v1/models/{model}",
        os.environ.get("OPENAI_API_KEY") or "",
        timeout,
        getter,
    )


def probe_flux(timeout: float = DEFAULT_TIMEOUT, getter: Callable = _get) -> EngineProbe:
    model = os.environ.get("FLUX_MODEL") or "black-forest-labs/flux-schnell"
    return _probe_simple(
        ENGINE_FLUX,
        f"https://api.replicate.com/v1/models/{model}",
        os.environ.get("REPLICATE_API_TOKEN") or "",
        timeout,
        getter,
    )


def probe_stability(timeout: float = DEFAULT_TIMEOUT, getter: Callable = _get) -> EngineProbe:
    """Stability не має endpoint'а на модель, зате віддає баланс — а вичерпаний
    баланс приходить як 429, який ретраї не лікують."""
    token = os.environ.get("STABILITY_API_KEY") or ""
    if not token:
        return EngineProbe(ENGINE_STABILITY, SKIPPED, "ключ не задано")
    url = "https://api.stability.ai/v1/user/balance"
    status, detail, resp = _probe_with_retry(url, token, timeout, getter)
    if status != OK:
        return EngineProbe(ENGINE_STABILITY, status, detail)

    try:
        credits = float((resp.json() or {}).get("credits"))
    except Exception:
        return EngineProbe(ENGINE_STABILITY, OK, "200 (баланс не розібрано)")

    floor = min_credits()
    if credits <= 0:
        return EngineProbe(ENGINE_STABILITY, FAIL, "баланс вичерпано", credits)
    if credits < floor:
        return EngineProbe(ENGINE_STABILITY, WARN, f"мало кредитів (<{floor:g})", credits)
    return EngineProbe(ENGINE_STABILITY, OK, "200", credits)


def probe_engines(timeout: float = DEFAULT_TIMEOUT, getter: Callable = _get) -> ProbeStatus:
    """Одна проба на кожен налаштований двигун. Мережа — так, побічних ефектів — ні."""
    if not probe_enabled():
        return ProbeStatus(True, ())
    probes = (
        probe_openai(timeout, getter),
        probe_stability(timeout, getter),
        probe_flux(timeout, getter),
    )
    return ProbeStatus(not any(p.failed for p in probes), probes)


def summary_text(status: ProbeStatus) -> str:
    if not status.engines:
        return "Проба двигунів: вимкнено (PROVIDER_PROBE_ENABLED=0)"
    if not status.checked:
        return "Проба двигунів: жоден не налаштовано"

    marks = {OK: "✅", FAIL: "❌", WARN: "⚠️", SKIPPED: "—"}
    parts = []
    for p in status.engines:
        if p.status == SKIPPED:
            continue
        bal = f", {p.balance:g} кредитів" if p.balance is not None else ""
        parts.append(f"{marks[p.status]} {p.engine}: {p.detail}{bal}")
    head = "Проба двигунів OK" if status.ok else "Проба двигунів: ПРОБЛЕМА"
    return head + " — " + "; ".join(parts)


def probe_generation(engine: str, prompt: str = "a small grey circle on white background") -> EngineProbe:
    """ГЛИБОКА проба: реальна генерація. **Платно** — opt-in, не для щоденного циклу.

    Metadata-проба вище доводить, що ключ і модель живі, але не те, що генерація
    доходить до кінця. Раз на N (тиждень/реліз) це варто перевірити наскрізь;
    щодня — ні, бо ~$0.10/добу проти $44.93 виторгу за весь час.
    """
    import services.ai_service as ai

    svc = ai.AIService()
    try:
        data = svc.generate_image(prompt, engine, width=1024, height=1024)
    except Exception as e:
        return EngineProbe(engine, FAIL, f"{type(e).__name__}: {str(e)[:120]}")
    if not data or len(data) < 10_000:
        return EngineProbe(engine, FAIL, f"підозріло малий результат: {len(data or b'')} байт")
    return EngineProbe(engine, OK, f"{len(data) // 1024} КБ")


def generation_probe_enabled() -> bool:
    """Платна проба — строго opt-in (рівно "1")."""
    return (os.environ.get("PROVIDER_PROBE_GENERATE") or "") == "1"
