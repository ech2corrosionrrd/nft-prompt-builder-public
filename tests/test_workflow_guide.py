from ui.workflow_guide import (
    MODE_CLASSIC,
    MODE_PIPELINE,
    PENDING_PIPELINE_STAGE_KEY,
    PENDING_WORKFLOW_KEY,
    PIPELINE_TRANSFER_MSG_KEY,
    WORKFLOW_KEY,
    _md_bold_to_html,
    _apply_pending_pipeline_stage,
    adjacent_accessible_stage,
    adjacent_stage,
    batch_results_to_pipeline_prompts,
    classic_help_section,
    classic_progress,
    collect_classic_image_prompts,
    goto_pipeline_stage,
    help_section_expanded,
    init_workflow_state,
    ordered_tab_ids,
    pipeline_help_section,
    pipeline_hint_cta,
    pipeline_forward_action,
    pipeline_stage_button_label,
    stage_accessible,
    workflow_mode,
)


def test_batch_to_pipeline_maps_traits_en():
    results = [
        {
            "id": 1,
            "prompt": "cyber fox in neon city",
            "traits": {"Голова / Шолом / Маска": "crown", "Фон / Аура": "space"},
        }
    ]
    out = batch_results_to_pipeline_prompts(results)
    assert len(out) == 1
    assert out[0]["prompt"] == "cyber fox in neon city"
    assert out[0]["traits"] == {
        "Head / Helmet / Mask": "crown",
        "Background / Aura": "space",
    }


def test_batch_to_pipeline_skips_empty_prompts():
    assert batch_results_to_pipeline_prompts([{"prompt": "  ", "traits": {}}]) == []


def test_collect_classic_image_prompts_dedupes_and_priority():
    rows = collect_classic_image_prompts(
        image_prompt="solo prompt",
        prompt_options={"a": "from batch pick", "b": "solo prompt"},
        batch_results=[{"prompt": "batch one", "traits": {"Фон": "neon"}}],
    )
    assert [r["prompt"] for r in rows] == ["batch one", "from batch pick", "solo prompt"]
    assert rows[0]["traits"] == {"Фон": "neon"}


def test_collect_classic_image_prompts_empty():
    assert collect_classic_image_prompts() == []


def test_ordered_tab_ids_pipeline_first():
    """У Pipeline-режимі Конвеєр — перша вкладка (лендинг новачка)."""
    out = ordered_tab_ids(MODE_PIPELINE)
    assert out[0] == "pipeline"
    # Усі 8 вкладок присутні рівно по разу, незалежно від режиму.
    assert sorted(out) == sorted(ordered_tab_ids(MODE_CLASSIC))
    assert len(out) == 8


def test_ordered_tab_ids_classic_keeps_legacy_order():
    """Classic-режим лишає історичний порядок: Конструктор першим, Конвеєр перед хвостом."""
    out = ordered_tab_ids(MODE_CLASSIC)
    assert out[0] == "build"
    assert out[-2:] == ["history", "help"]
    assert out.index("pipeline") == 5


def test_default_workflow_mode_is_pipeline(monkeypatch):
    """Дефолт — Pipeline (рекомендований шлях): init виставляє, workflow_mode читає."""
    import streamlit as st

    fake: dict = {}
    monkeypatch.setattr(st, "session_state", fake)
    # До init ключа нема → workflow_mode дає дефолтний Pipeline.
    assert workflow_mode() == MODE_PIPELINE
    init_workflow_state()
    assert fake[WORKFLOW_KEY] == MODE_PIPELINE
    assert fake["pipeline_active_stage"] == "billing"


def test_help_section_expanded():
    assert help_section_expanded("4. Pipeline — in detail", "4") is True
    assert help_section_expanded("4. Конвеєр — детально", "4") is True
    assert help_section_expanded("5. Collection", "4") is False
    assert help_section_expanded("5. Collection", None) is False


def test_pipeline_and_classic_help_sections():
    assert pipeline_help_section("billing") == "4"
    assert classic_help_section("images") == "5"


def test_stage_accessible_gates():
    """UX-B1: billing/text завжди; images = текст+гаманець; mint = гаманець (upload/approve на етапі)."""
    empty = {"text": False, "images": False, "mint": False, "billing": False}
    assert stage_accessible("billing", empty) is True
    assert stage_accessible("text", empty) is True
    assert stage_accessible("images", empty) is False
    assert stage_accessible("mint", empty) is False
    # Лише промпт без гаманця — images все ще закрито.
    assert stage_accessible("images", {**empty, "text": True}) is False
    # Промпт + гаманець — images відкрито.
    assert stage_accessible("images", {**empty, "text": True, "billing": True}) is True
    # Гаманець — Export відкрито (контент додається approve/upload).
    assert stage_accessible("mint", {**empty, "billing": True}) is True
    # Є схвалений контент + гаманець.
    assert stage_accessible("mint", {**empty, "mint": True, "billing": True}) is True


def test_adjacent_stage_linear_order():
    assert adjacent_stage("billing", -1) is None      # перший — назад нікуди
    assert adjacent_stage("billing", +1) == "text"
    assert adjacent_stage("text", +1) == "images"
    assert adjacent_stage("images", +1) == "mint"
    assert adjacent_stage("mint", +1) is None          # останній — далі нікуди
    assert adjacent_stage("mint", -1) == "images"
    assert adjacent_stage("unknown", +1) is None       # невідомий етап


def test_adjacent_accessible_stage_skips_locked():
    """«Далі» пропускає заблоковані етапи (images без промптів → export з гаманцем)."""
    progress = {"text": False, "images": False, "mint": False, "billing": True}
    assert adjacent_accessible_stage("billing", +1, progress) == "text"
    assert adjacent_accessible_stage("text", +1, progress) == "mint"
    progress2 = {"text": True, "images": False, "mint": False, "billing": True}
    assert adjacent_accessible_stage("billing", +1, progress2) == "images"


def test_pipeline_hint_cta_routes_to_blocker():
    """UX-B8: CTA веде на етап, що знімає поточний блокер."""
    empty = {"text": False, "images": False, "mint": False, "billing": False}
    # Промпти готові, гаманця нема → з Тексту веди до Кредитів.
    assert pipeline_hint_cta("text", {**empty, "text": True}) == ("cta.connect_wallet", "billing")
    # На Зображеннях без гаманця → теж до Кредитів (стрибок через етап).
    assert pipeline_hint_cta("images", empty) == ("cta.connect_wallet", "billing")
    # Гаманець є, але промптів нема → назад до Тексту.
    assert pipeline_hint_cta("images", {**empty, "billing": True}) == ("cta.write_prompts", "text")
    # Гаманець підключено на етапі Кредитів без промптів → до Тексту.
    assert pipeline_hint_cta("billing", {**empty, "billing": True}) == ("cta.to_prompts", "text")
    # Промпти вже є (welcome) → одразу на Зображення.
    assert pipeline_hint_cta("billing", {**empty, "billing": True, "text": True}) == (
        "cta.to_images",
        "images",
    )
    # Зображення готові, схвалення ще ні → на Експорт (upload/approve там).
    assert pipeline_hint_cta("images", {**empty, "billing": True, "text": True, "images": True}) == (
        "cta.to_export",
        "mint",
    )
    # Експорт порожній без гаманця → назад до зображень.
    assert pipeline_hint_cta("mint", empty) == ("cta.back_to_images", "images")
    # Є гаманець, контенту ще нема — CTA на цьому ж етапі (upload).
    assert pipeline_hint_cta("mint", {**empty, "billing": True}) is None


def test_pipeline_hint_cta_none_when_no_blocker():
    """Немає блокера для прямого стрибка → CTA не показуємо (є generic Далі/Назад)."""
    empty = {"text": False, "images": False, "mint": False, "billing": False}
    # На Тексті без промптів — дія саме тут, нав-CTA зайвий.
    assert pipeline_hint_cta("text", empty) is None
    # Кредити ще не підключено — кнопку дає сам етап білінгу.
    assert pipeline_hint_cta("billing", empty) is None
    # Усе готово на Зображеннях → далі веде generic «Далі →».
    full = {"text": True, "images": True, "mint": True, "billing": True}
    assert pipeline_hint_cta("images", full) is None
    # Експорт готовий — термінальна дія тут.
    assert pipeline_hint_cta("mint", full) is None


def test_pipeline_forward_after_prompts(monkeypatch):
    import streamlit as st
    from ui import workflow_guide as wg

    fake: dict = {}
    monkeypatch.setattr(st, "session_state", fake)
    assert wg.pipeline_forward_after_prompts() == "billing"
    fake["wallet_address"] = "0xabc"
    assert wg.pipeline_forward_after_prompts() == "images"


def test_classic_forward_action_chain(monkeypatch):
    import streamlit as st
    from ui import workflow_guide as wg

    monkeypatch.setattr(st, "session_state", {})
    progress = {
        "build": True, "traits": True, "batch": True, "collection": True, "images": False,
    }
    # Пропуск уже завершених кроків (як adjacent_accessible у Pipeline).
    assert wg.classic_forward_action("build", progress) == ("cta.forward.classic", "images")
    assert wg.classic_forward_action("traits", progress) == ("cta.forward.classic", "images")
    assert wg.classic_forward_action("batch", progress) == ("cta.forward.classic", "images")
    assert wg.classic_forward_action("collection", progress) == ("cta.forward.classic", "images")
    assert wg.classic_forward_action("images", progress) is None

    linear = {"build": True, "traits": False, "batch": False, "collection": False, "images": False}
    assert wg.classic_forward_action("build", linear) == ("cta.forward.classic", "traits")
    assert wg.classic_forward_action("traits", {**linear, "traits": True}) == (
        "cta.forward.classic", "batch",
    )


def test_pipeline_forward_action_after_stage_complete():
    """Після завершення етапу — явна кнопка «Далі» (UX-B9)."""
    empty = {"text": False, "images": False, "mint": False, "billing": False}
    assert pipeline_forward_action("billing", empty) is None
    assert pipeline_forward_action("billing", {**empty, "billing": True}) == (
        "cta.forward.prompts",
        "text",
    )
    assert pipeline_forward_action("billing", {**empty, "billing": True, "text": True}) == (
        "cta.forward.images",
        "images",
    )
    assert pipeline_forward_action("text", {**empty, "text": True, "billing": True}) == (
        "cta.forward.images",
        "images",
    )
    assert pipeline_forward_action("text", {**empty, "text": True}) is None
    assert pipeline_forward_action("images", {**empty, "billing": True, "text": True, "images": True}) == (
        "cta.forward.export",
        "mint",
    )
    assert pipeline_forward_action("images", {**empty, "billing": True, "text": True}) is None
    assert pipeline_forward_action("mint", {**empty, "mint": True}) is None


def test_pipeline_stage_button_label_shows_done_mark():
    labels = {"billing": "💳 Credits", "text": "1️⃣ Text"}
    assert pipeline_stage_button_label("billing", labels, {"billing": True}).startswith("✓")
    assert not pipeline_stage_button_label("text", labels, {"billing": True}).startswith("✓")


def test_request_welcome_clears_seen_on_init(monkeypatch):
    """PENDING_WELCOME → init_workflow_state скидає welcome_seen."""
    from ui.workflow_guide import PENDING_WELCOME_KEY, init_workflow_state

    class FakeSessionState(dict):
        def pop(self, key, default=None):
            return super().pop(key, default)

    import streamlit as st

    fake = FakeSessionState(welcome_seen=True, **{PENDING_WELCOME_KEY: True})
    monkeypatch.setattr(st, "session_state", fake)
    init_workflow_state()
    assert fake.get("welcome_seen") is False
    assert PENDING_WELCOME_KEY not in fake


def test_goto_pipeline_stage_sets_session(monkeypatch):
    """goto_pipeline_stage без Streamlit — через підміну session_state."""
    class FakeSessionState(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    import streamlit as st

    fake = FakeSessionState()
    monkeypatch.setattr(st, "session_state", fake)

    count = goto_pipeline_stage("images", [{"prompt": "fox", "traits": {}}], source="Batch")
    assert count == 1
    assert fake[PENDING_WORKFLOW_KEY] == MODE_PIPELINE
    assert fake[PENDING_PIPELINE_STAGE_KEY] == "images"
    assert PIPELINE_TRANSFER_MSG_KEY in fake
    assert "Batch" in fake[PIPELINE_TRANSFER_MSG_KEY]


def test_md_bold_to_html_converts_bold():
    # **...** має стати <strong>...</strong> (BUG-1: raw markdown у HTML-div)
    out = _md_bold_to_html("**Now:** describe · **Why:** locked")
    assert out == "<strong>Now:</strong> describe · <strong>Why:</strong> locked"
    assert "**" not in out


def test_md_bold_to_html_no_bold_unchanged():
    assert _md_bold_to_html("plain text, no bold") == "plain text, no bold"


def test_md_bold_to_html_non_greedy():
    # дві окремі пари не зливаються в одну
    out = _md_bold_to_html("**a** mid **b**")
    assert out == "<strong>a</strong> mid <strong>b</strong>"


class _FakeQueryParams(dict):
    """Стаб st.query_params: .get + запис як у Streamlit."""


def test_apply_pending_pipeline_stage(monkeypatch):
    """Pending етап застосовується безпосередньо перед pills, не на init."""
    import streamlit as st

    fake = {"pipeline_active_stage": "text", PENDING_PIPELINE_STAGE_KEY: "images"}
    monkeypatch.setattr(st, "session_state", fake)
    _apply_pending_pipeline_stage()
    assert fake["pipeline_active_stage"] == "images"
    assert PENDING_PIPELINE_STAGE_KEY not in fake


def test_apply_pending_pipeline_stage_returns_applied_stage(monkeypatch):
    import streamlit as st

    fake = {"pipeline_active_stage": "text", PENDING_PIPELINE_STAGE_KEY: "images"}
    monkeypatch.setattr(st, "session_state", fake)
    assert _apply_pending_pipeline_stage() == "images"


def test_apply_pending_pipeline_stage_returns_none_without_pending(monkeypatch):
    import streamlit as st

    fake = {"pipeline_active_stage": "text"}
    monkeypatch.setattr(st, "session_state", fake)
    assert _apply_pending_pipeline_stage() is None


def test_apply_pending_pipeline_stage_ignores_invalid(monkeypatch):
    import streamlit as st

    fake = {"pipeline_active_stage": "text", PENDING_PIPELINE_STAGE_KEY: "bogus"}
    monkeypatch.setattr(st, "session_state", fake)
    _apply_pending_pipeline_stage()
    assert fake["pipeline_active_stage"] == "text"
    assert PENDING_PIPELINE_STAGE_KEY not in fake


def test_init_seeds_stage_from_url(monkeypatch):
    """Свіжа сесія (рефреш) піднімає крок конвеєра з ?stage= в URL."""
    import streamlit as st

    monkeypatch.setattr(st, "query_params", _FakeQueryParams({"stage": "images"}))
    fake: dict = {}
    monkeypatch.setattr(st, "session_state", fake)
    init_workflow_state()
    assert fake["pipeline_active_stage"] == "images"


def test_init_ignores_invalid_url_stage(monkeypatch):
    """Невідомий ?stage= не ламає init — дефолт billing."""
    import streamlit as st

    monkeypatch.setattr(st, "query_params", _FakeQueryParams({"stage": "bogus"}))
    fake: dict = {}
    monkeypatch.setattr(st, "session_state", fake)
    init_workflow_state()
    assert fake["pipeline_active_stage"] == "billing"


def test_classic_progress_blocks_later_steps_without_traits(monkeypatch):
    """Traits ○ → batch/collection/images теж не «✓» (BUG-002)."""
    import streamlit as st

    fake = {
        "idea": "cyber fox",
        "batch_results": [{"prompt": "p1"}],
        "collection_run": None,
        "generated_images": [{"path": "/x"}],
    }
    monkeypatch.setattr(st, "session_state", fake)

    progress = classic_progress(lambda: {})
    assert progress["build"] is True
    assert progress["traits"] is False
    assert progress["batch"] is False
    assert progress["collection"] is False
    assert progress["images"] is False


def test_sync_url_stage_writes_only_on_change(monkeypatch):
    """sync_url_stage пише ?stage= лише при зміні (немає циклу reruns)."""
    import streamlit as st
    from ui.workflow_guide import WORKFLOW_KEY, sync_url_stage

    qp = _FakeQueryParams()
    monkeypatch.setattr(st, "query_params", qp)
    monkeypatch.setattr(st, "session_state", {WORKFLOW_KEY: MODE_PIPELINE})
    sync_url_stage("mint")
    assert qp["stage"] == "mint"
    # повторний виклик з тим самим значенням не «смикає» URL (значення лишається)
    sync_url_stage("mint")
    assert qp == {"stage": "mint"}
    # некоректний етап ігнорується
    sync_url_stage("bogus")
    assert qp["stage"] == "mint"


def test_sync_url_stage_clears_in_classic(monkeypatch):
    """У Classic ?stage= прибирається — не липне billing на Конструкторі."""
    import streamlit as st
    from ui.workflow_guide import WORKFLOW_KEY, sync_url_stage

    qp = _FakeQueryParams({"stage": "billing"})
    monkeypatch.setattr(st, "query_params", qp)
    monkeypatch.setattr(st, "session_state", {WORKFLOW_KEY: MODE_CLASSIC})
    sync_url_stage("billing")
    assert "stage" not in qp


def test_build_system_lists_trait_categories():
    from builder import build_system_instruction
    from i18n import TRAIT_CATEGORY_EN
    from options import TRAIT_CATEGORIES

    uk = build_system_instruction("OpenAI Images", True, True, lang="uk")
    for cat in TRAIT_CATEGORIES:
        assert cat in uk
    en = build_system_instruction("OpenAI Images", True, True, lang="en")
    for cat in TRAIT_CATEGORIES:
        assert TRAIT_CATEGORY_EN[cat] in en
