import re
import string
from pathlib import Path

from ui.cost_calculator import _suggest_package
from ui_strings import LANG_EN, LANG_UA, _STRINGS, default_ui_lang, t

_ROOT = Path(__file__).resolve().parent.parent
_T_LITERAL = re.compile(r'\bt\(\s*["\']([a-zA-Z0-9_.]+)["\']')


def _placeholders(text: str) -> set[str]:
    """Множина іменованих format-полів `{name}` (з коректним '{{' екрануванням)."""
    return {field for _, field, _, _ in string.Formatter().parse(text) if field}


def test_strings_bilingual():
    """Кожен ключ має UK і EN."""
    for key, block in _STRINGS.items():
        assert LANG_UA in block, f"missing UK: {key}"
        assert LANG_EN in block, f"missing EN: {key}"


# ── B7: i18n parity uk↔en (ПЛАН_ЗАПОЗИЧЕНЬ) ───────────────────────────────────

def test_strings_no_unexpected_languages():
    """Жоден блок не має зайвих/одруківкових мовних ключів (лише uk+en)."""
    allowed = {LANG_UA, LANG_EN}
    extras = {key: set(block) - allowed for key, block in _STRINGS.items() if set(block) - allowed}
    assert not extras, f"несподівані мовні ключі: {extras}"


def test_strings_nonempty_both_langs():
    """Обидві мови — непорожні (присутній ключ із '' = фактично відсутній переклад)."""
    empty = [
        key for key, block in _STRINGS.items()
        if not block.get(LANG_UA, "").strip() or not block.get(LANG_EN, "").strip()
    ]
    assert not empty, f"порожній переклад uk або en: {empty}"


def test_strings_placeholder_parity():
    """Набори `{...}`-плейсхолдерів мусять збігатися uk↔en (інакше t(key, **fmt)
    у одній мові тихо віддасть неформатований текст)."""
    mismatched = {}
    for key, block in _STRINGS.items():
        uk = _placeholders(block.get(LANG_UA, ""))
        en = _placeholders(block.get(LANG_EN, ""))
        if uk != en:
            mismatched[key] = {"uk_only": uk - en, "en_only": en - uk}
    assert not mismatched, f"розбіжність плейсхолдерів uk↔en: {mismatched}"


def test_all_referenced_keys_defined():
    """Кожен літеральний ключ перекладу у продакшн-коді має визначення в _STRINGS."""
    missing: dict[str, str] = {}
    for path in _ROOT.rglob("*.py"):
        # Тести пропускаємо: можуть містити приклади-плейсхолдери, не реальні ключі.
        if "__pycache__" in path.parts or "tests" in path.parts or path.name == "ui_strings.py":
            continue
        for key in _T_LITERAL.findall(path.read_text(encoding="utf-8", errors="ignore")):
            if key not in _STRINGS:
                missing[key] = path.name
    assert not missing, f"ключі перекладу без визначення: {missing}"


def test_default_ui_lang_en():
    """Публічний сайт — English за замовчуванням (без env)."""
    assert default_ui_lang() == LANG_EN


def test_default_ui_lang_from_env(monkeypatch):
    monkeypatch.setenv("UI_DEFAULT_LANG", "uk")
    assert default_ui_lang() == LANG_UA
    monkeypatch.setenv("UI_DEFAULT_LANG", "en")
    assert default_ui_lang() == LANG_EN
    monkeypatch.setenv("UI_DEFAULT_LANG", "xx")
    assert default_ui_lang() == LANG_EN


def test_t_default_en():
    assert t("step.constructor") == "Builder"


def test_t_uk(monkeypatch):
    monkeypatch.setattr("ui_strings.ui_lang", lambda: LANG_UA)
    assert "Конструктор" in t("step.constructor")


def test_suggest_package_covers_supply():
    pkg_id, usd = _suggest_package(50)
    assert pkg_id == "start"
    assert usd == 4.99


def test_suggest_package_large_supply():
    pkg_id, _ = _suggest_package(2000)
    assert pkg_id == "pro"


class _FakeQueryParams(dict):
    """Стаб st.query_params: підтримує .get і запис як у Streamlit."""


def _patch_query(monkeypatch, initial=None):
    import streamlit as st
    fake = _FakeQueryParams(initial or {})
    monkeypatch.setattr(st, "query_params", fake)
    return fake


def test_query_lang_overrides_env(monkeypatch):
    """?lang=uk перемагає env UI_DEFAULT_LANG=en (persist між reload, BUG-4)."""
    from ui_strings import default_ui_lang

    monkeypatch.setenv("UI_DEFAULT_LANG", "en")
    _patch_query(monkeypatch, {"lang": "uk"})
    assert default_ui_lang() == LANG_UA


def test_query_lang_invalid_falls_back_to_env(monkeypatch):
    from ui_strings import default_ui_lang

    monkeypatch.setenv("UI_DEFAULT_LANG", "en")
    _patch_query(monkeypatch, {"lang": "zz"})
    assert default_ui_lang() == LANG_EN


def test_query_lang_absent_uses_env(monkeypatch):
    from ui_strings import default_ui_lang

    monkeypatch.setenv("UI_DEFAULT_LANG", "uk")
    _patch_query(monkeypatch, {})
    assert default_ui_lang() == LANG_UA


def test_set_ui_lang_persists_to_query(monkeypatch):
    import streamlit as st
    from ui_strings import set_ui_lang

    monkeypatch.setattr(st, "session_state", {})
    fake = _patch_query(monkeypatch, {})
    set_ui_lang("uk")
    assert fake.get("lang") == "uk"
    assert st.session_state["ui_lang"] == "uk"


def test_set_ui_lang_invalid_ignored(monkeypatch):
    import streamlit as st
    from ui_strings import set_ui_lang

    monkeypatch.setattr(st, "session_state", {})
    fake = _patch_query(monkeypatch, {})
    set_ui_lang("zz")
    assert "lang" not in fake
    assert "ui_lang" not in st.session_state
