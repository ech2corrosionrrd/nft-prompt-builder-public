"""Тести i18n-хелперів пакетів кредитів (BUG-3: назви/нотатки без EN-перекладу)."""

import ui_strings
from services.payment_service import PACKAGES


def _set_lang(monkeypatch, lang):
    monkeypatch.setattr(ui_strings, "ui_lang", lambda: lang)


def test_all_packages_have_label_and_note_keys():
    # кожен пакет із PACKAGES має i18n-ключі label+note (інакше UI впаде на uk)
    for pid in PACKAGES:
        assert f"pkg.{pid}.label" in ui_strings._STRINGS, f"немає pkg.{pid}.label"
        assert f"pkg.{pid}.note" in ui_strings._STRINGS, f"немає pkg.{pid}.note"


def test_package_label_translates_en(monkeypatch):
    _set_lang(monkeypatch, "en")
    assert ui_strings.package_label("start") == "🟢 Start"
    assert ui_strings.package_label("creator") == "🟡 Creator"
    assert ui_strings.package_label("pro") == "🔵 Pro / Collection"


def test_package_label_uk(monkeypatch):
    _set_lang(monkeypatch, "uk")
    assert ui_strings.package_label("start") == "🟢 Старт"


def test_package_note_translates_en(monkeypatch):
    _set_lang(monkeypatch, "en")
    note = ui_strings.package_note("creator")
    assert "bonus" in note.lower()
    assert "бонус" not in note  # жодної кирилиці в EN


def test_package_label_unknown_id_fallback(monkeypatch):
    _set_lang(monkeypatch, "en")
    # невідомий пакет → повертаємо сам id, не «ключ pkg.X.label»
    assert ui_strings.package_label("ghost") == "ghost"


def test_package_note_unknown_id_empty(monkeypatch):
    _set_lang(monkeypatch, "en")
    assert ui_strings.package_note("ghost") == ""
