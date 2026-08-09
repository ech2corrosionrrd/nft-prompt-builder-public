"""Тести стану провайдерів: баланс Stability + health усіх провайдерів (без мережі)."""

from services import provider_status

_KEY_ENVS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "STABILITY_API_KEY", "REPLICATE_API_TOKEN",
    "PINATA_JWT", "HELIO_API_KEY", "BASE_RPC_URL", "SOLANA_RPC_URL",
)
_ALL = {"OpenAI", "Anthropic", "Stability AI", "Replicate", "Pinata", "Helio", "Base RPC", "Solana RPC"}


def test_stability_balance_parses(monkeypatch):
    monkeypatch.setenv("STABILITY_API_KEY", "k")

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"credits": 123.5}

    monkeypatch.setattr(provider_status.httpx, "get", lambda *a, **k: _R())
    assert provider_status.stability_balance() == 123.5


def test_stability_balance_none_without_key(monkeypatch):
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)
    assert provider_status.stability_balance() is None


def test_stability_balance_fail_closed(monkeypatch):
    monkeypatch.setenv("STABILITY_API_KEY", "k")

    def _boom(*a, **k):
        raise RuntimeError("network")

    monkeypatch.setattr(provider_status.httpx, "get", _boom)
    assert provider_status.stability_balance() is None


def test_provider_links_cover_all_with_urls(monkeypatch):
    for k in _KEY_ENVS:
        monkeypatch.delenv(k, raising=False)
    links = {p["name"]: p for p in provider_status.provider_links()}
    assert set(links) == _ALL                       # усі провайдери проєкту присутні
    assert all(p["url"].startswith("http") for p in links.values())  # у кожного є посилання
    assert all(p["purpose_key"].startswith("prov.purpose.") for p in links.values())  # i18n-ключ «навіщо»
    assert links["OpenAI"]["configured"] is False   # без ключа
    assert links["Base RPC"]["configured"] is True   # RPC має дефолт → налаштований
    assert links["Solana RPC"]["configured"] is True


def test_key_health_unconfigured(monkeypatch):
    for k in _KEY_ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(provider_status, "_http_ok", lambda *a, **k: True)
    monkeypatch.setattr(provider_status, "_rpc_ok", lambda *a, **k: None)
    monkeypatch.setattr(provider_status, "stability_balance", lambda: None)
    h = {x["name"]: x for x in provider_status.key_health()}
    assert set(h) == _ALL
    for n in ("OpenAI", "Anthropic", "Stability AI", "Replicate", "Pinata"):
        assert h[n]["configured"] is False and h[n]["checked"] is False
    assert h["Helio"]["checked"] is False               # Helio навмисне не пробуємо
    assert h["Base RPC"]["configured"] is True and h["Base RPC"]["checked"] is True


def test_key_health_probes_when_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("STABILITY_API_KEY", "st")
    monkeypatch.setenv("HELIO_API_KEY", "h")
    for k in ("ANTHROPIC_API_KEY", "REPLICATE_API_TOKEN", "PINATA_JWT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(provider_status, "_http_ok", lambda *a, **k: True)
    monkeypatch.setattr(provider_status, "_rpc_ok", lambda *a, **k: True)
    monkeypatch.setattr(provider_status, "stability_balance", lambda: 42.0)
    h = {x["name"]: x for x in provider_status.key_health()}
    assert h["OpenAI"]["checked"] and h["OpenAI"]["valid"] is True
    assert h["Stability AI"]["balance"] == 42.0 and h["Stability AI"]["valid"] is True
    assert h["Helio"]["configured"] is True and h["Helio"]["checked"] is False  # не пробуємо
    assert h["Base RPC"]["valid"] is True


# ── Провайдерський флоат (рек. мінімум vs баланс) ─────────────────────────────

def test_provider_float_stability_statuses(monkeypatch):
    monkeypatch.delenv("STABILITY_LOW_BALANCE", raising=False)  # дефолт 100
    cases = {
        2500: "ok",        # $25 ≥ рек. $20
        1025: "low",       # $10.25 < рек. $20, але ≥ поріг 100 cr
        50: "critical",    # < поріг алерту 100 cr
    }
    for credits, want in cases.items():
        monkeypatch.setattr(provider_status, "stability_balance", lambda c=credits: float(c))
        row = {r["name"]: r for r in provider_status.provider_float_status()}["Stability AI"]
        assert row["status"] == want, f"{credits}cr → {row['status']} (очік. {want})"
        assert row["balance_usd"] == round(credits * provider_status.STABILITY_USD_PER_CREDIT, 2)


def test_provider_float_postpaid_and_pinata(monkeypatch):
    monkeypatch.setattr(provider_status, "stability_balance", lambda: None)
    rows = {r["name"]: r for r in provider_status.provider_float_status()}
    # postpaid-провайдери: рекомендований мінімум є, балансу нема, статус unknown
    assert rows["OpenAI"]["recommended_usd"] == 30.0
    assert rows["OpenAI"]["balance_usd"] is None and rows["OpenAI"]["status"] == "unknown"
    assert rows["Pinata"]["status"] == "ok"               # free-tier
    assert rows["Stability AI"]["status"] == "unknown"    # баланс недоступний
