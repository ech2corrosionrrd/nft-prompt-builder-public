"""Інтерактивний конфігуратор розподілу рідкості traits (Web3 dark UI).

Замінює «сухі» таблиці ваг на візуальні слайдери: колір треку/повзунка
й кастомний прогрес-бар змінюються в реальному часі залежно від tier'а
(Common / Rare / Legend), а сума завжди зводиться до рівно 100%.

Структурне обмеження Streamlit: нативні віджети не мають per-widget класів,
тож таргетимо КОНКРЕТНИЙ слайдер через `st.container(key=...)` → DOM-клас
`.st-key-<key>` (Streamlit ≥ 1.39). CSS інжектиться щоранрана з урахуванням
поточного значення (читаємо session_state ПЕРЕД рендером віджета), тому
колір реагує миттєво.
"""

from __future__ import annotations

import streamlit as st

# ── Tier-пороги (NFT-конвенція: рідкісне = низька частка) ──────────────────────
# value >= COMMON_MIN  → Common  (часте; приглушений зелено-сірий)
# RARE_MIN..COMMON_MIN → Rare    (фіолетово-синій)
# value <  RARE_MIN    → Legend  (золото/помаранч)
COMMON_MIN = 25
RARE_MIN = 8

_TOKEN = {
    "common": "var(--rarity-common)",
    "rare": "var(--rarity-rare)",
    "legend": "var(--rarity-legend)",
}
_BADGE = {"common": "Common", "rare": "Rare", "legend": "Legend"}

_PENDING_PREFIX = "_rarity_pending_"  # auto-balance пише сюди, застосовуємо до рендеру


def tier(value: int) -> str:
    """Класифікує частку (%) у tier рідкості."""
    if value >= COMMON_MIN:
        return "common"
    if value >= RARE_MIN:
        return "rare"
    return "legend"


def _slider_key(prefix: str, idx: int) -> str:
    return f"{prefix}_rarity_slider_{idx}"


def _row_key(prefix: str, idx: int) -> str:
    return f"{prefix}_rarity_row_{idx}"


def _balance_to_100(values: list[int]) -> list[int]:
    """Нормалізує до суми рівно 100 (метод найбільших залишків).

    Порожній/нульовий вхід → рівний розподіл із розкиданням залишку.
    """
    n = len(values)
    if n == 0:
        return []
    total = sum(values)
    if total <= 0:
        base, rem = divmod(100, n)
        return [base + (1 if i < rem else 0) for i in range(n)]
    scaled = [v * 100 / total for v in values]
    floors = [int(x) for x in scaled]
    rem = 100 - sum(floors)
    # Залишок дістається позиціям із найбільшою дробовою частиною.
    order = sorted(range(n), key=lambda i: scaled[i] - floors[i], reverse=True)
    for i in order[:rem]:
        floors[i] += 1
    return floors


def normalize_pct(items: list[tuple[str, float]]) -> dict[str, int]:
    """[(назва, вага)] → {назва: %} із сумою рівно 100 — seed для слайдерів."""
    names = [n for n, _ in items]
    return dict(zip(names, _balance_to_100([float(w) for _, w in items])))


def _apply_pending(prefix: str) -> None:
    """Записує відкладені (auto-balance) значення у session_state до рендеру.

    Streamlit забороняє міняти key віджета в тому ж run, де він створений,
    тож auto-balance лише ставить прапорець, а застосування — на наступному run.
    """
    pending = st.session_state.pop(_PENDING_PREFIX + prefix, None)
    if not pending:
        return
    for idx, val in pending.items():
        st.session_state[_slider_key(prefix, idx)] = int(val)


def _inject_row_css(prefix: str, idx: int, t_name: str) -> None:
    """Скоупить колір треку/повзунка конкретного слайдера під його tier.

    Надійний сигнал — повзунок `[role="slider"]` (стабільний baseweb-вузол).
    Заливку треку baseweb рендерить інлайн-стилем, тож тонуємо best-effort
    через `div[style*="background"]` усередині того ж слайдера (з !important).
    """
    sel = f".st-key-{_row_key(prefix, idx)}"
    color = _TOKEN[t_name]
    st.markdown(
        f"""<style>
        {sel} div[data-baseweb="slider"] [role="slider"] {{
            background: {color} !important;
            border-color: {color} !important;
            box-shadow: 0 0 0 4px color-mix(in srgb, {color} 22%, transparent) !important;
        }}
        {sel} div[data-baseweb="slider"] div[style*="background"] {{
            background: {color} !important;
        }}
        {sel} [data-testid="stWidgetLabel"] {{ display: none; }}
        </style>""",
        unsafe_allow_html=True,
    )


def _bar(value: int, t_name: str) -> str:
    """Кастомний прогрес-бар — повністю контрольована розмітка (не baseweb).

    Гарантує видимість rarity-кольору незалежно від інлайн-стилів baseweb.
    """
    color = _TOKEN[t_name]
    width = max(0, min(100, value))
    return (
        f'<div style="height:6px;border-radius:4px;background:var(--surface-2);'
        f'overflow:hidden;margin-top:.35rem">'
        f'<div style="height:100%;width:{width}%;background:{color};'
        f'border-radius:4px;transition:width .15s ease"></div></div>'
    )


def _summary(total: int) -> None:
    """Рядок підсумку: залишок / переліміт / точно 100%."""
    if total == 100:
        st.markdown(
            '<div style="color:var(--success);font-weight:600">'
            '✓ Розподілено точно 100%</div>',
            unsafe_allow_html=True,
        )
    elif total < 100:
        st.markdown(
            f'<div style="color:var(--warning);font-weight:600">'
            f'Залишилось розподілити: {100 - total}%</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="color:var(--error);font-weight:600">'
            f'Переліміт: -{total - 100}%</div>',
            unsafe_allow_html=True,
        )
    # Агрегований індикатор суми (зелений до 100, червоний на переліміті).
    fill = min(100, total)
    over = total > 100
    bar_color = "var(--error)" if over else "var(--accent-grad)"
    st.markdown(
        f'<div style="height:8px;border-radius:5px;background:var(--surface-2);'
        f'overflow:hidden;margin:.25rem 0 .75rem">'
        f'<div style="height:100%;width:{fill}%;background:{bar_color};'
        f'border-radius:5px"></div></div>',
        unsafe_allow_html=True,
    )


def render_rarity_sliders(
    initial_state: dict[str, int],
    *,
    prefix: str = "",
    title: str | None = "🎲 Розподіл рідкості",
) -> dict[str, int]:
    """Рендерить набір rarity-слайдерів і повертає нові частки (%).

    initial_state: {назва_trait: відсоток}. Значення поза 0..100 затискаються.
    prefix: namespace ключів/CSS — потрібен, якщо на сторінці кілька інстансів
            (інакше DuplicateWidgetID). Має бути ascii-safe (для CSS-селектора).
    title: заголовок групи; None — без заголовка.
    Повертає {назва_trait: int(%)} з поточними значеннями слайдерів.
    """
    _apply_pending(prefix)

    names = list(initial_state.keys())
    if not names:
        st.info("Немає traits для конфігурації рідкості.")
        return {}

    # Поточні значення з session_state (реактивно) або з initial_state на 1-му run.
    cur = {
        i: max(0, min(100, int(st.session_state.get(_slider_key(prefix, i), initial_state[name]))))
        for i, name in enumerate(names)
    }

    if title:
        st.markdown(f"##### {title}")
        st.caption("Рідкісніше = менша частка. Колір слайдера показує tier у реальному часі.")

    result: dict[str, int] = {}
    for i, name in enumerate(names):
        t_name = tier(cur[i])
        _inject_row_css(prefix, i, t_name)  # скоуп під поточний tier ДО рендеру слайдера
        with st.container(key=_row_key(prefix, i)):
            c_label, c_slider, c_val = st.columns([3, 6, 2], vertical_alignment="center")
            with c_label:
                st.markdown(
                    f'<div style="font-weight:600;color:var(--text)">{name}</div>'
                    f'<span style="font-size:.7rem;font-weight:700;letter-spacing:.04em;'
                    f'text-transform:uppercase;color:{_TOKEN[t_name]}">'
                    f'{_BADGE[t_name]}</span>',
                    unsafe_allow_html=True,
                )
            with c_slider:
                val = st.slider(
                    name, 0, 100, cur[i], step=1,
                    key=_slider_key(prefix, i), label_visibility="collapsed",
                )
                st.markdown(_bar(val, tier(val)), unsafe_allow_html=True)
            with c_val:
                st.markdown(
                    f'<div style="text-align:right;font-variant-numeric:tabular-nums;'
                    f'font-weight:700;font-size:1.1rem;color:var(--text)">{val}%</div>',
                    unsafe_allow_html=True,
                )
        result[name] = int(val)

    total = sum(result.values())
    st.divider()
    _summary(total)

    if st.button("⚖️ Auto-balance до 100%", width='stretch',
                 disabled=(total == 100), key=f"{prefix}_rarity_autobalance"):
        balanced = _balance_to_100([result[n] for n in names])
        st.session_state[_PENDING_PREFIX + prefix] = {i: balanced[i] for i in range(len(names))}
        st.rerun()

    return result
