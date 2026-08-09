"""Тести операційного стану (ADM-C): readiness + reconcile-маркер, без мережі."""

from pathlib import Path

from services import ops_status

_ENVS = ("APP_ENV", "AUTH_GATEWAY_ENFORCE", "ENABLE_SIM_PAYMENTS",
         "AUTH_SESSION_SECRET", "OPENAI_API_KEY", "HELIO_WEBHOOK_SECRET", "HELIO_API_KEY")


def _clean_env(monkeypatch):
    for k in _ENVS:
        monkeypatch.delenv(k, raising=False)


def _prod_env(monkeypatch):
    """Здоровий прод-стан: production, гард на '1', секрети задані, sim вимкнено."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "1")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "real-prod-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("HELIO_WEBHOOK_SECRET", "whsec")
    monkeypatch.setenv("HELIO_API_KEY", "h")


def test_readiness_all_ok_when_healthy(monkeypatch):
    _prod_env(monkeypatch)
    monkeypatch.setattr(ops_status, "_http_ok", lambda url: True)
    monkeypatch.setattr(ops_status, "last_reconcile", lambda: "2026-06-17T00:00:00+00:00")
    rd = ops_status.readiness_summary()
    assert rd["all_ok"] is True
    assert all(i["ok"] is True for i in rd["items"])
    assert rd["last_reconcile"].startswith("2026-")


def test_health_down_marks_not_ok(monkeypatch):
    _prod_env(monkeypatch)
    monkeypatch.setattr(ops_status, "_http_ok", lambda url: False)
    rd = ops_status.readiness_summary()
    assert rd["all_ok"] is False
    assert {i["name"] for i in rd["items"] if i["ok"] is False} >= {"Streamlit (APP)", "API webhook"}


def test_network_none_does_not_fail_overall(monkeypatch):
    """None (мережа недоступна) — це ⚠️ «не перевірено», не валить all_ok."""
    _prod_env(monkeypatch)
    monkeypatch.setattr(ops_status, "_http_ok", lambda url: None)
    rd = ops_status.readiness_summary()
    assert rd["all_ok"] is True
    assert all(i["ok"] is None for i in ops_status.health_items("http://a", "http://b"))


def test_sim_payments_on_is_not_ok(monkeypatch):
    _prod_env(monkeypatch)
    monkeypatch.setenv("ENABLE_SIM_PAYMENTS", "1")
    flags = {f["name"]: f for f in ops_status.env_flags()}
    assert flags["ENABLE_SIM_PAYMENTS"]["ok"] is False


def test_enforce_true_is_not_one(monkeypatch):
    """'true' НЕ вмикає гард — код порівнює рівно з '1' (landmine)."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "true")
    flags = {f["name"]: f for f in ops_status.env_flags()}
    assert flags["AUTH_GATEWAY_ENFORCE"]["ok"] is False
    # detail тепер i18n-ключ + args (текст локалізується в UI); сире значення — в args.
    f = flags["AUTH_GATEWAY_ENFORCE"]
    assert f["detail_key"] == "ops.detail.enforce_true"
    assert f["detail_args"]["val"] == "true"


def test_session_secret_required_when_enforced(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "1")  # гард є, секрета нема
    flags = {f["name"]: f for f in ops_status.env_flags()}
    assert flags["AUTH_SESSION_SECRET"]["ok"] is False


def test_test_secret_rejected_when_enforced(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "1")
    monkeypatch.setenv("AUTH_SESSION_SECRET", ops_status.TEST_SESSION_SECRET)
    flags = {f["name"]: f for f in ops_status.env_flags()}
    assert flags["AUTH_SESSION_SECRET"]["ok"] is False


def test_missing_critical_secret_not_ok(monkeypatch):
    _clean_env(monkeypatch)  # OPENAI_API_KEY відсутній
    flags = {f["name"]: f for f in ops_status.secret_flags()}
    assert flags["OPENAI_API_KEY"]["ok"] is False


def test_reconcile_marker_roundtrip(monkeypatch, tmp_path):
    marker = tmp_path / "data" / "last_reconcile.txt"
    monkeypatch.setattr(ops_status, "RECONCILE_MARKER", marker)
    assert ops_status.last_reconcile() is None  # ще нема
    ops_status.write_reconcile_marker()
    val = ops_status.last_reconcile()
    assert val and "T" in val  # ISO-час


def test_reconcile_marker_write_failsoft(monkeypatch):
    """Збій диска не валить звіряння — write проковтує помилку."""
    monkeypatch.setattr(ops_status, "RECONCILE_MARKER", Path("/nonexistent-root/x/y.txt"))

    def _boom(*a, **k):
        raise OSError("disk")

    monkeypatch.setattr(Path, "mkdir", _boom)
    ops_status.write_reconcile_marker()  # не кидає
