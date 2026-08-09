"""B1 — Content-safety блоклист перед генерацією (ПЛАН_ЗАПОЗИЧЕНЬ.md).

Чиста функція без Streamlit: `check_prompt_safety(text, lang) -> SafetyResult`.
Застосунок публічний (SIWE = єдиний периметр), тож промпти треба фільтрувати
ДО будь-якого платного виклику AI. Фільтр навмисно вузький — блокує лише
очевидно недопустимий контент (сексуалізація неповнолітніх, сексуальне
насильство), щоб не давати хибних спрацювань на звичайних креативних промптах.

Прапорець `CONTENT_SAFETY_ENABLED`: фільтр **увімкнено за замовчуванням** і
вимикається рівно значенням `"0"` (як `WELCOME_REQUIRE_BALANCE`) — для safety-
функції на публічному сайті безпечний дефолт = «ввімкнено».

Landmine: НЕ логувати сам заблокований текст у відкритий лог (тільки категорію).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import requests

from secrets_env import get_secret

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyResult:
    """Результат перевірки промпту. ok=True — пропустити; інакше code/category."""

    ok: bool
    code: str = ""        # машинний код для UI-перекладу (error.blocked_prompt.*)
    category: str = ""    # внутрішня категорія для логів/метрик (без тексту промпту)


# ── Патерни (вузькі, з межами слів) ───────────────────────────────────────────
# Підхід: для CSAM вимагаємо ОДНОЧАСНО маркер неповнолітнього І сексуальний
# маркер — це різко знижує хибні спрацювання (саме слово «child» не блокується).
# Плюс кілька самодостатніх однозначних фраз. Двомовно (uk+en), бо промпти
# вводять і англійською, і українською.

_MINOR_TERMS = re.compile(
    r"\b("
    r"child|children|childlike|kid|kiddo|toddler|infant|baby|preteen|pre-teen|"
    r"tween|teen|teenage|teenager|adolescent|minor|underage|juvenile|schoolgirl|"
    r"schoolboy|loli|lolicon|shota"
    r"|дитин\w*|дитя\w*|дітей|малюк\w*|немовл\w*|підліт\w*|неповнолітн\w*|"
    r"малолітн\w*|школярк\w*|школяр\w*"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

_SEXUAL_TERMS = re.compile(
    r"\b("
    r"nude|naked|nsfw|porn\w*|pornographic|sex|sexual|sexy|erotic\w*|explicit|"
    r"hentai|fellatio|genital\w*|nipple\w*|undress\w*|lingerie|seductive|aroused"
    r"|оголен\w*|голий|гола|голе|порно\w*|секс\w*|еротич\w*|еротик\w*|"
    r"інтимн\w*|статев\w*|збуджен\w*"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

# Однозначні фрази — блокують самі по собі (без потреби в парі маркерів).
_EXPLICIT_CSAM = re.compile(
    r"\b("
    r"child\s*porn\w*|child\s*sex\w*|cp\s*porn|pedophil\w*|paedophil\w*|"
    r"underage\s*(sex|porn|nude)|csam|child\s*abuse"
    r"|дитяч\w*\s*порно\w*|педофіл\w*|розбещення\s*неповнолітн\w*"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

_SEXUAL_VIOLENCE = re.compile(
    r"\b("
    r"rape|raping|gang\s*rape|non-?consensual|forced\s*sex|sexual\s*assault"
    r"|зґвалтув\w*|згвалтув\w*|зґвалт\w*|сексуальн\w*\s*насил\w*|"
    r"насильн\w*\s*статев\w*"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)


def enabled() -> bool:
    """Фільтр увімкнено за замовчуванням; вимикається рівно `CONTENT_SAFETY_ENABLED=0`."""
    return os.environ.get("CONTENT_SAFETY_ENABLED", "1") != "0"


# ── Другий ешелон: OpenAI Moderation API (opt-in) ─────────────────────────────
# Regex вище — безкоштовний перший ешелон, але його легко обійти обфускацією
# (leetspeak `ch1ld`, дефіси `c-h-i-l-d`) чи іншими мовами (застосунок публічний,
# міжнародний). Moderation API розпізнає контекст багатьма мовами. Вмикається
# рівно `MODERATION_API_ENABLED=1` (opt-in, як решта abuse-прапорців) і використовує
# наявний `OPENAI_API_KEY`. **fail-open**: відсутній ключ чи будь-який мережевий
# збій НЕ блокує генерацію — regex уже зловив найгірше беззастережно, а падати на
# технічній помилці провайдера = карати легітимного користувача. Блокуємо ЛИШЕ
# найвищу-шкоду категорію `sexual/minors` — це дзеркалить вузький намір фільтра й
# майже не дає хибних спрацювань на легітимному арті (класична оголена статуя
# лишається ok, бо це категорія `sexual`, а не `sexual/minors`).
_MODERATION_URL = "https://api.openai.com/v1/moderations"
_MODERATION_MODEL = "omni-moderation-latest"
# Таймаут на виклик модерації. fail-open, тож при деградації провайдера кожен
# потік генерації чекав би саме стільки — тримаємо низьким (Moderation зазвичай
# <1с). Env-керований для тонкого налаштування на проді.
_MODERATION_TIMEOUT = float(os.environ.get("MODERATION_API_TIMEOUT") or "3.0")
# api-категорія OpenAI → (код повідомлення, внутрішня категорія для логів/метрик)
_MODERATION_BLOCK_MAP: dict[str, tuple[str, str]] = {
    "sexual/minors": ("error.blocked_prompt.csam", "csam_moderation"),
}


def moderation_enabled() -> bool:
    """Другий ешелон (Moderation API) — opt-in, вмикається рівно `MODERATION_API_ENABLED=1`."""
    return os.environ.get("MODERATION_API_ENABLED") == "1"


def _moderation_check(text: str) -> SafetyResult | None:
    """Другий ешелон: OpenAI Moderation API. **fail-open** (None = не змогли перевірити).

    - SafetyResult(False, ...) — API впевнено позначив заборонену категорію;
    - SafetyResult(True)       — API перевірив і пропустив;
    - None                     — немає ключа або будь-який мережевий/парсинг-збій
      (рішення лишається за regex — не блокуємо генерацію на технічній помилці).
    """
    key = get_secret("OPENAI_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            _MODERATION_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": _MODERATION_MODEL, "input": text},
            timeout=_MODERATION_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        if not results:
            return SafetyResult(True)
        categories = results[0].get("categories") or {}
        for api_cat, (code, category) in _MODERATION_BLOCK_MAP.items():
            if categories.get(api_cat):
                return SafetyResult(False, code=code, category=category)
        return SafetyResult(True)
    except Exception as e:  # навмисно широкий except — fail-open на будь-який збій
        logger.warning("content_safety: Moderation API недоступне, fail-open (%s)", type(e).__name__)
        return None


def check_prompt_safety(text: str, lang: str = "uk") -> SafetyResult:
    """Перевіряє промпт на недопустимий контент. Повертає SafetyResult.

    Порожній текст і вимкнений фільтр завжди ok=True. `lang` зарезервовано для
    майбутніх мовоспецифічних патернів; наразі патерни двомовні.
    """
    if not enabled():
        return SafetyResult(True)
    body = (text or "").strip()
    if not body:
        return SafetyResult(True)

    if _EXPLICIT_CSAM.search(body) or (_MINOR_TERMS.search(body) and _SEXUAL_TERMS.search(body)):
        return SafetyResult(False, code="error.blocked_prompt.csam", category="csam")
    if _SEXUAL_VIOLENCE.search(body):
        return SafetyResult(False, code="error.blocked_prompt.violence", category="sexual_violence")

    # Другий ешелон (opt-in): контекстна модерація ловить обфускацію/інші мови, що
    # проходять regex. fail-open — None не блокує; блок лише при впевненому вердикті.
    if moderation_enabled():
        mod = _moderation_check(body)
        if mod is not None and not mod.ok:
            return mod

    return SafetyResult(True)


# Двомовні повідомлення (self-contained — сервіс не імпортує ui_strings, бо той
# тягне Streamlit). UI може використати або ці рядки, або власні t()-ключі.
_MESSAGES: dict[str, dict[str, str]] = {
    "error.blocked_prompt.csam": {
        "uk": "Промпт відхилено: контент із сексуалізацією неповнолітніх заборонено.",
        "en": "Prompt rejected: sexual content involving minors is prohibited.",
    },
    "error.blocked_prompt.violence": {
        "uk": "Промпт відхилено: сексуальне насильство заборонено.",
        "en": "Prompt rejected: sexual violence is prohibited.",
    },
    "error.blocked_prompt": {
        "uk": "Промпт відхилено модерацією контенту.",
        "en": "Prompt rejected by content moderation.",
    },
}


def message(result: SafetyResult, lang: str = "uk") -> str:
    """Людиночитане двомовне повідомлення за результатом (для не-UI шляхів)."""
    block = _MESSAGES.get(result.code) or _MESSAGES["error.blocked_prompt"]
    return block.get(lang) or block["uk"]


def log_safety(result: SafetyResult) -> None:
    """Лог факту блокування — ЛИШЕ категорія, без тексту промпту (landmine)."""
    if not result.ok:
        logger.warning("content_safety: заблоковано промпт, категорія=%s", result.category)
