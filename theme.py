"""Перемикач світлої / темної теми операторського інтерфейсу.

Streamlit не перемикає нативну тему лише CSS-ом: при base=dark у config.toml
віджети лишаються темними. Тому:
  • [theme.light] / [theme.dark] у .streamlit/config.toml — палітри для native theme;
  • apply_theme() синхронізує localStorage (stActiveTheme-…-v2) і робить reload
    при зміні — тоді expander, select, alert тощо підхоплюють світлу тему;
  • вибір ui_theme пишеться в cookie (переживає reload; session_state — ні).
Додатковий CSS (theme_css) — брендинг і кастомні картки поверх native.

JS інжектиться через st.html(..., unsafe_allow_javascript=True): st.markdown
скриптів не виконує (DOMPurify), через що CSS і native theme «перемішувались».
"""

from __future__ import annotations

import json

import streamlit as st

from ui_strings import t

THEME_KEY = "ui_theme"
THEME_COOKIE = "ui_theme"
DEFAULT_THEME = "dark"

ACCENT = "#6e56cf"
ACCENT_LIGHT = "#9e8cfc"

# Стейт- і rarity-токени (єдині для обох тем — семантика не залежить від фону).
STATE = {
    "success": "#30a46c",
    "warning": "#f5a623",
    "error": "#e5484d",
}
RARITY = {
    "common": "#30a46c",
    "rare": "#9e8cfc",
    "legend": "#f5a623",
}

# Палітри: спільний бренд-акцент (фіолетовий), різні фон/текст/поверхні.
# Темна — Radix-inspired dark scale (висока щільність даних, Web3-естетика).
THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0a0b0f",
        "text": "#ecedef",
        "text_muted": "#9ba1ae",
        "surface": "#12141a",
        "border": "#232734",
        "sidebar": "linear-gradient(180deg, #12141a 0%, #0a0b0f 100%)",
        "input_bg": "#0d0f14",
    },
    "light": {
        "bg": "#ffffff",
        "text": "#1f2937",
        "text_muted": "#6b7280",
        "surface": "#f3f0fa",
        "border": "rgba(110, 86, 207, 0.20)",
        "sidebar": "linear-gradient(180deg, #f5f3ff 0%, #ede9fe 100%)",
        "input_bg": "#ffffff",
    },
}


def theme_from_cookie() -> str | None:
    """Прочитати збережений ui_theme з cookie (після reload session_state порожній)."""
    try:
        raw = st.context.cookies.get(THEME_COOKIE)
    except Exception:
        return None
    return raw if raw in THEMES else None


def ensure_theme_state() -> str:
    """Ініціалізувати ui_theme з cookie або дефолту; повернути поточну тему."""
    if THEME_KEY not in st.session_state:
        st.session_state[THEME_KEY] = theme_from_cookie() or DEFAULT_THEME
    return current_theme()


def current_theme() -> str:
    name = st.session_state.get(THEME_KEY, DEFAULT_THEME)
    return name if name in THEMES else DEFAULT_THEME


def native_theme_label(name: str) -> str:
    """Мітка для Streamlit localStorage (Light / Dark)."""
    return "Light" if name == "light" else "Dark"


def theme_sync_script(theme: str) -> str:
    """JS: cookie + Streamlit native theme (localStorage) + reload при розбіжності.

    Якщо в config.toml є і light, і dark, Streamlit без запису в localStorage
    дефолтить у Light — тому Dark теж явно пишемо (не лише Light).
    Cookie тримає наш ui_theme через reload (session_state скидається).
    """
    want = native_theme_label(theme)
    collapse_lbl = t("a11y.collapse_sidebar")
    expand_lbl = t("a11y.expand_sidebar")
    return f"""
    <div style="display:none" aria-hidden="true">
    <script>
    (function() {{
      const want = {json.dumps(want)};
      const themeKey = {json.dumps(theme)};
      const cookieName = {json.dumps(THEME_COOKIE)};
      document.cookie = cookieName + '=' + themeKey
        + '; path=/; max-age=31536000; SameSite=Lax';
      const key = 'stActiveTheme-' + window.location.pathname + '-v2';
      let cur = null;
      try {{
        cur = JSON.parse(localStorage.getItem(key) || 'null');
      }} catch (e) {{
        cur = '__invalid__';
      }}
      if (cur !== want) {{
        localStorage.setItem(key, JSON.stringify(want));
        window.location.reload();
        return;
      }}
      const collapseLbl = {json.dumps(collapse_lbl)};
      const expandLbl = {json.dumps(expand_lbl)};
      function labelSidebarToggle() {{
        const collapsed = document.querySelector('[data-testid="stSidebarCollapseButton"] button');
        if (collapsed) {{
          const open = document.querySelector('[data-testid="stSidebar"]')?.getAttribute("aria-expanded") !== "false";
          collapsed.setAttribute("aria-label", open ? collapseLbl : expandLbl);
        }}
      }}
      labelSidebarToggle();
      new MutationObserver(labelSidebarToggle).observe(document.body, {{childList: true, subtree: true}});
    }})();
    </script>
    </div>
    """


def theme_css(name: str) -> str:
    """CSS обраної теми (без тегів <style>) — окремо для тестів."""
    c = THEMES.get(name, THEMES[DEFAULT_THEME])
    is_light = name == "light"
    badge_large_fg = "#047857" if is_light else "#6ee7b7"
    badge_large_bg = "rgba(5, 150, 105, 0.12)" if is_light else "rgba(52, 211, 153, 0.15)"
    badge_large_border = "rgba(5, 150, 105, 0.35)" if is_light else "rgba(52, 211, 153, 0.35)"
    badge_mini_fg = "#1d4ed8" if is_light else "#93c5fd"
    badge_mini_bg = "rgba(37, 99, 235, 0.10)" if is_light else "rgba(96, 165, 250, 0.12)"
    badge_mini_border = "rgba(37, 99, 235, 0.28)" if is_light else "rgba(96, 165, 250, 0.3)"
    card_hover_shadow = "0 8px 28px rgba(110, 86, 207, 0.14)" if is_light else "0 8px 28px rgba(0, 0, 0, 0.28)"
    accent_hover = ACCENT if is_light else ACCENT_LIGHT
    light_native = ""
    if is_light:
        light_native = f"""
        /* Додатковий оверрайд нативних віджетів (якщо native theme ще не підхопився) */
        [data-testid="stAppViewContainer"],
        section[data-testid="stMain"] {{
            background-color: {c["bg"]} !important;
            color: {c["text"]} !important;
        }}
        [data-testid="stHeader"] {{
            background-color: {c["bg"]} !important;
        }}
        [data-testid="stExpander"] details {{
            background-color: {c["surface"]} !important;
            border-color: {c["border"]} !important;
        }}
        [data-testid="stAlert"],
        [data-testid="stNotification"] {{
            color: {c["text"]} !important;
        }}
        [data-baseweb="popover"],
        [data-baseweb="menu"] {{
            background-color: {c["bg"]} !important;
            color: {c["text"]} !important;
        }}
        [data-baseweb="menu"] li {{
            color: {c["text"]} !important;
        }}
        [data-testid="stMetricValue"] {{
            color: {c["text"]} !important;
        }}
        pre, code, [data-testid="stCode"] {{
            background-color: {c["surface"]} !important;
            color: {c["text"]} !important;
            white-space: pre-wrap !important;
            word-break: break-word !important;
            overflow-x: auto !important;
        }}
        /* BUG beta: довгий промпт у code-блоці — видимий скрол і перенос */
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {{
            white-space: pre-wrap !important;
            word-break: break-word !important;
            max-height: 14rem;
            overflow-y: auto !important;
        }}
        """
    dark_native = ""
    if not is_light:
        dark_native = f"""
        /* Нативні віджети: узгодження з темною палітрою (якщо localStorage ще не синхронізовано) */
        [data-testid="stAppViewContainer"],
        section[data-testid="stMain"] {{
            background-color: {c["bg"]} !important;
            color: {c["text"]} !important;
        }}
        [data-testid="stHeader"] {{
            background-color: {c["bg"]} !important;
        }}
        [data-testid="stExpander"] details {{
            background-color: {c["surface"]} !important;
            border-color: {c["border"]} !important;
            color: {c["text"]} !important;
        }}
        [data-testid="stAlert"],
        [data-testid="stNotification"] {{
            color: {c["text"]} !important;
        }}
        [data-baseweb="popover"],
        [data-baseweb="menu"] {{
            background-color: {c["surface"]} !important;
            color: {c["text"]} !important;
        }}
        [data-baseweb="menu"] li {{
            color: {c["text"]} !important;
        }}
        section[data-testid="stMain"] [data-testid="stMetricValue"] {{
            color: {c["text"]} !important;
        }}
        pre, code, [data-testid="stCode"] {{
            background-color: {c["input_bg"]} !important;
            color: {c["text"]} !important;
            white-space: pre-wrap !important;
            word-break: break-word !important;
            overflow-x: auto !important;
        }}
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {{
            white-space: pre-wrap !important;
            word-break: break-word !important;
            max-height: 14rem;
            overflow-y: auto !important;
        }}
        """
    light_btn = ""
    if is_light:
        light_btn = f"""
        /* BUG-011: base=dark у config.toml — форсуємо читабельні secondary-кнопки */
        section[data-testid="stMain"] .stButton > button,
        section[data-testid="stMain"] [data-testid="stBaseButton-secondary"],
        section[data-testid="stMain"] [data-testid="stBaseButton-secondary"] > span,
        div[data-testid="stSidebar"] .stButton > button,
        div[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
            color: {c["text"]} !important;
            background-color: {c["surface"]} !important;
            border: 1px solid {c["border"]} !important;
        }}
        section[data-testid="stMain"] .stButton > button p,
        section[data-testid="stMain"] .stButton > button span,
        section[data-testid="stMain"] .stButton > button div,
        div[data-testid="stSidebar"] .stButton > button p,
        div[data-testid="stSidebar"] .stButton > button span {{
            color: {c["text"]} !important;
        }}
        section[data-testid="stMain"] .stButton > button:hover,
        div[data-testid="stSidebar"] .stButton > button:hover {{
            color: {ACCENT} !important;
            background-color: #ebe6f7 !important;
            border-color: {ACCENT} !important;
        }}
        """
    return f"""
        :root {{
            --accent: {ACCENT};
            --accent-light: {ACCENT_LIGHT};
            --accent-grad: linear-gradient(90deg, {ACCENT}, {ACCENT_LIGHT});
            --surface-2: {c["surface"]};
            --border: {c["border"]};
            --text-muted: {c["text_muted"]};
            --success: {STATE["success"]};
            --warning: {STATE["warning"]};
            --error: {STATE["error"]};
            --rarity-common: {RARITY["common"]};
            --rarity-rare: {RARITY["rare"]};
            --rarity-legend: {RARITY["legend"]};
            --radius: 12px;
            /* Токени руху (UX-A8): крива entrance узгоджена з login.html Connect. */
            --ease: cubic-bezier(.4,0,.2,1);
            --ease-out: cubic-bezier(.16,1,.3,1);
            --dur-fast: .15s;
            --dur: .25s;
        }}
        .stApp {{ background-color: {c["bg"]}; color: {c["text"]}; }}
        .block-container {{ padding-top: 1.5rem; max-width: 1400px; }}
        h1 {{
            background: linear-gradient(135deg, #9e8cfc 0%, #6e56cf 50%, #4c3a9e 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            letter-spacing: -0.02em;
        }}
        .hero-subtitle {{ color: var(--text-muted); font-size: 1.05rem; margin-bottom: 0.75rem; }}
        .trust-strip {{
            display: flex; flex-wrap: wrap; gap: 0.5rem;
            margin: 0 0 1.5rem;
        }}
        .trust-strip span {{
            background: var(--surface-2);
            border: 1px solid {c["border"]};
            border-radius: 999px;
            padding: 0.2rem 0.7rem;
            font-size: 0.8rem;
            color: var(--text-muted);
            white-space: nowrap;
        }}
        div[data-testid="stSidebar"] {{
            background: {c["sidebar"]};
            border-right: 1px solid rgba(110, 86, 207, 0.2);
            color: {c["text"]};
        }}
        /* BUG-011: світла тема — читабельні кнопки, лейбли й sidebar */
        .stButton > button:not([kind="primary"]) {{
            color: {c["text"]} !important;
            background-color: {c["surface"]} !important;
            border: 1px solid {c["border"]} !important;
        }}
        .stButton > button:not([kind="primary"]):hover {{
            border-color: var(--accent) !important;
            color: {accent_hover} !important;
        }}
        label, label p, [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] p {{
            color: {c["text"]} !important;
        }}
        [data-testid="stCaptionContainer"], .stCaption {{
            color: var(--text-muted) !important;
        }}
        div[data-testid="stSidebar"] label, div[data-testid="stSidebar"] .stMarkdown {{
            color: {c["text"]} !important;
        }}
        div[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {{
            color: {c["text"]} !important;
            background-color: {c["input_bg"]} !important;
        }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, #6e56cf, #9e8cfc);
            border: none;
            border-radius: var(--radius);
            font-weight: 600;
            color: #fff;
        }}
        .stButton > button[kind="primary"]:hover {{
            box-shadow: 0 4px 20px rgba(110, 86, 207, 0.4);
        }}
        .metric-card, .template-card {{
            background: var(--surface-2);
            color: {c["text"]};
            border: 1px solid {c["border"]};
            border-radius: var(--radius);
            padding: 1rem 1.25rem;
            margin-bottom: 0.5rem;
        }}
        .template-card {{ border-left: 3px solid var(--accent); }}
        .template-card h4 {{ margin: 0 0 0.25rem; color: var(--accent-light); font-size: 0.9rem; }}
        .template-card p {{ margin: 0; font-size: 0.85rem; color: var(--text-muted); }}
        .template-supply-badge {{
            display: inline-block;
            font-size: 0.65rem;
            font-weight: 600;
            margin-left: 0.45rem;
            padding: 0.12rem 0.4rem;
            border-radius: 4px;
            vertical-align: middle;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }}
        .template-supply-badge--large {{
            background: {badge_large_bg};
            color: {badge_large_fg};
            border: 1px solid {badge_large_border};
        }}
        .template-supply-badge--mini {{
            background: {badge_mini_bg};
            color: {badge_mini_fg};
            border: 1px solid {badge_mini_border};
        }}
        .metric-card h4 {{ margin: 0 0 0.25rem; color: var(--accent-light); font-size: 0.85rem; }}
        .stTextInput input, .stNumberInput input, .stTextArea textarea,
        div[data-baseweb="select"] > div {{
            background-color: {c["input_bg"]};
            color: {c["text"]};
        }}
        .notranslate {{ translate: no !important; }}
        /* ── Рух і мікро-інтеракції (UX-A8): стримано, a11y-first ──────────── */
        .stButton > button {{
            transition: box-shadow var(--dur) var(--ease),
                        transform var(--dur-fast) var(--ease),
                        filter var(--dur) var(--ease);
        }}
        .stButton > button[kind="primary"]:hover {{
            filter: brightness(1.06);
            box-shadow: 0 4px 20px rgba(110, 86, 207, 0.4);
        }}
        .stButton > button:active {{ transform: translateY(1px); }}
        .metric-card, .template-card {{
            transition: transform var(--dur) var(--ease),
                        box-shadow var(--dur) var(--ease),
                        border-color var(--dur) var(--ease);
        }}
        .template-card:hover, .metric-card:hover {{
            transform: translateY(-2px);
            box-shadow: {card_hover_shadow};
            border-color: var(--accent);
        }}
        /* focus-visible ring (WCAG 2.4.7) — видима навігація з клавіатури. */
        .stButton > button:focus-visible, a:focus-visible,
        .stTextInput input:focus-visible, div[data-baseweb="select"]:focus-within {{
            outline: 2px solid var(--accent-light);
            outline-offset: 2px;
        }}
        button[data-baseweb="tab"] {{
            transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
            font-size: 0.9rem;
            font-weight: 500;
        }}
        button[data-baseweb="tab"]:not([aria-selected="true"]) {{
            color: var(--text-muted) !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{
            color: var(--accent-light) !important;
            font-weight: 700;
            border-bottom-color: var(--accent) !important;
        }}
        @keyframes fadeInUp {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
        .block-container {{ animation: fadeInUp .4s var(--ease-out); }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: .5; }} }}
        .is-loading {{ animation: pulse 1.2s var(--ease) infinite; }}
        /* Повага до системного налаштування зниженого руху (WCAG 2.3.3). */
        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                animation-duration: .001ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: .001ms !important;
            }}
        }}
        /* BUG-007: Streamlit дублює font-family на body — фіксуємо одним значенням */
        html, body, .stApp, [data-testid="stAppViewContainer"] {{
            font-family: "Source Sans Pro", "Source Sans", sans-serif !important;
        }}
        /* BUG-003: кнопки sidebar project bar — без переносу емодзі/тексту */
        div[data-testid="stSidebar"] .stButton button p {{
            white-space: nowrap;
        }}
        /* ── Sidebar: єдиний стандарт секцій (UX-A2 tiers) ─────────────────
           Заголовок зони = h4-«eyebrow»: дрібний, muted, uppercase — тиха
           структура, що не конкурує з контентом. Всі секції sidebar мають
           один рівень; звичайні h4 сторінки (welcome, main) не зачіпаються. */
        div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h4 {{
            font-size: 0.76rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-muted);
            margin: 0.3rem 0 0.1rem;
            padding: 0;
        }}
        div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h4 a,
        div[data-testid="stSidebar"] h4 [data-testid="stHeaderActionElements"] {{
            display: none;
        }}
        /* Картка шаблону в sidebar лишає власний заголовок (не eyebrow). */
        div[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] .template-card h4 {{
            font-size: 0.9rem;
            text-transform: none;
            letter-spacing: normal;
            color: var(--accent-light);
            margin: 0 0 0.25rem;
        }}
        /* Розділювачі зон — тонкі й компактні, не «сходи» з порожнин. */
        div[data-testid="stSidebar"] hr {{
            margin: 0.55rem 0;
            border: none;
            border-top: 1px solid var(--border);
        }}
        /* Баланс кредитів — головна цифра sidebar: брендовий акцент, стриманий розмір. */
        div[data-testid="stSidebar"] [data-testid="stMetricValue"] {{
            font-size: 1.55rem;
            color: var(--accent-light);
        }}
        div[data-testid="stSidebar"] [data-testid="stMetricLabel"] p {{
            font-size: 0.8rem;
            color: var(--text-muted) !important;
        }}
        /* Щільність: службові підписи дрібніші, вертикальний ритм коротший. */
        div[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
            font-size: 0.8rem;
            line-height: 1.35;
        }}
        div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {{
            gap: 0.75rem;
        }}
        /* ── Адаптив для вузьких екранів (UX-B2/B3, ≤768px) ───────────────── */
        @media (max-width: 768px) {{
            .block-container {{ padding-left: 0.75rem; padding-right: 0.75rem; padding-top: 2.5rem; }}
            /* Таби конвеєра/класики — компактніший шрифт, щоб не обрізались */
            button[data-baseweb="tab"] {{ font-size: 0.8rem; padding: 0.4rem 0.6rem; }}
            /* Радіо-селектор етапів та інші горизонтальні радіо — переносити рядком */
            div[role="radiogroup"] {{ flex-wrap: wrap; gap: 0.25rem 0.75rem; }}
            /* Step bar (1️⃣→2️⃣→…) не має витискати контент за екран */
            .hero-subtitle {{ font-size: 0.95rem; }}
            .trust-strip span {{ font-size: 0.72rem; padding: 0.15rem 0.55rem; }}
            /* Кнопки «Назад/Далі» wizard-а — повна ширина вже задана width='stretch' */
        }}
        {light_btn}
        {light_native}
        {dark_native}
    """


def apply_theme() -> None:
    """Інжектить CSS поточної теми. Викликати раз на початку рендеру."""
    theme = ensure_theme_state()
    # style-only → event container (не займає місце в layout)
    st.html(f"<style>{theme_css(theme)}</style>")
    # JS лише через st.html + unsafe_allow_javascript (markdown скриптів не виконує)
    st.html(theme_sync_script(theme), unsafe_allow_javascript=True)


def render_theme_selector() -> None:
    """Перемикач теми в sidebar (поряд із мовою)."""
    ensure_theme_state()
    labels = {"dark": t("theme.dark"), "light": t("theme.light")}
    st.selectbox(
        t("theme.label"),
        list(THEMES),
        format_func=lambda x: labels[x],
        key=THEME_KEY,
    )
