"""Імпорт фактичних витрат провайдерів (CSV з кабінетів + OpenAI Costs API).

Окрема SQLite `data/provider_spend.db` — не змішуємо з users.db.
Для Replicate/Anthropic/Stability — експорт CSV з billing-сторінки кабінету;
для OpenAI — також `scripts/import_provider_spend.py --fetch openai --days 30`
(потрібен admin-ключ: OPENAI_ADMIN_KEY або OPENAI_API_KEY з правами org).

Шаблон ручного CSV (універсальний):
  provider,period_start,period_end,amount_usd,note
  openai,2026-06-01,2026-06-30,42.50,червень з кабінету
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import httpx

from services import db
from storage import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "provider_spend.db"
TIMEOUT = 30.0

PROVIDERS = frozenset({"openai", "anthropic", "stability", "replicate", "helio", "other"})

# Stability CSV часто в кредитах платформи, не в USD.
STABILITY_USD_PER_CREDIT = float(os.environ.get("STABILITY_USD_PER_CREDIT") or "0.01")


@dataclass(frozen=True)
class SpendRecord:
    provider: str
    period_start: str  # YYYY-MM-DD
    period_end: str
    amount_usd: float
    source: str
    note: str = ""


def _connect() -> sqlite3.Connection:
    # Зʼєднання через шар абстракції (services/db.py): SQLite за замовчуванням,
    # Postgres при DATABASE_URL. UPSERT нижче (ON CONFLICT) — крос-діалектний.
    conn = db.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS spend_records ("
        " id " + db.autoinc_pk() + ","
        " provider TEXT NOT NULL,"
        " period_start TEXT NOT NULL,"
        " period_end TEXT NOT NULL,"
        " amount_usd REAL NOT NULL,"
        " source TEXT NOT NULL,"
        " note TEXT NOT NULL DEFAULT '',"
        " imported_at TEXT NOT NULL,"
        " UNIQUE(provider, period_start, period_end, source))"
    )
    conn.commit()
    return conn


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")


def _parse_date(raw: str) -> str | None:
    s = (raw or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%m/%d/%Y", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date().isoformat()
        except ValueError:
            continue
    if s.isdigit() and len(s) >= 10:
        try:
            return datetime.fromtimestamp(int(s), tz=timezone.utc).date().isoformat()
        except (ValueError, OSError):
            pass
    return None


def _parse_amount(raw: str) -> float | None:
    s = (raw or "").strip().replace("$", "").replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pick_column(headers: list[str], *candidates: str) -> str | None:
    norm = {_norm_header(h): h for h in headers}
    for c in candidates:
        if c in norm:
            return norm[c]
    for h in headers:
        nh = _norm_header(h)
        for c in candidates:
            if c in nh or nh in c:
                return h
    return None


def _normalize_provider(name: str) -> str:
    n = (name or "").strip().lower()
    if n in PROVIDERS:
        return n
    if "openai" in n or "dall" in n or "gpt" in n:
        return "openai"
    if "anthropic" in n or "claude" in n:
        return "anthropic"
    if "stability" in n:
        return "stability"
    if "replicate" in n or "flux" in n:
        return "replicate"
    if "helio" in n:
        return "helio"
    return "other"


def _rows_from_generic(reader: csv.DictReader) -> list[SpendRecord]:
    headers = reader.fieldnames or []
    prov_col = _pick_column(headers, "provider", "vendor", "service")
    start_col = _pick_column(headers, "period_start", "start", "start_date", "from")
    end_col = _pick_column(headers, "period_end", "end", "end_date", "to")
    date_col = _pick_column(headers, "date", "day", "usage_date")
    amt_col = _pick_column(
        headers,
        "amount_usd",
        "amount",
        "cost",
        "cost_usd",
        "usd",
        "total",
        "charge",
        "spend",
    )
    note_col = _pick_column(headers, "note", "description", "memo", "line_item")
    if not amt_col:
        return []

    out: list[SpendRecord] = []
    for row in reader:
        amt = _parse_amount(row.get(amt_col, ""))
        if amt is None or amt < 0:
            continue
        prov = _normalize_provider(row.get(prov_col, "") if prov_col else "other")
        d0 = _parse_date(row.get(start_col, "") if start_col else "")
        d1 = _parse_date(row.get(end_col, "") if end_col else "")
        dd = _parse_date(row.get(date_col, "") if date_col else "")
        if dd and not d0:
            d0 = d1 = dd
        if not d0:
            continue
        if not d1:
            d1 = d0
        note = (row.get(note_col, "") if note_col else "").strip()
        out.append(
            SpendRecord(prov, d0, d1, round(amt, 6), "csv", note)
        )
    return out


def _rows_from_openai_usage(reader: csv.DictReader) -> list[SpendRecord]:
    """Денні або рядкові витрати з OpenAI Usage/Billing export."""
    headers = reader.fieldnames or []
    date_col = _pick_column(headers, "date", "day", "usage_date", "start_time", "timestamp")
    amt_col = _pick_column(
        headers,
        "amount_usd",
        "amount",
        "cost",
        "cost_usd",
        "usd",
        "total_cost",
        "spend",
    )
    if not date_col or not amt_col:
        return []

    by_day: dict[str, float] = {}
    for row in reader:
        d = _parse_date(row.get(date_col, ""))
        amt = _parse_amount(row.get(amt_col, ""))
        if not d or amt is None:
            continue
        by_day[d] = by_day.get(d, 0.0) + amt

    return [
        SpendRecord("openai", d, d, round(v, 6), "csv", "OpenAI export")
        for d, v in sorted(by_day.items())
    ]


def _rows_from_stability_credits(reader: csv.DictReader) -> list[SpendRecord]:
    """CSV з кредитами Stability → USD через STABILITY_USD_PER_CREDIT."""
    headers = reader.fieldnames or []
    date_col = _pick_column(headers, "date", "day", "created_at", "timestamp")
    cred_col = _pick_column(headers, "credits", "amount", "credits_used", "usage")
    if not cred_col:
        return []

    by_day: dict[str, float] = {}
    for row in reader:
        creds = _parse_amount(row.get(cred_col, ""))
        if creds is None:
            continue
        d = _parse_date(row.get(date_col, "") if date_col else "") or datetime.now(timezone.utc).date().isoformat()
        usd = creds * STABILITY_USD_PER_CREDIT
        by_day[d] = by_day.get(d, 0.0) + usd

    return [
        SpendRecord("stability", d, d, round(v, 6), "csv", "Stability credits export")
        for d, v in sorted(by_day.items())
    ]


def detect_provider_from_csv(text: str) -> str | None:
    """Евристика провайдера за заголовками / вмістом."""
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        headers = [_norm_header(h) for h in (reader.fieldnames or [])]
        joined = " ".join(headers)
        if "line_item" in joined or "openai" in text.lower()[:500]:
            return "openai"
        if "anthropic" in joined or "claude" in text.lower()[:300]:
            return "anthropic"
        if "replicate" in joined:
            return "replicate"
        if "stability" in joined or "credits_used" in joined:
            return "stability"
        if _pick_column(reader.fieldnames or [], "provider"):
            return None  # generic з колонкою provider
    except Exception:
        pass
    return None


def parse_csv(text: str, provider: str | None = None) -> list[SpendRecord]:
    """Розбір CSV; provider=auto або None — автовизначення."""
    text = text.lstrip("\ufeff")
    if not text.strip():
        return []

    prov = (provider or "auto").strip().lower()
    if prov == "auto":
        prov = detect_provider_from_csv(text) or "generic"

    reader = csv.DictReader(io.StringIO(text))

    if prov == "openai":
        rows = _rows_from_openai_usage(reader)
        if rows:
            return rows
        reader = csv.DictReader(io.StringIO(text))
        return _rows_from_generic(reader)

    if prov == "stability":
        rows = _rows_from_stability_credits(reader)
        if rows:
            return rows
        reader = csv.DictReader(io.StringIO(text))
        return _rows_from_generic(reader)

    if prov in PROVIDERS and prov != "generic" and prov != "other":
        # replicate / anthropic — спочатку generic з фіксованим provider
        generic = _rows_from_generic(reader)
        if generic:
            return [
                SpendRecord(
                    prov if r.provider == "other" else r.provider,
                    r.period_start,
                    r.period_end,
                    r.amount_usd,
                    r.source,
                    r.note,
                )
                for r in generic
            ]
        reader = csv.DictReader(io.StringIO(text))
        daily = _rows_from_openai_usage(reader)  # той самий date+cost патерн
        return [
            SpendRecord(prov, r.period_start, r.period_end, r.amount_usd, "csv", r.note)
            for r in daily
        ]

    return _rows_from_generic(reader)


def save_records(records: Iterable[SpendRecord]) -> int:
    """UPSERT записів; повертає кількість збережених."""
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    with closing(_connect()) as conn:
        for r in records:
            if r.provider not in PROVIDERS:
                continue
            if r.amount_usd <= 0:
                continue
            conn.execute(
                "INSERT INTO spend_records "
                "(provider, period_start, period_end, amount_usd, source, note, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(provider, period_start, period_end, source) DO UPDATE SET "
                "amount_usd = excluded.amount_usd, note = excluded.note, imported_at = excluded.imported_at",
                (r.provider, r.period_start, r.period_end, r.amount_usd, r.source, r.note, now),
            )
            saved += 1
        conn.commit()
    return saved


def import_csv_text(text: str, provider: str | None = None) -> tuple[int, list[SpendRecord]]:
    rows = parse_csv(text, provider)
    return save_records(rows), rows


def import_csv_file(path: str | Path, provider: str | None = None) -> tuple[int, list[SpendRecord]]:
    text = Path(path).read_text(encoding="utf-8-sig")
    return import_csv_text(text, provider)


def add_manual(
    provider: str,
    period_start: str,
    period_end: str,
    amount_usd: float,
    note: str = "",
) -> int:
    """Один рядок з кабінету (сума за місяць)."""
    rec = SpendRecord(
        _normalize_provider(provider),
        period_start,
        period_end or period_start,
        round(float(amount_usd), 6),
        "manual",
        note,
    )
    return save_records([rec])


def _period_bounds(days: int | None) -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    end = today.isoformat()
    if days is None or days <= 0:
        return "1970-01-01", end
    start = (today - timedelta(days=days)).isoformat()
    return start, end


def total_usd(days: int | None = None, provider: str | None = None) -> float:
    """Сума імпортованих витрат, що перетинають вікно [today-days, today]."""
    start, end = _period_bounds(days)
    sql = (
        "SELECT COALESCE(SUM(amount_usd), 0) FROM spend_records "
        "WHERE period_end >= ? AND period_start <= ?"
    )
    params: list = [start, end]
    if provider:
        sql += " AND provider = ?"
        params.append(_normalize_provider(provider))
    with closing(_connect()) as c:
        return float(c.execute(sql, params).fetchone()[0])


def by_provider(days: int | None = None) -> list[dict]:
    start, end = _period_bounds(days)
    with closing(_connect()) as c:
        rows = c.execute(
            "SELECT provider, COALESCE(SUM(amount_usd), 0), COUNT(*) "
            "FROM spend_records WHERE period_end >= ? AND period_start <= ? "
            "GROUP BY provider ORDER BY 2 DESC",
            (start, end),
        ).fetchall()
    return [
        {"provider": r[0], "amount_usd": round(float(r[1]), 4), "records": int(r[2])}
        for r in rows
    ]


def list_imports(limit: int = 50) -> list[dict]:
    with closing(_connect()) as c:
        rows = c.execute(
            "SELECT provider, period_start, period_end, amount_usd, source, note, imported_at "
            "FROM spend_records ORDER BY period_end DESC, id DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
    return [
        {
            "provider": r[0],
            "period_start": r[1],
            "period_end": r[2],
            "amount_usd": r[3],
            "source": r[4],
            "note": r[5],
            "imported_at": r[6][:19],
        }
        for r in rows
    ]


def _openai_admin_key() -> str | None:
    for env in ("OPENAI_ADMIN_KEY", "OPENAI_API_KEY"):
        key = (os.environ.get(env) or "").strip()
        if key:
            return key
    return None


def fetch_openai_costs(days: int = 30) -> tuple[int, list[SpendRecord], str | None]:
    """Завантажити денні витрати з OpenAI Costs API. Повертає (saved, rows, error)."""
    key = _openai_admin_key()
    if not key:
        return 0, [], "немає OPENAI_ADMIN_KEY / OPENAI_API_KEY"

    days = max(1, min(days, 180))
    start_dt = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=days)
    params: dict = {
        "start_time": int(start_dt.timestamp()),
        "limit": days,
        "bucket_width": "1d",
    }
    headers = {"Authorization": f"Bearer {key}"}
    org = (os.environ.get("OPENAI_ORG_ID") or "").strip()
    if org:
        headers["OpenAI-Organization"] = org

    records: list[SpendRecord] = []
    page: str | None = None
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            while True:
                q = dict(params)
                if page:
                    q["page"] = page
                r = client.get("https://api.openai.com/v1/organization/costs", headers=headers, params=q)
                if r.status_code == 404:
                    return 0, [], "OpenAI Costs API 404 — потрібен admin-ключ організації"
                r.raise_for_status()
                body = r.json()
                for bucket in body.get("data") or []:
                    start_ts = bucket.get("start_time")
                    if start_ts is None:
                        continue
                    day = datetime.fromtimestamp(int(start_ts), tz=timezone.utc).date().isoformat()
                    total = 0.0
                    for item in bucket.get("results") or []:
                        amt = item.get("amount") or {}
                        val = amt.get("value")
                        if val is not None:
                            total += float(val)
                    if total > 0:
                        records.append(
                            SpendRecord("openai", day, day, round(total, 6), "openai_api", "Costs API")
                        )
                if not body.get("has_more"):
                    break
                page = body.get("next_page")
                if not page:
                    break
    except httpx.HTTPError as exc:
        logger.warning("OpenAI costs fetch failed: %s", exc)
        return 0, [], str(exc)

    saved = save_records(records)
    return saved, records, None


def summary_text(days: int | None = None) -> str:
    """Короткий текст для CLI / дайджесту."""
    start, end = _period_bounds(days)
    total = total_usd(days)
    if total <= 0:
        return f"Фактичні витрати API ({start}…{end}): немає імпортів"
    parts = by_provider(days)
    detail = " · ".join(f"{p['provider']} ${p['amount_usd']}" for p in parts)
    return f"Фактичні витрати API ({start}…{end}): ${round(total, 2)} — {detail}"
