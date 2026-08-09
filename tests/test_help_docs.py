"""Тест паритету довідок: ДОВІДКА.md (uk) і HELP.md (en) мають однакову структуру.

Вкладка 📖 Help (app.py) розбиває довідку на розгортачі по `## `-секціях і вибирає
файл за мовою інтерфейсу. Якщо переклад відстане (з'явиться/зникне секція в одному
файлі) — UI двох мов розійдеться. Звіряємо нумерацію `## N.`-заголовків дзеркально.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELP_UK = ROOT / "ДОВІДКА.md"
HELP_EN = ROOT / "HELP.md"

# Заголовки рівня 2 виду "## 1. ..." — саме вони стають розгортачами в UI.
_SECTION_RE = re.compile(r"^## (\d+)\. ", re.MULTILINE)
# Посилання на .md у репо (не https) у довідці для користувача — 404 на ai.w3ir.io.
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _section_numbers(path: Path) -> list[str]:
    return _SECTION_RE.findall(path.read_text(encoding="utf-8"))


def _internal_repo_md_links(path: Path) -> list[str]:
    """Відносні посилання на .md (ПЛАН_*, LEGAL.md тощо) — не для вкладки Help."""
    bad: list[str] = []
    for target in _MD_LINK_RE.findall(path.read_text(encoding="utf-8")):
        t = target.strip()
        if t.endswith(".md") and not t.startswith(("http://", "https://")):
            bad.append(t)
    return bad


def test_both_help_files_exist():
    assert HELP_UK.is_file(), "ДОВІДКА.md (uk) відсутня"
    assert HELP_EN.is_file(), "HELP.md (en) відсутня"


def test_help_sections_match():
    uk = _section_numbers(HELP_UK)
    en = _section_numbers(HELP_EN)
    assert uk, "У ДОВІДКА.md не знайдено жодної `## N.`-секції"
    assert uk == en, (
        "Нумерація `## `-секцій ДОВІДКА.md і HELP.md розійшлася "
        f"(uk={uk}, en={en}) — синхронізуйте переклад."
    )


def test_help_no_internal_repo_md_links():
    """Довідка для користувача: лише публічні URL, не файли репозиторію."""
    for path in (HELP_UK, HELP_EN):
        bad = _internal_repo_md_links(path)
        assert not bad, (
            f"{path.name}: посилання на внутрішні .md (не працюють на ai.w3ir.io): {bad}"
        )
