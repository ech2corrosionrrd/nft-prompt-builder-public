"""Сервісний шар (ops_status/provider_status) повертає i18n-ключі, не готовий текст.

Гарантує, що кожен detail_key/purpose_key/note_key визначено в ui_strings (uk+en) —
інакше адмінка показала б сам ключ замість тексту (тиха регресія локалізації).
"""

import ui_strings
from services import ops_status, provider_status


def _resolves(key: str) -> bool:
    # t() повертає сам ключ, якщо його немає в таблиці → значить не визначено
    return ui_strings._STRINGS.get(key) is not None


def test_ops_detail_keys_defined(monkeypatch):
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "1")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "x")
    rd = ops_status.readiness_summary(app_url="http://x", pay_url="http://y")
    assert rd["items"], "очікуємо непорожній список пунктів"
    for it in rd["items"]:
        assert "detail" not in it, "сервіс не має повертати готовий текст detail"
        assert _resolves(it["detail_key"]), f"невизначений ключ {it['detail_key']}"
        # ключ із плейсхолдерами форматується без помилки
        ui_strings.t(it["detail_key"], **it.get("detail_args", {}))


def test_provider_purpose_keys_defined():
    for p in provider_status.provider_links():
        assert _resolves(p["purpose_key"]), f"невизначений {p['purpose_key']}"


def test_provider_float_note_keys_defined(monkeypatch):
    for k in ("STABILITY_API_KEY",):
        monkeypatch.delenv(k, raising=False)
    for f in provider_status.provider_float_status():
        assert _resolves(f["note_key"]), f"невизначений {f['note_key']}"
        ui_strings.t(f["note_key"], **f.get("note_args", {}))


def test_ops_detail_renders_en_vs_uk(monkeypatch):
    """Один і той самий detail_key дає різний текст у EN vs UK (реальна локалізація)."""
    monkeypatch.setattr(ui_strings, "ui_lang", lambda: "en")
    en = ui_strings.t("ops.detail.sim_off")
    monkeypatch.setattr(ui_strings, "ui_lang", lambda: "uk")
    uk = ui_strings.t("ops.detail.sim_off")
    assert en == "disabled" and uk == "вимкнено"
