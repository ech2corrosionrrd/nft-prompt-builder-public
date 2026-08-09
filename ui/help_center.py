"""Центр довідки (вкладка 📖 Help): вибір файлу за мовою та рендер секцій.

Винесено з app.py (декомпозиція хотспоту). Чисті функції (`help_file`,
`split_sections`) тестуються без Streamlit; `render()` лише викликає UI.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st

from ui import workflow_guide
from ui_strings import LANG_EN, t, ui_lang

_HELP_DIR = Path(__file__).resolve().parent.parent  # корінь репозиторію (ui/ → ..)
HELP_FILE_UK = _HELP_DIR / "ДОВІДКА.md"
HELP_FILE_EN = _HELP_DIR / "HELP.md"
_SUBHEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$", re.MULTILINE)


def _slugify(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", s).strip("-") or "section"


def uniquify_subheadings(body: str, section_prefix: str) -> str:
    """Перетворює #### заголовки на HTML з унікальними id (BUG-004 cheat-sheet ×N)."""
    counts: dict[str, int] = {}

    def repl(match: re.Match[str]) -> str:
        level_marks, title = match.group(1), match.group(2).strip()
        base = _slugify(title)
        n = counts.get(base, 0)
        counts[base] = n + 1
        anchor = f"{section_prefix}-{base}" if n == 0 else f"{section_prefix}-{base}-{n}"
        level = len(level_marks)
        return f'<h{level} id="{html.escape(anchor)}">{html.escape(title)}</h{level}>'

    return _SUBHEADING_RE.sub(repl, body)


def help_file() -> Path:
    """Файл довідки за мовою інтерфейсу; англійський — з фолбеком на український."""
    if ui_lang() == LANG_EN and HELP_FILE_EN.exists():
        return HELP_FILE_EN
    return HELP_FILE_UK


def split_sections(help_text: str) -> tuple[str, list[tuple[str, str]]]:
    """Розбиває довідку на вступ і список (заголовок, тіло) за `## `-секціями.

    Дзеркалить логіку UI: перший фрагмент — вступ, решта стають розгортачами.
    """
    parts = help_text.split("\n## ")
    intro = parts[0]
    sections: list[tuple[str, str]] = []
    for section in parts[1:]:
        title, _, body = section.partition("\n")
        sections.append((title.strip(), body))
    return intro, sections


@st.cache_data
def _load_help_text(path: str, mtime: float) -> str:
    return Path(path).read_text(encoding="utf-8")


def render() -> None:
    """Рендерить вкладку довідки: завантаження файлу + секції-розгортачі."""
    file = help_file()
    if not file.exists():
        st.info(t("help.missing"))
        return
    help_text = _load_help_text(str(file), file.stat().st_mtime)
    st.download_button(
        t("help.download"), help_text,
        file.name, "text/markdown",
    )
    intro, sections = split_sections(help_text)
    pending_help = st.session_state.pop(workflow_guide.HELP_PENDING_SECTION_KEY, None)
    st.markdown(intro)
    for title, body in sections:
        with st.expander(
            title,
            expanded=workflow_guide.help_section_expanded(title, pending_help),
        ):
            prefix = _slugify(title.split(".", 1)[-1] if "." in title else title)
            st.markdown(uniquify_subheadings(body, prefix), unsafe_allow_html=True)
