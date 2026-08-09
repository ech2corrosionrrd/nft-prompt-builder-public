"""Навігація та логіка двох робочих шляхів застосунку."""

from __future__ import annotations

import re

import streamlit as st

from i18n import trait_type_en
from state.pipeline_state import APPROVED_CONTENT, GENERATED_PROMPTS, MINT_ASSETS
from ui_strings import t

WORKFLOW_KEY = "workflow_mode"
MODE_CLASSIC = "classic"
MODE_PIPELINE = "pipeline"

# Порядок вкладок верхнього рівня. У Pipeline-режимі (дефолт для новачка) Конвеєр —
# перша вкладка, тож застосунок landить саме на ньому; класичні вкладки йдуть далі
# як «розширені» (у Pipeline-режимі їх ще й ховають CSS-ом, див. app.py).
CLASSIC_TAB_IDS = ("build", "traits", "batch", "collection", "images")
CLASSIC_ORDER = CLASSIC_TAB_IDS
CLASSIC_TAB_FLASH_KEY = "_classic_tab_flash"
_TAIL_TAB_IDS = ("history", "help")


def pipeline_forward_after_prompts() -> str:
    """Цільовий етап після збереження промптів (гаманець → images, інакше billing)."""
    if pipeline_progress().get("billing"):
        return "images"
    return "billing"


def request_pipeline_stage(stage: str) -> None:
    """Перейти на етап конвеєра на наступному run (pending-key)."""
    st.session_state[PENDING_PIPELINE_STAGE_KEY] = stage


def render_inline_pipeline_forward(
    target: str,
    *,
    key_suffix: str = "",
    require_progress: dict[str, bool] | None = None,
) -> None:
    """Помітна кнопка «Далі» одразу після успішної дії на етапі (UX-B9 inline)."""
    progress = pipeline_progress()
    if require_progress:
        for k, need in require_progress.items():
            if bool(progress.get(k)) != need:
                return
    if not stage_accessible(target, progress):
        if target == "images" and not progress.get("billing"):
            target = "billing"
        elif not stage_accessible(target, progress):
            return
    labels = pipeline_stage_labels()
    st.divider()
    if st.button(
        t("cta.forward.prompts", next_stage=labels.get(target, target)),
        type="primary",
        width='stretch',
        key=f"inline_pipe_fwd_{target}_{key_suffix}",
    ):
        request_pipeline_stage(target)
        st.rerun()


def render_post_prompt_store_forward() -> None:
    """Після збереження промптів на Етапі 1 — одразу запропонувати наступний крок."""
    target = pipeline_forward_after_prompts()
    render_inline_pipeline_forward(target, key_suffix="pl1_store")


def _classic_next_incomplete(current: str, progress: dict[str, bool]) -> str | None:
    """Перша незавершена classic-вкладка після current (пропуск уже ✓ кроків)."""
    try:
        start = CLASSIC_ORDER.index(current) + 1
    except ValueError:
        return None
    for step_id in CLASSIC_ORDER[start:]:
        if not progress.get(step_id):
            return step_id
    return None


def classic_forward_action(current: str, progress: dict[str, bool]) -> tuple[str, str] | None:
    """Кнопка «Далі» для classic-вкладок — перший незавершений крок після поточного."""
    if current == "build":
        if not (progress.get("build") or st.session_state.get("last_result")):
            return None
    elif current not in CLASSIC_ORDER or not progress.get(current):
        return None
    target = _classic_next_incomplete(current, progress)
    if not target:
        return None
    return "cta.forward.classic", target


def render_classic_forward_cta(current_step: str, get_traits_weighted) -> None:
    """Кнопка переходу на наступну classic-вкладку після завершення етапу."""
    progress = classic_progress(get_traits_weighted)
    action = classic_forward_action(current_step, progress)
    if not action:
        return
    label_key, target = action
    labels = {s["id"]: f"{s['icon']} {s['label']}" for s in _classic_steps()}
    st.divider()
    st.caption(t("classic.forward_caption", stage=labels.get(current_step, current_step)))
    if st.button(
        t(label_key, next=labels.get(target, target)),
        type="primary",
        width='stretch',
        key=f"classic_fwd_{current_step}_{target}",
    ):
        st.session_state[CLASSIC_TAB_FLASH_KEY] = target
        st.rerun()


def render_classic_tab_flash_banner(get_traits_weighted=None) -> None:
    """Підказка відкрити наступну classic-вкладку (Streamlit не перемикає tabs).

    Викликати лише один раз на run (зазвичай app.py над st.tabs) — інакше дубль key.
    """
    target = st.session_state.get(CLASSIC_TAB_FLASH_KEY)
    if not target:
        return
    if get_traits_weighted is not None:
        progress = classic_progress(get_traits_weighted)
        if progress.get(target):
            st.session_state.pop(CLASSIC_TAB_FLASH_KEY, None)
            return
    labels = {s["id"]: f"{s['icon']} {s['label']}" for s in _classic_steps()}
    c1, c2 = st.columns([5, 1])
    with c1:
        st.info(t("classic.tab_flash", tab=labels.get(target, target)))
    with c2:
        if st.button("✕", key="dismiss_classic_tab_flash", help=t("common.dismiss")):
            st.session_state.pop(CLASSIC_TAB_FLASH_KEY, None)
            st.rerun()


def render_post_images_generation_hint() -> None:
    """Після генерації — запропонувати перехід на експорт."""
    progress = pipeline_progress()
    if progress.get("images") and progress.get("billing"):
        render_inline_pipeline_forward("mint", key_suffix="after_gen")


def ordered_tab_ids(mode: str) -> list[str]:
    """Ідентифікатори вкладок у порядку показу для режиму (чиста функція)."""
    if mode == MODE_PIPELINE:
        return ["pipeline", *_TAIL_TAB_IDS, *CLASSIC_TAB_IDS]
    return [*CLASSIC_TAB_IDS, "pipeline", *_TAIL_TAB_IDS]

PIPELINE_STAGE_KEY = "pipeline_active_stage"
# Етап конвеєра дзеркалиться в URL (?stage=) — щоб оновлення браузера лишало
# користувача на тому ж кроці, а не на старті. Працює навіть без гаманця/диску
# (на відміну від autosave у project_service); крок стає й діплінкабельним.
STAGE_QUERY_PARAM = "stage"
PIPELINE_TRANSFER_MSG_KEY = "pipeline_transfer_msg"
HELP_PENDING_SECTION_KEY = "_pending_help_section"
CONFIRM_CLASSIC_MODE_KEY = "_confirm_classic_mode"
# Застосовуються в init_workflow_state() до віджетів (Streamlit забороняє
# змінювати key віджета після його створення в тому ж run).
PENDING_WORKFLOW_KEY = "_pending_workflow_mode"
PENDING_PIPELINE_STAGE_KEY = "_pending_pipeline_stage"
PENDING_WELCOME_KEY = "_pending_welcome"


def _classic_steps() -> tuple[dict, ...]:
    return (
        {"id": "build", "label": t("step.constructor"), "icon": "🛠️"},
        {"id": "traits", "label": t("step.traits"), "icon": "🧬"},
        {"id": "batch", "label": t("step.batch"), "icon": "📦"},
        {"id": "collection", "label": t("step.collection"), "icon": "🏭"},
        {"id": "images", "label": t("step.images_classic"), "icon": "🖼️"},
    )


def _pipeline_steps() -> tuple[dict, ...]:
    # 💳 Кредити першим: гаманець і баланс потрібні ДО генерації (Етап 2).
    return (
        {"id": "billing", "label": t("step.billing"), "icon": "💳"},
        {"id": "text", "label": t("step.text"), "icon": "1️⃣"},
        {"id": "images", "label": t("step.images"), "icon": "2️⃣"},
        {"id": "mint", "label": t("step.mint"), "icon": "3️⃣"},
    )


def pipeline_stage_labels() -> dict[str, str]:
    return {s["id"]: f"{s['icon']} {s['label']}" for s in _pipeline_steps()}


def _request_mode_switch(mode: str, *, pipeline_stage: str | None = None) -> None:
    """Відкласти зміну режиму + синхронізувати widget-ключі й диск.

    Викликати до st.rerun(). Sync build_* ← canonical, щоб після Classic⇄Pipeline
    поле «Основний персонаж» не виглядало порожнім при наявному last_result.
    """
    st.session_state[PENDING_WORKFLOW_KEY] = mode
    if pipeline_stage is not None:
        st.session_state[PENDING_PIPELINE_STAGE_KEY] = pipeline_stage
        st.session_state[PIPELINE_STAGE_KEY] = pipeline_stage
    try:
        from ui.build_panel import sync_build_widget_keys

        sync_build_widget_keys()
    except Exception:
        pass
    try:
        from services import project_service
        from ui import billing_ui

        wallet = billing_ui.connected_wallet()
        if wallet and st.session_state.get(project_service.SESSION_PROJECT_ID):
            # Застосувати pending mode у snapshot до запису на диск.
            st.session_state[WORKFLOW_KEY] = mode
            project_service.persist(wallet)
    except OSError:
        pass


def init_workflow_state() -> None:
    if st.session_state.pop(PENDING_WELCOME_KEY, False):
        st.session_state["welcome_seen"] = False
    if PENDING_WORKFLOW_KEY in st.session_state:
        st.session_state[WORKFLOW_KEY] = st.session_state.pop(PENDING_WORKFLOW_KEY)
        try:
            from ui.build_panel import sync_build_widget_keys

            sync_build_widget_keys()
        except Exception:
            pass
    # PENDING_PIPELINE_STAGE_KEY застосовується в render_pipeline_stage_selector()
    # (безпосередньо перед st.pills), а не тут: між init і конвеєром
    # on_wallet_ready → apply_state може перезаписати етап із диска.
    if WORKFLOW_KEY not in st.session_state:
        st.session_state[WORKFLOW_KEY] = MODE_PIPELINE  # дефолт — рекомендований шлях
    if PIPELINE_STAGE_KEY not in st.session_state:
        # Свіжа сесія (зокрема після оновлення браузера): піднімаємо крок з URL,
        # якщо він там є. Диск (apply_state по гаманцю) пізніше за потреби уточнить.
        st.session_state[PIPELINE_STAGE_KEY] = _query_param_stage() or "billing"


def _apply_pending_pipeline_stage() -> str | None:
    """Підставити відкладений етап ДО st.pills (pending-key + rerun)."""
    pending = st.session_state.pop(PENDING_PIPELINE_STAGE_KEY, None)
    if pending is not None and pending in _PIPELINE_ORDER:
        st.session_state[PIPELINE_STAGE_KEY] = pending
        return pending
    return None


def _query_param_stage() -> str | None:
    """Етап конвеєра з URL (?stage=…), якщо валідний; інакше None.

    Безпечно за відсутності Streamlit-runtime (тести/bare-mode) — повертає None.
    """
    try:
        value = st.query_params.get(STAGE_QUERY_PARAM)
    except Exception:
        return None
    return value if value in _PIPELINE_ORDER else None


def sync_url_stage(stage: str) -> None:
    """Записати активний етап у URL (?stage=) — лише в Pipeline-режимі.

    У Classic ?stage=billing збивав з пантелику (Конструктор/Batch виглядали
    як «Етап billing»). Guard «лише при зміні» унеможливлює цикл reruns.
    """
    if workflow_mode() != MODE_PIPELINE:
        try:
            if STAGE_QUERY_PARAM in st.query_params:
                del st.query_params[STAGE_QUERY_PARAM]
        except Exception:
            pass
        return
    if stage not in _PIPELINE_ORDER:
        return
    try:
        if st.query_params.get(STAGE_QUERY_PARAM) != stage:
            st.query_params[STAGE_QUERY_PARAM] = stage
    except Exception:
        pass


def workflow_mode() -> str:
    return st.session_state.get(WORKFLOW_KEY, MODE_PIPELINE)


def _traits_ready(get_traits_weighted) -> bool:
    return bool(get_traits_weighted())


def _sequential_progress(raw: dict[str, bool], order: tuple[str, ...]) -> dict[str, bool]:
    """Пізніші кроки не «✓», поки попередній у ланцюжку не завершено (BUG-002)."""
    out: dict[str, bool] = {}
    blocked = False
    for step_id in order:
        done = bool(raw.get(step_id)) and not blocked
        out[step_id] = done
        if not done:
            blocked = True
    return out


def classic_progress(get_traits_weighted) -> dict[str, bool]:
    idea = bool((st.session_state.get("idea") or "").strip())
    traits = _traits_ready(get_traits_weighted)
    batch = bool(st.session_state.get("batch_results"))
    run = st.session_state.get("collection_run")
    collection = False
    if run:
        try:
            import collection as coll_mod
            cp = coll_mod.load_checkpoint(run)
            collection = bool(cp and cp.get("results"))
        except Exception:
            collection = False
    previews = bool(st.session_state.get("generated_images")) or batch or collection
    raw = {
        "build": idea or bool(st.session_state.get("active_template")),
        "traits": traits,
        "batch": batch,
        "collection": collection,
        "images": previews,
    }
    return _sequential_progress(raw, CLASSIC_ORDER)


def pipeline_progress() -> dict[str, bool]:
    wallet = bool(st.session_state.get("wallet_address"))
    return {
        "text": bool(st.session_state.get(GENERATED_PROMPTS)),
        "images": bool(st.session_state.get("pipeline_images")),
        "mint": bool(st.session_state.get(APPROVED_CONTENT) or st.session_state.get(MINT_ASSETS)),
        "billing": wallet,
    }


def batch_results_to_pipeline_prompts(results: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in results:
        prompt = (row.get("prompt") or "").strip()
        if not prompt:
            continue
        traits = {
            trait_type_en(str(k)): str(v)
            for k, v in (row.get("traits") or {}).items()
        }
        out.append({
            "prompt": prompt,
            "core": "",
            "style": "",
            "details": [],
            "tags": "",
            "traits": traits,
            "rarity_score": row.get("rarity_score"),
        })
    return out


def collect_classic_image_prompts(
    *,
    image_prompt: str = "",
    prompt_options: dict[str, str] | None = None,
    batch_results: list[dict] | None = None,
) -> list[dict]:
    """Збирає промпти з Classic Images для переносу в Pipeline (D3-lite)."""
    rows: list[dict] = []
    seen: set[str] = set()

    def _add(prompt: str, traits: dict | None = None) -> None:
        p = (prompt or "").strip()
        if not p or p in seen:
            return
        seen.add(p)
        rows.append({"prompt": p, "traits": traits or {}})

    for r in batch_results or []:
        _add(r.get("prompt", ""), r.get("traits"))
    for p in (prompt_options or {}).values():
        _add(p)
    _add(image_prompt)
    return rows


def request_welcome_screen() -> None:
    """Повернути на welcome-гейт (сценарний вибір 1 / 25 / Advanced).

    Через PENDING_* + rerun — той самий патерн, що для етапів конвеєра.
    """
    st.session_state[PENDING_WELCOME_KEY] = True


def render_nav_to_welcome() -> None:
    """Кнопка в sidebar: повернення на початковий екран вибору напряму."""
    if st.button(
        t("nav.choose_direction"),
        width='stretch',
        key="nav_choose_direction",
        help=t("nav.choose_direction_help"),
    ):
        request_welcome_screen()
        st.rerun()


def render_sidebar_mode_selector() -> None:
    """Pipeline за замовчуванням; Classic — лише після підтвердження в expander."""
    mode = workflow_mode()
    if mode == MODE_PIPELINE:
        st.caption(t("workflow.current_pipeline"))
        with st.expander(t("workflow.advanced_expander"), expanded=False):
            st.markdown(t("workflow.advanced_warning"))
            st.checkbox(t("workflow.advanced_confirm"), key=CONFIRM_CLASSIC_MODE_KEY)
            if st.button(t("workflow.switch_to_classic"), width='stretch', key="switch_classic"):
                if st.session_state.get(CONFIRM_CLASSIC_MODE_KEY):
                    _request_mode_switch(MODE_CLASSIC)
                    st.rerun()
                else:
                    st.warning(t("workflow.advanced_confirm_required"))
    else:
        st.warning(t("workflow.classic_active_banner"))
        # Не primary: Ctrl+Enter у text_area/Enter у text_input інакше
        # «сабмітить» цю кнопку → викид у Pipeline + стрибок вкладки (History).
        if st.button(
            t("workflow.switch_to_pipeline"),
            width='stretch',
            key="switch_pipeline",
        ):
            _request_mode_switch(MODE_PIPELINE, pipeline_stage="billing")
            st.rerun()


def pipeline_help_section(_stage: str) -> str:
    """Номер секції довідки (## N.) для етапів конвеєра."""
    return "4"


def classic_help_section(_step_id: str) -> str:
    """Номер секції довідки для classic-вкладок."""
    return "5"


def help_section_expanded(title: str, pending: str | None) -> bool:
    """Чи розгорнути expander довідки (pending = «4» → «4. …»)."""
    if not pending:
        return False
    t0 = title.strip()
    return t0.startswith(f"{pending}.") or t0.startswith(pending)


def queue_help_section(section_num: str) -> None:
    st.session_state[HELP_PENDING_SECTION_KEY] = section_num


def render_contextual_help_link(section_num: str, *, key_suffix: str) -> None:
    """Кнопка «Довідка: цей крок» — розгортає секцію після переходу на вкладку Довідка."""
    if st.button(t("nav.help_this_step"), key=f"ctx_help_{key_suffix}"):
        queue_help_section(section_num)
        st.info(t("nav.help_open_tab"))


def _step_bar(steps: tuple, progress: dict[str, bool], current_id: str | None) -> None:
    parts: list[str] = []
    for step in steps:
        done = progress.get(step["id"], False)
        active = step["id"] == current_id
        if active:
            mark, style = "▶", "font-weight:700;color:#9e8cfc"
        elif done:
            mark, style = "✓", "color:#30a46c"
        else:
            mark, style = "○", "color:#5a6072"
        parts.append(f'<span style="{style}">{mark} {step["icon"]} {step["label"]}</span>')
    st.markdown(" → ".join(parts), unsafe_allow_html=True)


def render_classic_header(current_step: str, get_traits_weighted) -> None:
    progress = classic_progress(get_traits_weighted)
    st.caption(t("workflow.classic_caption"))
    _step_bar(_classic_steps(), progress, current_step)
    hints = _classic_next_hint(current_step, progress)
    if hints:
        st.info(hints)
        render_contextual_help_link(
            classic_help_section(current_step),
            key_suffix=f"classic_{current_step}",
        )


def render_pipeline_header(current_step: str) -> None:
    progress = pipeline_progress()
    st.caption(t("workflow.pipeline_caption"))
    hints = _pipeline_next_hint(current_step, progress)
    if hints:
        st.info(hints)
    cta = pipeline_hint_cta(current_step, progress)
    if cta:
        label_key, target = cta
        # Активна підказка (UX-B8): хінт каже «потрібен X» — кнопка веде туди.
        if st.button(t(label_key), key=f"hint_cta_{target}", type="primary"):
            st.session_state[PENDING_PIPELINE_STAGE_KEY] = target
            st.rerun()


def _classic_next_hint(current: str, progress: dict[str, bool]) -> str:
    if current == "build":
        if not progress["build"]:
            return t("hint.classic.build.start")
        if not progress["traits"]:
            return t("hint.classic.build.traits")
        return t("hint.classic.build.ready")
    if current == "traits":
        if not progress["traits"]:
            return t("hint.classic.traits.empty")
        if not progress["build"]:
            return t("hint.classic.traits.no_idea")
        return t("hint.classic.traits.ready")
    if current == "batch":
        if not progress["batch"]:
            return t("hint.classic.batch.empty")
        return t("hint.classic.batch.ready")
    if current == "collection":
        if not progress["collection"]:
            return t("hint.classic.collection.empty")
        return t("hint.classic.collection.ready")
    if current == "images":
        return t("hint.classic.images")
    return ""


def _pipeline_next_hint(current: str, progress: dict[str, bool]) -> str:
    if current == "text":
        if not progress["text"]:
            return t("hint.pipeline.text.empty")
        if not progress["billing"]:
            return t("hint.pipeline.text.wallet")
        return t("hint.pipeline.text.ready")
    if current == "images":
        if not progress["billing"]:
            return t("hint.pipeline.images.wallet")
        if not progress["text"]:
            return t("hint.pipeline.images.no_prompts")
        if not progress["images"]:
            return t("hint.pipeline.images.generate")
        if not progress["mint"]:
            return t("hint.pipeline.images.approve")
        return t("hint.pipeline.images.mint")
    if current == "mint":
        if not progress["mint"]:
            return t("hint.pipeline.mint.empty")
        return t("hint.pipeline.mint.ready")
    if current == "billing":
        return t("hint.pipeline.billing")
    return ""


def pipeline_hint_cta(current: str, progress: dict[str, bool]) -> tuple[str, str] | None:
    """CTA під хінтом: (i18n-ключ підпису, цільовий етап) або None (UX-B8).

    Веде ПРЯМО на етап, що знімає поточний блокер — на відміну від сусідньої
    навігації `render_pipeline_nav` (Назад/Далі). Напр. гаманець потрібен і на
    Промптах, і на Зображеннях; кнопка стрибає на 💳 з будь-якого з них. Не
    дублює generic-навігацію: для «йти далі по готовому» вже є «Далі →».
    """
    if current == "billing":
        if not progress.get("billing"):
            return None
        # Welcome/шаблон уже наповнили промпти — одразу на Зображення.
        if progress.get("text"):
            return "cta.to_images", "images"
        return "cta.to_prompts", "text"
    if current == "text":
        # Промпти є, але без гаманця наступний етап закрито → веди до 💳.
        if progress.get("text") and not progress.get("billing"):
            return "cta.connect_wallet", "billing"
        return None
    if current == "images":
        if not progress.get("billing"):
            return "cta.connect_wallet", "billing"
        if not progress.get("text"):
            return "cta.write_prompts", "text"
        if progress.get("images") and not progress.get("mint"):
            return "cta.to_export", "mint"
        return None
    if current == "mint":
        # Є гаманець, але ще немає контенту — upload на цьому ж етапі (не назад).
        if progress.get("billing") and not progress.get("mint"):
            return None
        if not progress.get("mint"):
            return "cta.back_to_images", "images"
        return None
    return None


# Лінійний порядок етапів конвеєра (UX-B1 wizard). Збігається з _pipeline_steps.
_PIPELINE_ORDER = ("billing", "text", "images", "mint")


def stage_accessible(stage: str, progress: dict[str, bool]) -> bool:
    """Чи доступний етап за поточним прогресом (gate-таблиця UX-B1).

    billing/text — завжди; images — гаманець + ≥1 промпт;
    mint (Експорт) — гаманець (контент: approve на Етапі 2 або upload тут).
    """
    if stage == "images":
        return bool(progress.get("text") and progress.get("billing"))
    if stage == "mint":
        return bool(progress.get("billing"))
    return True


def stage_block_message(stage: str, progress: dict[str, bool]) -> str:
    """Пояснення, чому етап заблоковано (порожній рядок = доступний)."""
    if stage_accessible(stage, progress):
        return ""
    if stage == "images":
        if not progress.get("billing"):
            return t("gate.images.wallet")
        return t("gate.images.prompts")
    if stage == "mint":
        return t("gate.mint.wallet")
    return ""


def adjacent_stage(current: str, delta: int) -> str | None:
    """Сусідній етап у лінійному порядку (delta -1/+1) або None на краю."""
    try:
        i = _PIPELINE_ORDER.index(current)
    except ValueError:
        return None
    j = i + delta
    return _PIPELINE_ORDER[j] if 0 <= j < len(_PIPELINE_ORDER) else None


def adjacent_accessible_stage(
    current: str, delta: int, progress: dict[str, bool],
) -> str | None:
    """Наступний/попередній *доступний* етап (пропускає заблоковані gates).

    Вперед також пропускає етапи, чий результат уже є (напр. промпти з welcome).
    """
    try:
        i = _PIPELINE_ORDER.index(current)
    except ValueError:
        return None
    step = 1 if delta > 0 else -1
    j = i + step
    while 0 <= j < len(_PIPELINE_ORDER):
        candidate = _PIPELINE_ORDER[j]
        if not stage_accessible(candidate, progress):
            j += step
            continue
        if step > 0 and _stage_result_done(candidate, progress):
            j += step
            continue
        return candidate
    return None


def _stage_result_done(stage: str, progress: dict[str, bool]) -> bool:
    """Чи вже є результат етапу (для пропуску вперед по майстру)."""
    if stage == "billing":
        return bool(progress.get("billing"))
    if stage == "text":
        return bool(progress.get("text"))
    if stage == "images":
        return bool(progress.get("images"))
    if stage == "mint":
        return bool(progress.get("mint"))
    return False


def _md_bold_to_html(text: str) -> str:
    """`**жирний**` → `<strong>жирний</strong>` для вставки в raw-HTML контейнер."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def render_pipeline_empty_state(current: str, progress: dict[str, bool]) -> None:
    """Орієнтир «Зараз → Далі → Чому» для доступного, але порожнього етапу (UX-B4).

    Показуємо лише коли етап НЕ заблоковано (gate) і ще немає його результату —
    щоб новачок (після welcome-гейту) не дивився на порожню форму без контексту.
    """
    if stage_block_message(current, progress):
        return  # заблокований етап уже показує власне пояснення
    body: str | None = None
    if current == "billing" and not progress.get("billing"):
        body = t("empty.pipeline.billing")
    elif current == "text" and not progress.get("text"):
        body = t("empty.pipeline.text")
    elif current == "images" and not progress.get("images"):
        body = t("empty.pipeline.images")
    elif current == "mint" and not progress.get("mint"):
        body = t("empty.pipeline.mint")
    if not body:
        return
    # body тримаємо в markdown-стилі (`**...**`) як решта рядків, але вставляємо
    # у raw-HTML div (metric-card) — там CommonMark НЕ парсить markdown, тож
    # конвертуємо жирний у <strong> вручну (інакше зірочки видно літерально).
    st.markdown(f'<div class="metric-card">{_md_bold_to_html(body)}</div>', unsafe_allow_html=True)
    render_contextual_help_link(pipeline_help_section(current), key_suffix=f"empty_{current}")


def pipeline_forward_action(current: str, progress: dict[str, bool]) -> tuple[str, str] | None:
    """Кнопка «наступний етап» після завершення поточного (не для блокерів).

    Повертає (i18n-ключ підпису, цільовий етап) або None.
    """
    if current == "billing" and progress.get("billing"):
        if progress.get("text"):
            return "cta.forward.images", "images"
        return "cta.forward.prompts", "text"
    if current == "text" and progress.get("text") and progress.get("billing"):
        return "cta.forward.images", "images"
    if current == "images" and progress.get("images") and progress.get("billing"):
        return "cta.forward.export", "mint"
    return None


def render_pipeline_forward_cta(current: str) -> None:
    """Помітна кнопка переходу на наступний етап після завершення роботи (UX-B9)."""
    progress = pipeline_progress()
    if stage_block_message(current, progress):
        return
    action = pipeline_forward_action(current, progress)
    if not action:
        return
    label_key, target = action
    labels = pipeline_stage_labels()
    st.divider()
    st.caption(t("pipeline.forward_caption", stage=labels.get(current, current)))
    if st.button(
        t(label_key, next_stage=labels.get(target, target)),
        type="primary",
        width='stretch',
        key=f"pipe_forward_{current}_{target}",
    ):
        st.session_state[PENDING_PIPELINE_STAGE_KEY] = target
        st.rerun()


def render_pipeline_nav(current: str) -> None:
    """Кнопки «← Назад» / «Далі →» поруч зі step bar (лінійний wizard, UX-B1).

    Перемикання — через PENDING-ключ + rerun (Streamlit widget-key safe).
    «Далі» пропускає заблоковані етапи (напр. Export без approve — лише з гаманцем).
    """
    labels = pipeline_stage_labels()
    progress = pipeline_progress()
    prev_s = adjacent_accessible_stage(current, -1, progress)
    next_s = adjacent_accessible_stage(current, +1, progress)
    c1, c2 = st.columns(2)
    with c1:
        if prev_s and st.button(f"← {labels[prev_s]}", width='stretch', key="pipe_back"):
            st.session_state[PENDING_PIPELINE_STAGE_KEY] = prev_s
            st.rerun()
    with c2:
        if next_s and st.button(f"{labels[next_s]} →", width='stretch',
                                type="primary", key="pipe_next"):
            st.session_state[PENDING_PIPELINE_STAGE_KEY] = next_s
            st.rerun()


def set_pending_mode(mode: str, stage: str | None = None) -> None:
    """Відкласти перемикання режиму (і опц. етапу конвеєра) до наступного run.

    Streamlit забороняє міняти key віджета в тому ж run, тож пишемо у PENDING_*
    ключі — init_workflow_state() застосує їх на наступному ререндері. Для
    welcome-сценаріїв (UX-A3) і будь-якого програмного перемикання шляху.
    """
    st.session_state[PENDING_WORKFLOW_KEY] = mode
    if stage is not None:
        st.session_state[PENDING_PIPELINE_STAGE_KEY] = stage


def goto_pipeline_stage(stage: str, results: list[dict], source: str = "") -> int:
    converted = batch_results_to_pipeline_prompts(results)
    st.session_state[GENERATED_PROMPTS] = converted
    st.session_state[PENDING_WORKFLOW_KEY] = MODE_PIPELINE
    st.session_state[PENDING_PIPELINE_STAGE_KEY] = stage
    src = f" ({source})" if source else ""
    labels = pipeline_stage_labels()
    st.session_state[PIPELINE_TRANSFER_MSG_KEY] = t(
        "workflow.transfer_msg",
        count=len(converted),
        source=src,
        stage=labels.get(stage, stage),
    )
    return len(converted)


def render_transfer_banner() -> None:
    msg = st.session_state.get(PIPELINE_TRANSFER_MSG_KEY)
    if not msg:
        return
    c1, c2 = st.columns([5, 1])
    with c1:
        st.success(msg)
    with c2:
        if st.button("✕", key="dismiss_pipeline_transfer", help=t("common.dismiss")):
            st.session_state.pop(PIPELINE_TRANSFER_MSG_KEY, None)
            st.rerun()


def pipeline_stage_button_label(stage_id: str, labels: dict[str, str], progress: dict[str, bool]) -> str:
    """Підпис кнопки етапу конвеєра (✓ якщо етап виконано)."""
    text = labels.get(stage_id, stage_id)
    return f"✓ {text}" if progress.get(stage_id) else text


def _persist_pipeline_stage_to_disk() -> None:
    """Миттєвий autosave етапу конвеєра — інакше при збої sidebar до кінця run
    на диску лишається billing і load_project «скидає» на Кредити."""
    from services import project_service
    from ui import billing_ui

    wallet = billing_ui.connected_wallet()
    if wallet and st.session_state.get(project_service.SESSION_PROJECT_ID):
        try:
            project_service.persist(wallet)
        except OSError:
            pass


def render_pipeline_stage_selector() -> str:
    """Клікабельні етапи конвеєра (pills замість дубльованого radio + step bar)."""
    # Classic: не чіпати pills/URL — інакше ?stage=billing «липне» на всіх вкладках.
    if workflow_mode() != MODE_PIPELINE:
        sync_url_stage("")  # прибирає ?stage= з URL
        return st.session_state.get(PIPELINE_STAGE_KEY) or "billing"
    jumped = _apply_pending_pipeline_stage()
    labels = pipeline_stage_labels()
    progress = pipeline_progress()
    options = [s["id"] for s in _pipeline_steps()]
    selected = st.pills(
        t("pipeline.stage_radio"),
        options,
        format_func=lambda k: pipeline_stage_button_label(k, labels, progress),
        selection_mode="single",
        key=PIPELINE_STAGE_KEY,
        on_change=_persist_pipeline_stage_to_disk,
    )
    # Після programmatic jump не перезаписувати pills stale-значенням (BUG pending).
    if jumped is None and selected and st.session_state.get(PIPELINE_STAGE_KEY) != selected:
        st.session_state[PIPELINE_STAGE_KEY] = selected
    stage = st.session_state.get(PIPELINE_STAGE_KEY) or selected or "billing"
    sync_url_stage(stage)  # тримаємо URL у синхроні → рефреш лишає на цьому кроці
    return stage


def render_pipeline_bridge(
    results: list[dict],
    key_prefix: str,
    source: str = "Batch",
    default_limit: int = 100,
) -> None:
    if not results:
        return
    total = len(results)
    st.divider()
    st.markdown(t("workflow.bridge_title"))
    st.caption(t("workflow.bridge_caption"))
    limit = total
    if total > default_limit:
        limit = st.number_input(
            t("workflow.bridge_limit"),
            1, total, min(default_limit, total),
            key=f"{key_prefix}_bridge_limit",
        )
    if st.button(
        t("workflow.bridge_btn", limit=int(limit), total=total),
        type="primary",
        width='stretch',
        key=f"{key_prefix}_bridge_btn",
    ):
        goto_pipeline_stage("images", results[: int(limit)], source=source)
        st.rerun()


def render_batch_to_pipeline_bridge(batch_results: list[dict]) -> None:
    render_pipeline_bridge(batch_results, "batch", source="Batch")


def render_images_to_pipeline_bridge(
    *,
    image_prompt: str = "",
    prompt_options: dict[str, str] | None = None,
    batch_results: list[dict] | None = None,
) -> None:
    """D3-lite: CTA з Classic Images → Pipeline Етап 2 (без merge генераторів)."""
    rows = collect_classic_image_prompts(
        image_prompt=image_prompt,
        prompt_options=prompt_options,
        batch_results=batch_results,
    )
    if rows:
        render_pipeline_bridge(rows, "images_tab", source="Images")
        return
    st.divider()
    st.markdown(t("workflow.bridge_title"))
    st.caption(t("img.pipeline_bridge_caption"))
    st.caption(t("img.pipeline_no_prompts"))
