"""Гард проти env-empty-defeats-default для ЧИСЛОВИХ читань.

`int(os.environ.get("K", "5"))` падає `ValueError`, якщо `K=` порожній у .env
(`int("")`). Безпечний патерн — `int(os.environ.get("K") or "5")`: порожнє й
відсутнє трактуються однаково. Цей тест ловить регресію (новий числовий 2-арг
get) у продакшн-коді. Контекст: [[env-empty-defeats-default]] / commit-серія 2026-06-27.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (int|float), що ОБГОРТАЄ os.environ.get/getenv із комою (2-арг default) до `)`.
# Безпечна форма `... or default` коми в самому get не має → не матчиться.
_NUMERIC_2ARG_GET = re.compile(r"(?:int|float)\(\s*os\.(?:environ\.get|getenv)\(\s*[^()]*,")


def test_no_numeric_env_get_with_inline_default():
    offenders: dict[str, str] = {}
    for path in ROOT.rglob("*.py"):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if _NUMERIC_2ARG_GET.search(line):
                offenders[f"{path.relative_to(ROOT)}:{i}"] = line.strip()
    assert not offenders, (
        "Числовий env-read із 2-арг default — порожнє значення дасть ValueError. "
        "Заміни на `(int|float)(os.environ.get(key) or default)`:\n"
        + "\n".join(f"  {k}  {v}" for k, v in offenders.items())
    )
