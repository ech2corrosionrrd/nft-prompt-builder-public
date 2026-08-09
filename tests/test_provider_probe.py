"""Тести активної проби двигунів (services/provider_probe.py).

Мережу не чіпаємо: `getter` інжектується. Головне, що перевіряємо — асиметрію
класифікації, бо саме вона визначає, коли оператора будять: 401/404 мусять
підіймати алерт (стан не самополагодиться), а таймаут і 5xx — ні (постачальники
моргають, а перевірка ходить раз на добу).
"""

import pytest

from services import provider_probe as pp


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _getter(code, payload=None, record=None):
    def g(url, token, timeout):
        if record is not None:
            record.append((url, token, timeout))
        return _Resp(code, payload)
    return g


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k-openai")
    monkeypatch.setenv("STABILITY_API_KEY", "k-stability")
    monkeypatch.setenv("REPLICATE_API_TOKEN", "k-replicate")


# ── класифікація HTTP ────────────────────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    (200, pp.OK),
    (401, pp.FAIL),   # ключ відкликано — людина потрібна
    (403, pp.FAIL),
    (404, pp.FAIL),   # модель вилучено — саме так помер DALL-E 3
    (429, pp.WARN),
    (500, pp.WARN),
    (503, pp.WARN),   # моргання постачальника не має будити оператора
])
def test_http_classification(code, expected):
    assert pp._classify_http(code)[0] == expected


def test_model_gone_is_fail_not_warn():
    """Регресія історії: DALL-E 3 вилучили з API, і виклик почав давати 404.
    Якщо 404 стане WARN, той самий випадок знову пройде непоміченим."""
    probe = pp.probe_openai(getter=_getter(404))
    assert probe.status == pp.FAIL
    assert probe.failed


def test_transient_error_is_warn_not_fail():
    probe = pp.probe_openai(getter=_getter(503))
    assert probe.status == pp.WARN
    assert not probe.failed


def test_transient_result_is_retried_once():
    """Спостережено в проді: одиничний ReadTimeout серед стабільних 0.4 с.
    Повтор безкоштовний (GET), тож блимок не має лишати WARN у щоденному логу."""
    calls = {"n": 0}

    def flaky(url, token, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("blip")
        return _Resp(200)

    probe = pp.probe_openai(getter=flaky)
    assert calls["n"] == 2
    assert probe.status == pp.OK


def test_definitive_failure_is_not_retried():
    """404 остаточний — повтор його не змінить, а зайвий запит нічого не дає."""
    calls = {"n": 0}

    def gone(url, token, timeout):
        calls["n"] += 1
        return _Resp(404)

    probe = pp.probe_openai(getter=gone)
    assert calls["n"] == 1
    assert probe.status == pp.FAIL


def test_network_exception_is_warn():
    def boom(url, token, timeout):
        raise TimeoutError("network unreachable")
    probe = pp.probe_flux(getter=boom)
    assert probe.status == pp.WARN
    assert not probe.failed


# ── пропуск ненастроєних двигунів ────────────────────────────────────────────

def test_missing_key_is_skipped_not_failure(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    probe = pp.probe_openai(getter=_getter(200))
    assert probe.status == pp.SKIPPED
    assert not probe.failed


def test_skipped_engines_do_not_break_overall_ok(monkeypatch):
    for var in ("OPENAI_API_KEY", "STABILITY_API_KEY", "REPLICATE_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    status = pp.probe_engines(getter=_getter(200))
    assert status.ok
    assert not status.checked


# ── адреси проб ──────────────────────────────────────────────────────────────

def test_openai_probes_configured_model(monkeypatch):
    monkeypatch.setenv("OPENAI_IMAGE_MODEL", "gpt-image-9")
    seen = []
    pp.probe_openai(getter=_getter(200, record=seen))
    assert seen[0][0].endswith("/v1/models/gpt-image-9")


def test_flux_probes_configured_model(monkeypatch):
    monkeypatch.setenv("FLUX_MODEL", "owner/custom-model")
    seen = []
    pp.probe_flux(getter=_getter(200, record=seen))
    assert seen[0][0].endswith("/v1/models/owner/custom-model")


# ── баланс Stability ─────────────────────────────────────────────────────────

def test_stability_healthy_balance():
    probe = pp.probe_stability(getter=_getter(200, {"credits": 4242}))
    assert probe.status == pp.OK
    assert probe.balance == 4242


def test_stability_zero_balance_is_fail():
    """Вичерпаний баланс приходить як 429, а 429 ретраї не лікують — краще
    дізнатись до того, як користувач упреться."""
    probe = pp.probe_stability(getter=_getter(200, {"credits": 0}))
    assert probe.status == pp.FAIL


def test_stability_low_balance_is_warn(monkeypatch):
    monkeypatch.setenv("PROVIDER_PROBE_MIN_CREDITS", "100")
    probe = pp.probe_stability(getter=_getter(200, {"credits": 20}))
    assert probe.status == pp.WARN
    assert not probe.failed


def test_stability_unparsable_balance_still_ok():
    probe = pp.probe_stability(getter=_getter(200, {"unexpected": "shape"}))
    assert probe.status == pp.OK


def test_stability_reads_balance_from_same_response():
    """Один запит, не два: тіло беремо з тієї ж відповіді, що дала статус."""
    seen = []
    probe = pp.probe_stability(getter=_getter(200, {"credits": 7}, record=seen))
    assert len(seen) == 1
    assert probe.balance == 7


# ── агрегація й вимикач ──────────────────────────────────────────────────────

def test_overall_fails_when_any_engine_fails():
    def g(url, token, timeout):
        return _Resp(404) if "replicate" in url else _Resp(200, {"credits": 999})
    status = pp.probe_engines(getter=g)
    assert not status.ok
    assert any(p.failed and p.engine == pp.ENGINE_FLUX for p in status.engines)


def test_overall_ok_on_warn_only():
    status = pp.probe_engines(getter=_getter(503))
    assert status.ok, "тимчасові збої не мають валити щоденну перевірку"


def test_probe_disabled_by_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_PROBE_ENABLED", "0")
    status = pp.probe_engines(getter=_getter(404))
    assert status.ok and status.engines == ()


def test_paid_generation_probe_is_opt_in(monkeypatch):
    """Дефолт має бути OFF: щоденна генерація коштує ~$3/міс при $45 виторгу."""
    monkeypatch.delenv("PROVIDER_PROBE_GENERATE", raising=False)
    assert not pp.generation_probe_enabled()
    monkeypatch.setenv("PROVIDER_PROBE_GENERATE", "1")
    assert pp.generation_probe_enabled()
    monkeypatch.setenv("PROVIDER_PROBE_GENERATE", "true")
    assert not pp.generation_probe_enabled(), "вмикається рівно '1', як решта прапорців"


# ── текст для оператора ──────────────────────────────────────────────────────

def test_summary_names_the_broken_engine():
    def g(url, token, timeout):
        return _Resp(404) if "openai" in url else _Resp(200, {"credits": 999})
    text = pp.summary_text(pp.probe_engines(getter=g))
    assert "ПРОБЛЕМА" in text
    assert pp.ENGINE_GPT_IMAGE in text
    assert "моделі немає" in text


def test_summary_ok_mentions_balance():
    text = pp.summary_text(pp.probe_engines(getter=_getter(200, {"credits": 4242})))
    assert text.startswith("Проба двигунів OK")
    assert "4242 кредитів" in text


def test_summary_when_disabled(monkeypatch):
    monkeypatch.setenv("PROVIDER_PROBE_ENABLED", "0")
    assert "вимкнено" in pp.summary_text(pp.probe_engines(getter=_getter(200)))
