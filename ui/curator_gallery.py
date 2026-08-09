"""Галерея куратора: рейтинг 1–5, фільтри rarity/traits, сортування."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from services import image_qa
from ui_strings import t

# BUG-5: 3-колонкова сітка давала рендер-квірк Streamlit у вузькій СЕРЕДНІЙ
# колонці (checkbox не показував checked-стан). 2 колонки — ширші клітинки, без
# проблемної середньої позиції; стан схвалення — через st.toggle (інший DOM/CSS).
GRID_COLUMNS = 2
SORT_NUM = "num"
SORT_RATING = "rating"
SORT_RARITY = "rarity"
TIER_ALL = "__all__"
SORT_QA = "qa"
TIERS = ["Legendary", "Epic", "Rare", "Uncommon", "Common", "Unique"]
_ISSUE_KEYS = {
    image_qa.ISSUE_CORRUPT: "curator.qa_issue_corrupt",
    image_qa.ISSUE_TINY: "curator.qa_issue_tiny",
    image_qa.ISSUE_BLANK: "curator.qa_issue_blank",
    image_qa.ISSUE_BLURRY: "curator.qa_issue_blurry",
}


def qa_card_caption(qa: image_qa.QAResult) -> str:
    """Підпис Auto-QA для картки куратора (0–100, технічні дефекти)."""
    star = image_qa.star_rating_from_qa(qa.score)
    if qa.issues:
        issues = ", ".join(t(_ISSUE_KEYS.get(iss, "curator.qa_issue_corrupt")) for iss in qa.issues)
        return t("curator.qa_card_warn", score=qa.score, issues=issues, star=star)
    return t("curator.qa_card_ok", score=qa.score, star=star)


def _trait_text(img: dict) -> str:
    return ", ".join(f"{k}: {v}" for k, v in (img.get("traits") or {}).items()).lower()


def filter_images(
    images: list[dict],
    min_rating: int,
    min_rarity: float,
    trait_query: str,
    tier_filter: str,
    *,
    min_qa_score: int = 0,
    qa_by_path: dict[str, image_qa.QAResult] | None = None,
) -> list[int]:
    q = (trait_query or "").strip().lower()
    out: list[int] = []
    for i, img in enumerate(images):
        if not Path(img.get("path", "")).exists():
            continue
        rating = int(st.session_state.get(f"pl2_rating_{i}", 0))
        if rating < min_rating:
            continue
        score = img.get("rarity_score")
        if min_rarity > 0 and (score is None or float(score) < min_rarity):
            continue
        if tier_filter != TIER_ALL and img.get("rarity_tier") != tier_filter:
            continue
        if q and q not in _trait_text(img) and q not in img.get("prompt", "").lower():
            continue
        if min_qa_score > 0 and qa_by_path is not None:
            path = str(img.get("path", ""))
            qa = qa_by_path.get(path)
            if qa is None or qa.score < min_qa_score:
                continue
        out.append(i)
    return out


def sort_indices(
    indices: list[int],
    images: list[dict],
    sort_by: str,
    qa_by_path: dict[str, image_qa.QAResult] | None = None,
) -> list[int]:
    if sort_by == SORT_RATING:
        return sorted(indices, key=lambda i: st.session_state.get(f"pl2_rating_{i}", 0), reverse=True)
    if sort_by == SORT_RARITY:
        return sorted(indices, key=lambda i: float(images[i].get("rarity_score") or 0), reverse=True)
    if sort_by == SORT_QA and qa_by_path is not None:
        return sorted(
            indices,
            key=lambda i: qa_by_path.get(str(images[i].get("path", "")), image_qa.QAResult(0)).score,
            reverse=True,
        )
    return sorted(indices)


def build_qa_cache(images: list[dict]) -> dict[str, image_qa.QAResult]:
    """QA-результати для поточного batch (кешується в session_state)."""
    sig = tuple(str(img.get("path", "")) for img in images)
    if st.session_state.get("_pl2_qa_sig") != sig:
        st.session_state["_pl2_qa_sig"] = sig
        st.session_state["_pl2_qa"] = {
            str(img.get("path", "")): image_qa.analyze_image_path(str(img.get("path", "")))
            for img in images if img.get("path")
        }
    return st.session_state.get("_pl2_qa", {})


def render_gallery_filters() -> tuple[int, float, str, str, str, int]:
    st.markdown(t("curator.title"))
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        # Дефолт 0 — щоб свіжозгенеровані (ще не оцінені, рейтинг 0) зображення
        # одразу були видимі. Інакше фільтр ховав би весь результат генерації.
        min_rating = st.slider(t("curator.min_rating"), 0, 5, 0, key="pl2_min_rating")
    with f2:
        min_rarity = st.number_input(t("curator.min_rarity"), 0.0, 100.0, 0.0, 0.5, key="pl2_min_rarity")
    with f3:
        trait_query = st.text_input(t("curator.trait_filter"), key="pl2_trait_q", placeholder="crown, neon…")
    with f4:
        tier_filter = st.selectbox(
            t("curator.tier"),
            [TIER_ALL] + TIERS,
            format_func=lambda x: t("common.all") if x == TIER_ALL else x,
            key="pl2_tier_filter",
        )
    min_qa = st.slider(t("curator.min_qa"), 0, 100, 0, key="pl2_min_qa", help=t("curator.min_qa_help"))
    sort_by = st.radio(
        t("curator.sort"),
        [SORT_NUM, SORT_RATING, SORT_RARITY, SORT_QA],
        format_func=lambda s: {
            SORT_NUM: t("curator.sort_num"),
            SORT_RATING: t("curator.sort_rating"),
            SORT_RARITY: t("curator.sort_rarity"),
            SORT_QA: t("curator.sort_qa"),
        }[s],
        horizontal=True,
        key="pl2_sort",
    )
    return min_rating, min_rarity, trait_query, tier_filter, sort_by, min_qa


def _open_zoom(img: dict, idx: int) -> None:
    """Lightbox-перегляд зображення на повний розмір (UX-B6) через st.dialog.

    Декоратор застосовуємо ліниво (всередині), щоб t() узяв поточну мову сесії,
    а не дефолт на момент імпорту модуля.
    """
    @st.dialog(t("curator.zoom_title", n=idx + 1), width="large")
    def _dlg() -> None:
        st.image(img["path"], width='stretch')
        if img.get("prompt"):
            st.markdown(t("curator.zoom_prompt"))
            st.caption(img["prompt"])
        traits = img.get("traits") or {}
        if traits:
            st.markdown(t("curator.zoom_traits"))
            st.caption(", ".join(f"{k}: {v}" for k, v in traits.items()))

    _dlg()


def render_curator_grid(
    images: list[dict], indices: list[int], qa_by_path: dict[str, image_qa.QAResult] | None = None,
) -> list[int]:
    cols = st.columns(GRID_COLUMNS)
    for pos, i in enumerate(indices):
        img = images[i]
        with cols[pos % GRID_COLUMNS]:
            cap = f"#{i + 1}"
            if img.get("rarity_score") is not None:
                cap += f" · R:{img['rarity_score']}"
            if img.get("rarity_tier"):
                cap += f" · {img['rarity_tier']}"
            if img.get("engine"):
                cap += f" · {img['engine'].split('(')[0].strip()}"
            path = str(img.get("path", ""))
            if qa_by_path and path in qa_by_path:
                qa = qa_by_path[path]
                cap += f" · QA:{qa.score}"
                if qa.issues:
                    cap += " ⚠"
            st.image(img["path"], caption=cap, width='stretch')
            if qa_by_path and path in qa_by_path:
                st.caption(qa_card_caption(qa_by_path[path]))
            if st.button(t("curator.zoom", n=i + 1), key=f"pl2_zoom_{i}", width='stretch'):
                _open_zoom(img, i)
            st.caption(img["prompt"][:80] + ("…" if len(img.get("prompt", "")) > 80 else ""))
            st.slider(t("curator.rate", n=i + 1), 0, 5, key=f"pl2_rating_{i}", help=t("curator.rate_help"))
            st.toggle(t("curator.approve", n=i + 1), key=f"pl2_approve_{i}", help=t("curator.approve_help"))
            if st.button(t("curator.regenerate", n=i + 1), key=f"pl2_regen_{i}", width='stretch'):
                st.session_state["_pl2_regen_index"] = i
    return indices
