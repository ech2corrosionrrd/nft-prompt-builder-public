"""backup_health.py — перевірка, що бекапи БД реально свіжі.

Навіщо окрема перевірка: погодинний бекап живе в cron на VPS, а cron ламається
тихо. `docker compose exec` не знайшов контейнер, диск заповнився, змінилась назва
сервісу — задача просто перестає створювати файли, і про це ніхто не дізнається аж
до моменту, коли копія знадобилась. Наявність теки `backups/` заспокоює, а лежать
там файли тижневої давності.

Тут — чиста функція (без Streamlit і без мережі): дивиться на НАЙНОВІШИЙ файл у
теці й каже, чи він достатньо свіжий і не порожній. Викликається зі
`scripts/daily_health_check.py`, який шле Telegram-алерт.

Свідомо НЕ перевіряє вміст БД: цілісність round-trip'ом доводить
`scripts/verify_backup.py`, тут — дешева перевірка «пульсу», яку не шкода ганяти
щодня поруч із health-ендпоінтами.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Погодинний cron + запас на довгий бекап великої БД. Дві пропущені години —
# це вже не «пощастило не збігтися», а поламаний розклад.
DEFAULT_MAX_AGE_HOURS = 2.0


@dataclass(frozen=True)
class BackupStatus:
    ok: bool
    problem: str | None
    newest_name: str | None
    age_hours: float | None
    count: int
    newest_bytes: int


def max_age_hours() -> float:
    raw = os.environ.get("BACKUP_MAX_AGE_HOURS") or ""
    try:
        val = float(raw)
    except ValueError:
        return DEFAULT_MAX_AGE_HOURS
    return val if val > 0 else DEFAULT_MAX_AGE_HOURS


def check_backups(
    backup_dir: Path,
    *,
    pattern: str = "*.db",
    max_age: float | None = None,
    now: datetime | None = None,
) -> BackupStatus:
    """Стан найновішого бекапу в теці. Свіжість беремо з mtime, не з назви файлу.

    Назву формує скрипт бекапу, і вона збрехала б, якби той скрипт зламався на
    середині (файл створено, дані не дописані) — mtime такого файлу теж старий
    лише за годинником, тож додатково перевіряємо непорожність.
    """
    limit = max_age if max_age is not None else max_age_hours()
    moment = now or datetime.now(timezone.utc)

    if not backup_dir.is_dir():
        return BackupStatus(False, f"теки {backup_dir} не існує", None, None, 0, 0)

    files = [p for p in backup_dir.glob(pattern) if p.is_file()]
    if not files:
        return BackupStatus(False, f"у {backup_dir} немає жодного бекапу", None, None, 0, 0)

    newest = max(files, key=lambda p: p.stat().st_mtime)
    stat = newest.stat()
    age = (moment - datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)).total_seconds() / 3600.0

    if stat.st_size == 0:
        return BackupStatus(False, f"найновіший бекап порожній: {newest.name}", newest.name, age, len(files), 0)

    if age > limit:
        return BackupStatus(
            False,
            f"найновішому бекапу {age:.1f} год (ліміт {limit:.0f}) — розклад бекапів зупинився",
            newest.name,
            age,
            len(files),
            stat.st_size,
        )

    return BackupStatus(True, None, newest.name, age, len(files), stat.st_size)


def summary_text(status: BackupStatus) -> str:
    """Рядок для Telegram-алерту / логу."""
    if status.ok:
        mb = status.newest_bytes / (1024 * 1024)
        return (
            f"✅ Бекапи: {status.newest_name} "
            f"({status.age_hours:.1f} год тому, {mb:.1f} МБ, всього {status.count})"
        )
    return f"❌ Бекапи: {status.problem}"
