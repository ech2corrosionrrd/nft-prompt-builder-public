"""Headless UI-smoke: app.py виконується через Streamlit AppTest без винятків.

Ловить render-краші головного застосунку (биті f-стрічки, неправильні виклики
Streamlit, помилки в перевпорядкуванні/приховуванні вкладок, регресії UX-A1),
яких unit-тести сервісів не бачать. conftest не вантажить .env (ROOT →
неіснуюча тека), а гард тут вимкнено явно — тож рендериться ПОВНИЙ застосунок
із вкладками, не екран входу SIWE.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from services import project_service

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _run(monkeypatch, welcome_seen=True):
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")  # без SIWE-гарду → повний рендер
    at = AppTest.from_file(APP, default_timeout=60)
    if welcome_seen:
        at.session_state["welcome_seen"] = True  # пропустити welcome-гейт (UX-A3)
    at.run()
    return at


def test_welcome_shows_continue_when_projects_exist(monkeypatch, tmp_path):
    """Welcome: якщо є збережені проєкти — кнопка «Продовжити останній»."""
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")
    wallet = "0x" + "cd" * 20
    monkeypatch.setattr(
        "services.project_service.WORKSPACE_ROOT", tmp_path / "workspace",
    )
    project_service.create_project(wallet, "Saved drop")
    import streamlit as st

    class _State(dict):
        def get(self, key, default=None):
            return super().get(key, default)

        def pop(self, key, default=None):
            return super().pop(key, default)

    monkeypatch.setattr(st, "session_state", _State(wallet_address=wallet))
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    labels = [b.label for b in at.button]
    assert any("Continue" in lbl or "Продовжити" in lbl for lbl in labels)


def test_app_renders_without_exception(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception, at.exception


def test_app_has_top_level_tabs(monkeypatch):
    """Рендер дає верхній рівень вкладок (8 без адмін-гаманця)."""
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    # AppTest.tabs — пласкі контейнери вкладок; має бути щонайменше 8 (без Адмін).
    assert len(at.tabs) >= 8


def test_app_trust_strip_rendered(monkeypatch):
    """UX-A4: trust strip присутній у рендері головної."""
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "trust-strip" in md


def test_app_pipeline_mode_default(monkeypatch):
    """UX-A1: дефолтний режим — Pipeline (а не Classic)."""
    at = _run(monkeypatch)
    assert not at.exception, at.exception
    from ui.workflow_guide import MODE_PIPELINE, WORKFLOW_KEY

    assert at.session_state[WORKFLOW_KEY] == MODE_PIPELINE


def test_welcome_gate_first_visit(monkeypatch):
    """UX-A3: на першому візиті показується welcome-гейт із трьома сценаріями."""
    at = _run(monkeypatch, welcome_seen=False)
    assert not at.exception, at.exception
    labels = [b.label for b in at.button]
    assert any("1 NFT" in lbl for lbl in labels)
    assert any("25" in lbl for lbl in labels)
    # Гейт зупиняє рендер до вкладок — головних вкладок ще не видно.
    assert len(at.tabs) == 0


def test_welcome_one_nft_sets_pipeline(monkeypatch):
    """Кнопка «1 NFT» → Pipeline-режим + шаблон 1/1 (через PENDING_* після rerun)."""
    from ui.workflow_guide import MODE_PIPELINE, PENDING_WORKFLOW_KEY

    from ui.workflow_guide import WORKFLOW_KEY

    at = _run(monkeypatch, welcome_seen=False)
    btn = next(b for b in at.button if "1 NFT" in b.label)
    btn.click().run()
    assert not at.exception, at.exception
    # init_workflow_state спожив PENDING на rerun → режим застосовано.
    assert PENDING_WORKFLOW_KEY not in at.session_state
    assert at.session_state[WORKFLOW_KEY] == MODE_PIPELINE
    assert at.session_state["welcome_seen"] is True
    assert at.session_state["active_template"] == "1/1 Fine Art"


def test_nav_back_to_welcome(monkeypatch):
    """Sidebar «Choose path» → welcome-гейт знову."""
    at = _run(monkeypatch, welcome_seen=True)
    assert not at.exception, at.exception
    btn = next(
        b for b in at.button
        if "Choose your path" in b.label or "Обрати напрям" in b.label
    )
    btn.click().run()
    assert not at.exception, at.exception
    labels = [b.label for b in at.button]
    assert any("1 NFT" in lbl for lbl in labels)
    assert len(at.tabs) == 0


def test_pipeline_text_empty_state(monkeypatch):
    """UX-B4: дефолтний етап Текст без промптів показує орієнтир-картку."""
    at = _run(monkeypatch)  # welcome дисміснуто, стан порожній, етап text
    assert not at.exception, at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "Prompt-Lock" in md  # маркер empty.pipeline.text


def test_pipeline_export_stage_gated(monkeypatch):
    """UX-B1: етап Експорт без гаманця показує блок, не падає."""
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["welcome_seen"] = True
    at.session_state["pipeline_active_stage"] = "mint"
    at.run()
    assert not at.exception, at.exception
    warns = " ".join(w.value for w in at.warning)
    assert "Спочатку" in warns or "first" in warns.lower() or "locked" in warns.lower()


def test_batch_tab_generate_succeeds(monkeypatch):
    """Регресія build_tech_params: клік «Згенерувати» у вкладці Batch має дати успіх.

    Цей шлях (обробник кнопки `run_batch_generation`) headless-рендер не зачіпає, бо
    кнопку треба клікнути — саме тому зник імпорт `build_tech_params` лишався непомітним.
    Пастка: `batch_panel` ловить будь-який виняток у `except Exception` і ховає його в
    `st.error`, тож `at.exception` лишається порожнім навіть при NameError. Тому
    перевіряємо САМЕ успіх (batch_results заповнено), а не лише відсутність винятку.
    Мережу глушимо моком `generate_batch_async`; білінг у тестах вимкнено (try_reserve→ok).
    """
    import batch
    from options import TRAIT_CATEGORIES, trait_key

    async def _fake_generate(api_key, model, platform, base, combos, tech, temperature,
                             on_progress=None):
        results = [{"id": i + 1, "prompt": f"prompt {i}"} for i in range(len(combos))]
        if on_progress:
            on_progress(len(results), len(results))
        return results, {"prompt_tokens": 10, "completion_tokens": 20}, []

    # app.py робить `from batch import generate_batch_async` при exec — патчимо ДО run().
    monkeypatch.setattr(batch, "generate_batch_async", _fake_generate)
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")
    monkeypatch.setenv("UI_DEFAULT_LANG", "en")
    # Герметичність: білінг вимкнено НАПРЯМУ → try_reserve→ok без верифікованого гаманця.
    # Чому не досить env: exec app.py під час at.run() перечитує .env і повертає
    # APP_ENV=production в os.environ ПІСЛЯ delenv → enforcement вмикається, reserve_llm
    # повертає "wallet", генерація не стартує (batch_results=[]). У повному наборі проходило
    # лише через порядок імпортів. Прямий патч робить тест order-independent (це wiring-смоук,
    # не тест білінгу).
    from services import billing_guard
    monkeypatch.setattr(billing_guard, "enforcement_enabled", lambda: False)

    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["welcome_seen"] = True
    at.session_state["idea"] = "neon cats"  # знімає гард batch.need_idea
    at.session_state["api_key_input"] = "sk-test"  # llm_key truthy → не api_key_missing
    # Непорожні traits → кнопка генерації рендериться (гард batch.need_traits).
    at.session_state[trait_key(TRAIT_CATEGORIES[0])] = "blue | 2\nred\ngreen"
    at.run()
    assert not at.exception, at.exception

    btn = next(b for b in at.button if "prompts" in b.label and "Generate" in b.label)
    btn.click().run()
    assert not at.exception, at.exception
    # Успіх: run_batch_generation відпрацював і записав результати (а не впав у st.error).
    assert at.session_state["batch_results"], "Batch-генерація не дала результатів (NameError проковтнуто?)"
    assert len(at.session_state["batch_results"]) == 10


def test_admin_panel_renders_five_tabs(monkeypatch, tmp_path):
    """ADM-D: admin_panel.render() дає 5 вкладок без винятку.

    Зовнішні сервіси (мережа/окремі БД) застублено — smoke перевіряє саме
    розкладку вкладок і обгортки _render_*, не дані.
    """
    from services import (
        ops_status,
        payment_service,
        provider_spend,
        provider_status,
    )
    from ui import admin_panel

    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    addr = "0x" + "ab" * 20
    payment_service.complete_wallet_sign_in(addr)
    payment_service.record_payment("tx1", addr, 100, 4.99)
    payment_service.deduct_credits(addr, 4, engine="OpenAI DALL-E 3", note="img")
    monkeypatch.setenv("ADMIN_WALLETS", addr)

    # Стаби зовнішніх викликів (мережа + окрема provider_spend.db).
    monkeypatch.setattr(provider_status, "key_health", lambda: [])
    monkeypatch.setattr(
        ops_status, "readiness_summary",
        lambda *a, **k: {"items": [], "all_ok": True, "last_reconcile": None},
    )
    monkeypatch.setattr(provider_spend, "total_usd", lambda *a, **k: 0.0)
    monkeypatch.setattr(provider_spend, "by_provider", lambda *a, **k: [])
    monkeypatch.setattr(provider_spend, "list_imports", lambda limit=50: [])
    # Кеші st.cache_data можуть утримувати стале з інших тестів — скидаємо.
    admin_panel._cached_health.clear()
    admin_panel._cached_readiness.clear()

    def script():
        from ui import admin_panel as ap
        ap.render()

    at = AppTest.from_function(script, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 5  # Огляд / Економіка / Користувачі / Ops / Провайдери


def _admin_tab_labels(monkeypatch, tmp_path, lang):
    """Рендерить admin-панель у заданій мові й повертає підписи 5 вкладок (BUG-2 i18n)."""
    from services import ops_status, payment_service, provider_spend, provider_status
    from ui import admin_panel

    monkeypatch.setenv("UI_DEFAULT_LANG", lang)
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / f"users_{lang}.db")
    addr = "0x" + "cd" * 20
    payment_service.complete_wallet_sign_in(addr)
    monkeypatch.setenv("ADMIN_WALLETS", addr)
    monkeypatch.setattr(provider_status, "key_health", lambda: [])
    monkeypatch.setattr(
        ops_status, "readiness_summary",
        lambda *a, **k: {"items": [], "all_ok": True, "last_reconcile": None},
    )
    monkeypatch.setattr(provider_spend, "list_imports", lambda limit=50: [])
    admin_panel._cached_health.clear()
    admin_panel._cached_readiness.clear()

    def script():
        from ui import admin_panel as ap
        ap.render()

    at = AppTest.from_function(script, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return [tab.label for tab in at.tabs]


def test_admin_panel_localized_en(monkeypatch, tmp_path):
    """BUG-2: у EN-режимі вкладки адмінки перекладені (не кирилиця)."""
    labels = _admin_tab_labels(monkeypatch, tmp_path, "en")
    assert labels == ["Overview", "Economics", "Users", "Ops", "Providers"]


def test_admin_panel_localized_uk(monkeypatch, tmp_path):
    """UK-режим лишає українські підписи вкладок адмінки."""
    labels = _admin_tab_labels(monkeypatch, tmp_path, "uk")
    assert labels == ["Огляд", "Економіка", "Користувачі", "Ops", "Провайдери"]
