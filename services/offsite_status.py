"""Зведення стану off-site бекапів із logs/*.log — для денного дайджесту.

Чиста функція (без Streamlit, без мережі): парсить лог, який пише
scripts/offsite_backup.py (users.db) чи scripts/host_backup.py (host-level:
provider_spend.db + workspace/public/…), і дає короткий рядок для
`alerts.digest_text()`. Свіжість копії (staleness) тут важлива: якщо планувальник
тихо перестав запускатись, per-run алертів не буде (бо немає падіння) —
застарілість ловить саме дайджест.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "logs" / "offsite_backup.log"
HOST_LOG_PATH = ROOT / "logs" / "host_backup.log"
METADATA_LOG_PATH = ROOT / "logs" / "metadata_backup.log"

# Формат рядків: "2026-06-21 19:49:58,948 INFO: offsite OK (auto): users_X.db -> dest (verified)"
_OK_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\D.*offsite OK \((\w+)\): (\S+)")
_FAIL_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\D.*offsite backup FAIL \((\w+)\)")
# host_backup.py пише "host backup OK (auto): provider_spend_X.db -> dest".
_HOST_OK_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\D.*host backup OK \((\w+)\): (\S+)")
_HOST_FAIL_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\D.*host backup FAIL \((\w+)\)")
# metadata_backup.py пише "metadata backup OK (auto): <commit|no> ...".
_META_OK_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\D.*metadata backup OK \((\w+)\): (\S+)")
_META_FAIL_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\D.*metadata backup FAIL \((\w+)\)")

# Завдання йде кожні 6 год; >8 год без успішної копії = щось не так.
DEFAULT_STALE_HOURS = 8


def _parse_ts(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def summarize(
    log_text: str,
    *,
    now: datetime | None = None,
    window_hours: int = 24,
    stale_hours: int = DEFAULT_STALE_HOURS,
    ok_re: re.Pattern = _OK_RE,
    fail_re: re.Pattern = _FAIL_RE,
) -> dict:
    """Зводить події бекапу: к-сть OK/FAIL за вікно + вік останньої успішної копії.

    ok_re/fail_re дають один парсер для обох логів (offsite users.db і host-level).
    """
    now = now or datetime.now()
    since = now - timedelta(hours=window_hours)
    ok_window = 0
    fail_window = 0
    last_ok: tuple[datetime, str, str] | None = None  # (dt, snapshot, source)

    for line in log_text.splitlines():
        m = ok_re.search(line)
        if m:
            dt = _parse_ts(m.group(1))
            if last_ok is None or dt > last_ok[0]:
                last_ok = (dt, m.group(3), m.group(2))
            if dt >= since:
                ok_window += 1
            continue
        m = fail_re.search(line)
        if m and _parse_ts(m.group(1)) >= since:
            fail_window += 1

    age_hours = (now - last_ok[0]).total_seconds() / 3600 if last_ok else None
    stale = last_ok is None or (age_hours is not None and age_hours > stale_hours)
    return {
        "ok_window": ok_window,
        "fail_window": fail_window,
        "last_ok_snapshot": last_ok[1] if last_ok else None,
        "last_ok_source": last_ok[2] if last_ok else None,
        "age_hours": age_hours,
        "stale": stale,
        "has_any": last_ok is not None,
    }


def digest_line(summary: dict, *, label: str = "💾 Off-site бекап") -> str:
    """Один рядок для денного дайджесту (label відрізняє offsite vs host-бекап)."""
    if not summary["has_any"]:
        return f"{label}: ⚠️ немає жодної успішної копії"
    age = summary["age_hours"]
    age_str = f"{age:.1f}г тому" if age < 48 else f"{age / 24:.0f}д тому"
    icon = "⚠️" if (summary["stale"] or summary["fail_window"] > 0) else "✅"
    parts = [f"{label}: {icon} {summary['ok_window']} за 24г", f"остання {age_str}"]
    if summary["fail_window"]:
        parts.append(f"❌ збоїв: {summary['fail_window']}")
    if summary["stale"]:
        parts.append("⏰ застаріла")
    return " · ".join(parts)


def status_line(log_path: Path | None = None, now: datetime | None = None) -> str:
    """Читає offsite-лог (fail-open: нема файлу → попередження) і дає рядок дайджесту."""
    try:
        text = (log_path or LOG_PATH).read_text(encoding="utf-8")
    except OSError:
        text = ""
    return digest_line(summarize(text, now=now))


def host_status_line(log_path: Path | None = None, now: datetime | None = None) -> str:
    """Рядок дайджесту для бекапу provider_spend.db на Proton."""
    try:
        text = (log_path or HOST_LOG_PATH).read_text(encoding="utf-8")
    except OSError:
        text = ""
    summary = summarize(text, now=now, ok_re=_HOST_OK_RE, fail_re=_HOST_FAIL_RE)
    return digest_line(summary, label="🗄 Host-бекап")


def metadata_status_line(log_path: Path | None = None, now: datetime | None = None) -> str:
    """Рядок дайджесту для бекапу метаданих проєктів у приватний GitHub."""
    try:
        text = (log_path or METADATA_LOG_PATH).read_text(encoding="utf-8")
    except OSError:
        text = ""
    summary = summarize(text, now=now, ok_re=_META_OK_RE, fail_re=_META_FAIL_RE)
    return digest_line(summary, label="📦 Metadata-бекап (GitHub)")
