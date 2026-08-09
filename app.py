import asyncio
import concurrent.futures
import os
import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

import network_config
import storage
import theme
from secrets_env import get_secret, has_secret, load_project_env
from batch import (
    build_metadata,
    build_metadata_metaplex,
    count_combinations,
    generate_batch_async,
    is_claude_model,
    parse_trait_lines,
    sample_trait_combinations,
)
from builder import build_tech_params
import importlib

import services.template_pipeline as template_pipeline

# Streamlit кешує services.* у sys.modules між rerun — після деплою/змін
# template_pipeline без рестарту процесу лишається стара версія модуля.
if not hasattr(template_pipeline, "archetype_session_hints"):
    importlib.reload(template_pipeline)
from i18n import default_mint_collection_name
from options import TRAIT_CATEGORIES, trait_key
from templates import COLLECTION_TEMPLATES
from state.app_defaults import DEFAULTS
from state.pipeline_state import GENERATED_PROMPTS, init_pipeline_state
from services import admin_access, billing_guard, gateway_guard, payment_service, project_service
from ui import admin_panel, batch_panel, billing_ui, build_panel, collection_panel, cost_calculator, footer, help_center, history_panel, images_panel, mini_drop_guides, page_meta, pipeline_panel, sidebar as sidebar_ui, traits_panel, workflow_guide
from ui_strings import t

load_project_env()


def _hydrate_streamlit_secrets() -> None:
    try:
        for key in (
            "OPENAI_API_KEY", "PINATA_JWT", "ANTHROPIC_API_KEY",
            "STABILITY_API_KEY", "REPLICATE_API_TOKEN",
            "HELIO_API_KEY", "HELIO_API_SECRET",
            "HELIO_PAYLINK_START", "HELIO_PAYLINK_CREATOR", "HELIO_PAYLINK_PRO",
        ):
            if key in st.secrets and st.secrets[key]:
                os.environ.setdefault(key, str(st.secrets[key]))
    except Exception:
        pass


_hydrate_streamlit_secrets()
# Paylink з .env після hydrate — secrets.toml не має перебивати оновлені ID.
load_project_env(force=True)
network_config.init()  # temp_assets/ для зображень конвеєра (оптимізація пам'яті)


def _run_async(coro):
    """Виконує корутину в окремому потоці з прив'язаним ScriptRunContext."""
    ctx = get_script_run_ctx()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        initializer=lambda: add_script_run_ctx(threading.current_thread(), ctx),
    ) as pool:
        return pool.submit(asyncio.run, coro).result()


_BRAND_ICON = os.path.join(os.path.dirname(__file__), "assets", "brand", "w3ir-favicon.svg")
st.set_page_config(
    page_title="Professional NFT Prompt Builder",
    page_icon=_BRAND_ICON if os.path.isfile(_BRAND_ICON) else "🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)
page_meta.inject_page_meta()

theme.apply_theme()

def _init_state() -> None:
    for key, val in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val
    for cat in TRAIT_CATEGORIES:
        if trait_key(cat) not in st.session_state:
            st.session_state[trait_key(cat)] = ""
    if "history" not in st.session_state:
        st.session_state.history = []  # справжню історію гаманця вантажимо після adopt
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "batch_results" not in st.session_state:
        st.session_state.batch_results = []
    if "batch_usage" not in st.session_state:
        st.session_state.batch_usage = None
    if "active_template" not in st.session_state:
        st.session_state.active_template = None
    if "generated_images" not in st.session_state:
        st.session_state.generated_images = []
    if "collection_run" not in st.session_state:
        st.session_state.collection_run = None
    if "image_prompt_edit" not in st.session_state:
        st.session_state.image_prompt_edit = ""
    if "session_cost" not in st.session_state:
        st.session_state.session_cost = 0.0
    if billing_ui.SESSION_CREDITS_KEY not in st.session_state:
        st.session_state[billing_ui.SESSION_CREDITS_KEY] = 0
    init_pipeline_state()
    workflow_guide.init_workflow_state()


def _load_wallet_history() -> None:
    """Вантажить історію поточного гаманця в session_state (після adopt).

    Історія розмежована по гаманцю, а гаманець стає відомий лише після
    adopt_gateway_wallet(), тож завантажуємо тут, не в _init_state. Перезавантаж
    лише коли гаманець змінився (вхід/перемикання) — щоб не затирати правки сесії.
    """
    wallet = billing_ui.connected_wallet()
    if st.session_state.get("_history_wallet") != wallet:
        st.session_state.history = storage.load_history(wallet)
        st.session_state["_history_wallet"] = wallet


_REF_PENDING_KEY = "_referral_ref"
_REF_DONE_KEY = "_referral_recorded"


def _capture_referral() -> None:
    """Прив'язує реферера з ?ref=<code|wallet> до поточного гаманця (G3.3, після adopt).

    `ref` стежимо в session (query-параметри можуть зникнути після rerun чи
    SIWE-редіректу), а зв'язок створюємо щойно відомий власний гаманець. `ref`
    може бути опаковим реферал-кодом (shareable-сторінка, privacy) або прямою
    адресою (старі посилання) — resolve_referrer розбирає обидва. Бонус рефереру
    нараховується пізніше — лише за першу оплату invitee (анти-Sybil).
    """
    if _REF_PENDING_KEY not in st.session_state:
        st.session_state[_REF_PENDING_KEY] = st.query_params.get("ref", "") or ""
    ref = st.session_state[_REF_PENDING_KEY]
    if not ref or st.session_state.get(_REF_DONE_KEY):
        return
    wallet = billing_ui.connected_wallet()
    if not wallet:
        return  # гаманець ще невідомий — спробуємо на наступному rerun
    referrer = payment_service.resolve_referrer(ref)  # код→гаманець або адреса як є
    if referrer:
        payment_service.record_referral(wallet, referrer)  # тихо ігнорує самореферал
    st.session_state[_REF_DONE_KEY] = True


_init_state()
gateway_guard.enforce()  # SIWE-гард (opt-in: AUTH_GATEWAY_ENFORCE=1)
billing_ui.adopt_gateway_wallet()  # один вхід: гаманець гейтвея = гаманець білінгу
_load_wallet_history()  # історія/проєкти/превʼю розмежовані по гаманцю — після adopt
_wallet = billing_ui.connected_wallet()
# welcome_seen на диску — не показувати гейт у новій сесії; «Обрати шлях» лишає False.
if (
    _wallet
    and project_service.welcome_seen_persisted(_wallet)
    and st.session_state.get("welcome_seen") is not False
):
    st.session_state["welcome_seen"] = True
_capture_referral()  # G3.3: зв'язати ?ref=<wallet> з поточним гаманцем


# ── API key helpers ────────────────────────────────────────────────────────────

def has_persistent_api_key() -> bool:
    return has_secret("OPENAI_API_KEY")


def get_api_key() -> str | None:
    return get_secret("OPENAI_API_KEY") or st.session_state.get("api_key_input")


def has_persistent_anthropic_key() -> bool:
    return has_secret("ANTHROPIC_API_KEY")


def get_anthropic_key() -> str | None:
    return get_secret("ANTHROPIC_API_KEY") or st.session_state.get("anthropic_key_input")


def get_llm_api_key(model: str) -> str | None:
    """Повертає правильний ключ залежно від провайдера моделі."""
    return get_anthropic_key() if is_claude_model(model) else get_api_key()


def _billing_error(code: str | None) -> None:
    if code == "wallet":
        st.error(t("pl2.connect_wallet"))
    elif code == "unverified":
        st.error(t("pl2.unverified_wallet"))
    elif code == "credits":
        st.error(t("pl2.low_credits"))
    elif code == "rate":
        st.error(t("pl2.rate_limit", rate=payment_service.RATE_LIMIT_PER_MINUTE))
    elif code == "freemium":
        st.error(t("pl2.freemium_limit"))


def _reserve_llm(wallet: str | None, units: int, note: str) -> bool:
    cost = billing_guard.CREDIT_COST_LLM * units
    ok, err = billing_guard.try_reserve(wallet, cost, engine="LLM", note=note)
    if not ok:
        _billing_error(err)
    return ok


def _refund_llm(wallet: str | None, units: int, note: str) -> None:
    billing_guard.refund(wallet, billing_guard.CREDIT_COST_LLM * units, engine="LLM", note=note)


# ── Single-call LLM (Constructor tab) ─────────────────────────────────────────



def apply_template(name: str) -> None:
    tpl = COLLECTION_TEMPLATES[name]
    for field in ("idea", "style", "camera", "lighting", "background", "quality", "mood", "aspect_ratio", "stylize", "chaos"):
        st.session_state[field] = tpl[field]
    st.session_state.collection_size = tpl["collection_size"]
    st.session_state.active_template = name
    sidebar_ui.queue_template_pick_reset()
    # Калькулятор вартості — той самий supply, що й сценарій welcome/шаблон.
    st.session_state["cost_calc_supply"] = int(tpl["collection_size"])
    for key, val in template_pipeline.ui_session_from_template(tpl).items():
        st.session_state[key] = val
    for key, val in template_pipeline.widget_keys_from_template(tpl).items():
        st.session_state[key] = val
    # ПЛАН_NFT_РЕЗУЛЬТАТ.md § A5: одразу готуємо Stage 1 + Style Bible з шаблону.
    st.session_state[GENERATED_PROMPTS] = template_pipeline.prompts_from_template(tpl)
    bible = template_pipeline.bible_from_template(tpl)
    for key, val in template_pipeline.archetype_session_hints(tpl).items():
        st.session_state[key] = val
    st.session_state["_pl2_suffix_auto_sig"] = bible.bible_text()
    wallet = billing_ui.connected_wallet()
    if wallet:
        project_service.set_style_bible(bible.to_dict())
        project_service.persist(wallet)
    if mini_drop_guides.is_mini_drop(name):
        mini_drop_guides.queue_guide_expanded()


def _complete_welcome(wallet: str | None) -> None:
    """Закрити welcome-гейт у сесії та на диску (per-wallet)."""
    st.session_state.welcome_seen = True
    if wallet:
        project_service.set_welcome_seen(wallet)


def _welcome_start_project(*, mode: str, stage: str = "billing") -> None:
    """Новий дроп з welcome: завжди новий проєкт (свідомий вибір сценарію)."""
    wallet = billing_ui.connected_wallet()
    if wallet:
        project_service.create_project(wallet)
    _complete_welcome(wallet)
    workflow_guide.set_pending_mode(mode, stage)


def _welcome_continue_last(wallet: str) -> None:
    """Продовжити останній активний проєкт без шаблону й без нового id."""
    _complete_welcome(wallet)
    project_service.ensure_active(wallet)


def _welcome_pick_template(template_name: str) -> None:
    """Старт міні-дропу з welcome: новий проєкт + застосувати шаблон."""
    _welcome_start_project(mode=workflow_guide.MODE_PIPELINE)
    apply_template(template_name)
    project_service.persist(billing_ui.connected_wallet())
    st.rerun()


def render_welcome() -> None:
    """Welcome-гейт першого візиту (UX-A3): сценарний вибір 1 / 25 / Advanced.

    Викликати ПЕРЕД sidebar (apply_template виставляє widget-key collection_size,
    який ще не створено цього run) і завершити st.stop(). Дисміс — у session
    (welcome_seen). Кожна кнопка веде на правильний сценарій через PENDING_*.
    """
    st.markdown(t("welcome.title"))
    st.markdown(t("welcome.subtitle"))
    st.caption(t("welcome.pilot_playbook"))
    wallet = billing_ui.connected_wallet()
    if wallet and project_service.has_saved_projects(wallet):
        st.info(t("welcome.continue_hint"))
        if st.button(
            t("welcome.continue"),
            width='stretch',
            type="primary",
            key="welcome_continue",
        ):
            _welcome_continue_last(wallet)
            st.rerun()
        st.divider()
        st.caption(t("welcome.new_drop_caption"))
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption(t("welcome.one_desc"))
        if st.button(t("welcome.one"), width='stretch', key="welcome_one"):
            _welcome_start_project(mode=workflow_guide.MODE_PIPELINE)
            apply_template("1/1 Fine Art")
            project_service.persist(billing_ui.connected_wallet())
            st.rerun()
        with st.expander(t("welcome.guide_label")):
            st.markdown(t("welcome.one_guide"))
    with col2:
        st.caption(t("welcome.batch_desc"))
        if st.button(t("welcome.batch"), width='stretch', key="welcome_batch"):
            # «W3IR Showcase Demo» — admin-only (staging). Звичайні користувачі
            # стартують сценарій 25-дропу на публічному шаблоні з тим самим обсягом.
            _welcome_start_project(mode=workflow_guide.MODE_PIPELINE)
            if admin_access.is_admin(billing_ui.connected_wallet()):
                apply_template("W3IR Showcase Demo")
            else:
                apply_template("Abstract Geometry Series")
            project_service.persist(billing_ui.connected_wallet())
            st.rerun()
        with st.expander(t("welcome.guide_label")):
            st.markdown(t("welcome.batch_guide"))
    with col3:
        st.caption(t("welcome.advanced_desc"))
        if st.button(t("welcome.advanced"), width='stretch', key="welcome_advanced"):
            if wallet:
                project_service.create_project(wallet)
            _complete_welcome(wallet)
            workflow_guide.set_pending_mode(workflow_guide.MODE_CLASSIC)
            if wallet:
                project_service.persist(wallet)
            st.rerun()
        with st.expander(t("welcome.guide_label")):
            st.markdown(t("welcome.advanced_guide"))
    st.markdown(t("welcome.archetype_row_title"))
    col4, col5, col6 = st.columns(3)
    with col4:
        st.caption(t("welcome.landscape_desc"))
        if st.button(t("welcome.landscape"), width='stretch', key="welcome_landscape"):
            _welcome_pick_template("Atmospheric Worlds")
        with st.expander(t("welcome.guide_label")):
            st.markdown(t("welcome.landscape_guide"))
    with col5:
        st.caption(t("welcome.event_desc"))
        if st.button(t("welcome.event"), width='stretch', key="welcome_event"):
            _welcome_pick_template("Event Badge Series")
        with st.expander(t("welcome.guide_label")):
            st.markdown(t("welcome.event_guide"))
    with col6:
        st.caption(t("welcome.brand_desc"))
        if st.button(t("welcome.brand"), width='stretch', key="welcome_brand"):
            _welcome_pick_template("Brand Icon System")
        with st.expander(t("welcome.guide_label")):
            st.markdown(t("welcome.brand_guide"))
    st.markdown(t("welcome.more_mini_title"))
    st.caption(t("welcome.more_mini_caption"))
    row3a = st.columns(4)
    _more_mini = (
        ("welcome.glitch", "welcome.glitch_desc", "Glitch Geometry"),
        ("welcome.sumie", "welcome.sumie_desc", "Sumi-e Ink Studies"),
        ("welcome.chibi", "welcome.chibi_desc", "Chibi Champs"),
        ("welcome.vinyl", "welcome.vinyl_desc", "Vinyl Toy Squad"),
    )
    for col, (label_key, desc_key, tpl_name) in zip(row3a, _more_mini):
        with col:
            st.caption(t(desc_key))
            slug = tpl_name.replace("/", "_").replace(" ", "_")
            if st.button(t(label_key), width='stretch', key=f"welcome_tpl_{slug}"):
                _welcome_pick_template(tpl_name)
    row3b = st.columns(3)
    _more_mini_b = (
        ("welcome.retro", "welcome.retro_desc", "Retro Poster Series"),
        ("welcome.chrome", "welcome.chrome_desc", "Chrome Fashion Icons"),
        ("welcome.artdeco", "welcome.artdeco_desc", "Art Deco Medallions"),
    )
    for col, (label_key, desc_key, tpl_name) in zip(row3b, _more_mini_b):
        with col:
            st.caption(t(desc_key))
            slug = tpl_name.replace("/", "_").replace(" ", "_")
            if st.button(t(label_key), width='stretch', key=f"welcome_tpl_{slug}"):
                _welcome_pick_template(tpl_name)
    if st.button(t("welcome.dismiss"), key="welcome_dismiss"):
        _complete_welcome(wallet)
        if wallet:
            if project_service.has_saved_projects(wallet):
                project_service.ensure_active(wallet)
            else:
                workflow_guide.set_pending_mode(workflow_guide.MODE_PIPELINE, "billing")
                project_service.create_project(wallet)
                apply_template("1/1 Fine Art")
                project_service.persist(wallet)
        st.rerun()


def collect_config() -> dict:
    config = {key: st.session_state[key] for key in DEFAULTS}
    config["traits"] = {cat: st.session_state[trait_key(cat)] for cat in TRAIT_CATEGORIES}
    config["active_template"] = st.session_state.active_template
    return config


def apply_config(config: dict) -> None:
    for key in DEFAULTS:
        if key in config:
            st.session_state[key] = config[key]
    for cat, raw in config.get("traits", {}).items():
        if cat in TRAIT_CATEGORIES:
            st.session_state[trait_key(cat)] = raw
    st.session_state.active_template = config.get("active_template")


def get_traits_weighted() -> dict[str, list[tuple[str, float]]]:
    result = {}
    for cat in TRAIT_CATEGORIES:
        items = parse_trait_lines(st.session_state.get(trait_key(cat), ""))
        if items:
            result[cat] = items
    return result


def get_base_config() -> dict:
    return {
        "idea": st.session_state.idea,
        "style": st.session_state.style,
        "camera": st.session_state.camera,
        "lighting": st.session_state.lighting,
        "background": st.session_state.background,
        "quality": st.session_state.quality,
        "mood": st.session_state.mood,
        "extra_notes": st.session_state.extra_notes,
    }


def render_pipeline_context(traits_weighted: dict | None = None) -> None:
    if traits_weighted is None:
        traits_weighted = get_traits_weighted()
    parts: list[str] = []
    if st.session_state.get("active_template"):
        parts.append(COLLECTION_TEMPLATES[st.session_state.active_template]["label"])
    idea = st.session_state.idea or ""
    parts.append(idea[:45] + ("…" if len(idea) > 45 else "") if idea else t("classic.ctx_no_idea"))
    parts.append(st.session_state.aspect_ratio.split(" (")[0])
    parts.append(f"--s {st.session_state.stylize} · --c {st.session_state.chaos}")
    notes = (st.session_state.extra_notes or "").strip()
    if notes:
        parts.append(t("classic.ctx_notes", text=notes[:40] + ("…" if len(notes) > 40 else "")))
    if traits_weighted:
        parts.append(t("classic.ctx_combos", n=count_combinations(traits_weighted)))
    st.caption(t("classic.ctx_prefix") + " " + " · ".join(parts))


def render_metadata_form(
    results: list[dict],
    key_prefix: str,
    default_idea: str = "",
    default_base_uri: str = "",
) -> list[dict]:
    """Рендерить форму метаданих і повертає побудований список metadata."""
    meta_standard = st.radio(
        t("meta.standard"), ["ERC-721 / OpenSea (Ethereum)", "Metaplex (Solana)"],
        horizontal=True, key=f"{key_prefix}_meta_standard",
    )
    m1, m2 = st.columns(2)
    with m1:
        meta_name = st.text_input(
            t("meta.name"),
            value=default_mint_collection_name(default_idea),
            key=f"{key_prefix}_meta_name",
        )
        meta_desc = st.text_input(t("meta.desc"), value="", key=f"{key_prefix}_meta_desc")
    with m2:
        meta_base_uri = st.text_input(
            t("meta.base_uri"),
            value=default_base_uri,
            placeholder="ipfs://Qm…/ або https://…/",
            help=t("meta.base_uri_help"),
            key=f"{key_prefix}_meta_uri",
        )
    if "Metaplex" in meta_standard:
        mp1, mp2, mp3 = st.columns(3)
        with mp1:
            meta_symbol = st.text_input(
                t("meta.symbol"), value="", placeholder="APES", max_chars=10, key=f"{key_prefix}_meta_symbol"
            )
        with mp2:
            meta_royalty = st.number_input(t("meta.royalty"), 0.0, 50.0, 5.0, 0.5, key=f"{key_prefix}_meta_royalty")
        with mp3:
            meta_creator = st.text_input(
                t("meta.creator"), value="", placeholder="optional", key=f"{key_prefix}_meta_creator"
            )
        return build_metadata_metaplex(
            results, meta_name, meta_symbol, meta_desc, meta_base_uri,
            int(meta_royalty * 100), meta_creator.strip(),
        )
    return build_metadata(results, meta_name, meta_desc, meta_base_uri)


def run_batch_generation(api_key: str, model: str, platform: str, count: int, temperature: float):
    traits = get_traits_weighted()
    if not traits:
        raise ValueError(t("batch.no_traits_err"))

    combos = sample_trait_combinations(traits, count)
    base = get_base_config()
    tech = build_tech_params(
        platform,
        st.session_state.aspect_ratio,
        st.session_state.stylize,
        st.session_state.chaos,
        st.session_state.seed,
    )

    progress = st.progress(0, text=t("batch.progress"))

    def on_progress(done: int, total: int) -> None:
        progress.progress(done / total, text=t("batch.blocks_done", done=done, total=total))

    results, usage, errors = _run_async(
        generate_batch_async(
            api_key, model, platform, base, combos, tech, temperature,
            on_progress=on_progress,
        )
    )
    progress.empty()
    return results, usage, errors


# Welcome-гейт — до sidebar і до on_wallet_ready (не завантажувати active «під» welcome).
if not st.session_state.get("welcome_seen"):
    render_welcome()
    st.stop()

project_service.on_wallet_ready(billing_ui.connected_wallet())

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    _sidebar = sidebar_ui.render_sidebar(
        apply_template=apply_template,
        apply_config=apply_config,
        collect_config=collect_config,
        get_api_key=get_api_key,
        get_llm_api_key=get_llm_api_key,
        has_persistent_api_key=has_persistent_api_key,
        has_persistent_anthropic_key=has_persistent_anthropic_key,
    )
model = _sidebar["model"]
platform = _sidebar["platform"]
temperature = _sidebar["temperature"]
include_traits = _sidebar["include_traits"]
include_negative = _sidebar["include_negative"]
collection_size = _sidebar["collection_size"]
api_key = get_api_key()
llm_key = get_llm_api_key(model)


# ── Header ────────────────────────────────────────────────────────────────────
st.title(t("app.title"))
if workflow_guide.workflow_mode() == workflow_guide.MODE_CLASSIC:
    hero = t("app.hero.classic")
else:
    hero = t("app.hero.pipeline")
st.markdown(f'<p class="hero-subtitle">{hero}</p>', unsafe_allow_html=True)
# Trust strip (UX-A4): довіра видима в застосунку, не лише на login.
st.markdown(f'<div class="trust-strip">{t("app.trust_strip")}</div>', unsafe_allow_html=True)
if not api_key:
    st.warning(t("app.no_api_key"))

_queue_size = len(st.session_state.get(GENERATED_PROMPTS) or [])
if workflow_guide.workflow_mode() == workflow_guide.MODE_PIPELINE:
    cost_calculator.render(expanded=True, queue_size=_queue_size)
else:
    cost_calculator.render(expanded=False, queue_size=_queue_size)

workflow_guide.render_transfer_banner()
if workflow_guide.workflow_mode() == workflow_guide.MODE_CLASSIC:
    workflow_guide.render_classic_tab_flash_banner(get_traits_weighted)

_is_admin = admin_access.is_admin(billing_ui.connected_wallet())
_tab_label_by_id = {
    "build": t("tab.builder"), "traits": t("tab.traits"), "batch": t("tab.batch"),
    "collection": t("tab.collection"), "images": t("tab.images"),
    "pipeline": t("tab.pipeline"), "history": t("tab.history"), "help": t("tab.help"),
}
_mode = workflow_guide.workflow_mode()
_tab_order = workflow_guide.ordered_tab_ids(_mode)  # Конвеєр першим у Pipeline-режимі
_tab_labels = [_tab_label_by_id[i] for i in _tab_order]
if _is_admin:
    _tab_labels.append(t("tab.admin"))  # вкладка видима лише адмін-гаманцям (ADMIN_WALLETS)
_tabs = st.tabs(_tab_labels)
_tab_by_id = {tid: _tabs[idx] for idx, tid in enumerate(_tab_order)}
tab_build = _tab_by_id["build"]
tab_traits = _tab_by_id["traits"]
tab_batch = _tab_by_id["batch"]
tab_collection = _tab_by_id["collection"]
tab_images = _tab_by_id["images"]
tab_pipeline = _tab_by_id["pipeline"]
tab_history = _tab_by_id["history"]
tab_help = _tab_by_id["help"]
if _is_admin:
    with _tabs[len(_tab_order)]:
        admin_panel.render()
# У Pipeline-режимі класичні вкладки (позиції 4–8) ховаємо — новачок бачить лише
# Конвеєр/Історію/Довідку; перемикач «Розширений режим» у sidebar повертає їх.
# Fail-режим безпечний: якщо селектор не збігся — вкладки просто лишаться видимими.
if _mode == workflow_guide.MODE_PIPELINE:
    st.markdown(
        '<style>div[data-baseweb="tab-list"] button[data-baseweb="tab"]'
        ":nth-child(n+4):nth-child(-n+8){display:none;}</style>",
        unsafe_allow_html=True,
    )

# ── Constructor ───────────────────────────────────────────────────────────────
with tab_build:
    build_panel.render(
        model=model,
        platform=platform,
        temperature=temperature,
        llm_key=llm_key,
        include_traits=include_traits,
        include_negative=include_negative,
        collection_size=collection_size,
        get_traits_weighted=get_traits_weighted,
        reserve_llm=_reserve_llm,
        refund_llm=_refund_llm,
    )

# ── Traits ────────────────────────────────────────────────────────────────────
with tab_traits:
    traits_panel.render(
        collection_size=collection_size,
        get_traits_weighted=get_traits_weighted,
        render_pipeline_context=render_pipeline_context,
    )

# ── Batch ─────────────────────────────────────────────────────────────────────
with tab_batch:
    batch_panel.render(
        model=model,
        platform=platform,
        temperature=temperature,
        llm_key=llm_key,
        get_traits_weighted=get_traits_weighted,
        run_batch_generation=run_batch_generation,
        render_metadata_form=render_metadata_form,
        reserve_llm=_reserve_llm,
        refund_llm=_refund_llm,
        render_pipeline_context=render_pipeline_context,
    )

# ── Collection ────────────────────────────────────────────────────────────────
with tab_collection:
    collection_panel.render(
        model=model,
        platform=platform,
        temperature=temperature,
        llm_key=llm_key,
        api_key=api_key,
        collection_size=collection_size,
        get_traits_weighted=get_traits_weighted,
        get_base_config=get_base_config,
        get_llm_api_key=get_llm_api_key,
        reserve_llm=_reserve_llm,
        refund_llm=_refund_llm,
        render_metadata_form=render_metadata_form,
        render_pipeline_context=render_pipeline_context,
        run_async=_run_async,
    )

# ── Images ────────────────────────────────────────────────────────────────────
with tab_images:
    images_panel.render(
        api_key=api_key,
        get_traits_weighted=get_traits_weighted,
        render_pipeline_context=render_pipeline_context,
        billing_error=_billing_error,
    )

# ── Pipeline (Web3-конвеєр) ───────────────────────────────────────────────────
with tab_pipeline:
    pipeline_panel.render(api_key=api_key)

# ── History ───────────────────────────────────────────────────────────────────
with tab_history:
    history_panel.render()

# ── Help ──────────────────────────────────────────────────────────────────────
with tab_help:
    help_center.render()

footer.render()

billing_ui.refresh_sidebar_balance_display()

# Autosave наприкінці прогону — покриває classic-вкладки (Batch/Collection/Traits/
# Builder) без точкових autosave; dirty-check відсікає зайві записи на reruns.
project_service.autosave_if_changed(billing_ui.connected_wallet())
