"""Вкладка 🕘 History: пошук і перегляд історії генерацій.

Винесено з app.py (декомпозиція хотспоту). `filter_history` — чиста функція
(тестується без Streamlit); live-пошук — HTML-компонент (BUG-020: Streamlit
text_input комітить лише на Enter, не на кожен символ).
"""

from __future__ import annotations

import html
import json

import streamlit as st
import streamlit.components.v1 as components

import storage
from ui import billing_ui
from ui_strings import t


def filter_history(history: list[dict], query: str) -> list[dict]:
    """Фільтрує записи історії за підрядком у ідеї/платформі/моделі/контенті.

    Порожній запит → уся історія. Регістронезалежно.
    """
    q = (query or "").strip().lower()
    if not q:
        return list(history)
    return [
        item for item in history
        if q in (
            item.get("idea", "") + " " +
            item.get("platform", "") + " " +
            item.get("model", "") + " " +
            item.get("content", "")
        ).lower()
    ]


def history_list_html(
    history: list[dict], *, search_placeholder: str, download_label: str,
) -> str:
    """HTML+JS список історії з миттєвим фільтром (без round-trip на Enter)."""
    rows = []
    for i, item in enumerate(history):
        ts = (item.get("timestamp") or "")[:19].replace("T", " ")
        model_tag = item.get("model") or ""
        idea = item.get("idea") or "—"
        hay = " ".join(
            str(item.get(k, "")) for k in ("idea", "platform", "model", "content")
        ).lower()
        rows.append({
            "i": i,
            "ts": ts,
            "model": model_tag,
            "idea": idea,
            "content": item.get("content") or "",
            "hay": hay,
        })
    payload = json.dumps(rows, ensure_ascii=False)
    ph = html.escape(search_placeholder, quote=True)
    dl = html.escape(download_label, quote=True)
    return f"""
<div class="w3ir-hist-root">
  <input type="search" class="w3ir-hist-q" placeholder="{ph}" aria-label="{ph}"
         oninput="window._w3irHistFilter(this.value)" />
  <p class="w3ir-hist-meta" id="w3ir-hist-meta"></p>
  <div id="w3ir-hist-list"></div>
</div>
<style>
  .w3ir-hist-root {{ font-family: "Source Sans Pro", sans-serif; font-size: 0.9rem; }}
  .w3ir-hist-q {{
    width: 100%; box-sizing: border-box; padding: 0.45rem 0.65rem; margin-bottom: 0.5rem;
    border-radius: 8px; border: 1px solid rgba(110, 86, 207, 0.35); background: #fff;
  }}
  .w3ir-hist-meta {{ color: #6b7280; font-size: 0.8rem; margin: 0 0 0.5rem; }}
  details.w3ir-hist-item {{
    border: 1px solid rgba(110, 86, 207, 0.2); border-radius: 8px;
    margin-bottom: 0.35rem; padding: 0.25rem 0.5rem; background: #f9f8fc;
  }}
  details.w3ir-hist-item summary {{ cursor: pointer; font-weight: 500; }}
  .w3ir-hist-body {{ white-space: pre-wrap; font-size: 0.85rem; margin: 0.5rem 0; }}
  .w3ir-hist-dl {{
    font-size: 0.8rem; color: #6e56cf; cursor: pointer; border: none; background: none;
    text-decoration: underline; padding: 0;
  }}
</style>
<script>
(function() {{
  const items = {payload};
  const list = document.getElementById("w3ir-hist-meta");
  const root = document.getElementById("w3ir-hist-list");
  function esc(s) {{
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;");
  }}
  window._w3irHistDownload = function(idx) {{
    const it = items[idx];
    if (!it) return;
    const blob = new Blob([it.content], {{type: "text/markdown"}});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "hist_" + idx + ".md";
    a.click();
    URL.revokeObjectURL(a.href);
  }};
  window._w3irHistFilter = function(q) {{
    const needle = (q || "").trim().toLowerCase();
    const filtered = needle
      ? items.filter(it => it.hay.includes(needle))
      : items;
    list.textContent = filtered.length + " / " + items.length;
    root.innerHTML = filtered.map(it => {{
      const tag = it.model ? " · " + esc(it.model) : "";
      return `<details class="w3ir-hist-item" open>
        <summary>#${{it.i + 1}} · ${{esc(it.idea)}} · ${{esc(it.ts)}}${{tag}}</summary>
        <div class="w3ir-hist-body">${{esc(it.content)}}</div>
        <button type="button" class="w3ir-hist-dl" onclick="window._w3irHistDownload(${{it.i}})">{dl}</button>
      </details>`;
    }}).join("");
  }};
  window._w3irHistFilter("");
}})();
</script>
"""


def render() -> None:
    """Рендерить вкладку історії: пошук, очищення, список розгортачів."""
    st.subheader(t("hist.title"))
    if not st.session_state.history:
        st.info(t("hist.empty"))
        return
    _render_history_body()


@st.fragment
def _render_history_body() -> None:
    """Список історії з live-пошуком (HTML) і кнопкою очищення."""
    if st.button(t("hist.clear_all"), key="hist_clear_all"):
        st.session_state.history = []
        st.session_state.last_result = None
        storage.save_history(billing_ui.connected_wallet(), [])
        st.rerun()

    history = st.session_state.history
    est_h = min(720, 120 + len(history) * 72)
    components.html(
        history_list_html(
            history,
            search_placeholder=t("hist.search_ph"),
            download_label=t("hist.download"),
        ),
        height=est_h,
        scrolling=True,
    )
