"""Тести services/offsite_status.py — зведення стану off-site бекапів для дайджесту."""

from datetime import datetime

from services import offsite_status

NOW = datetime(2026, 6, 21, 20, 0, 0)


def _line(ts: str, kind: str, source: str, snap: str = "users_x.db") -> str:
    if kind == "ok":
        return f"{ts},123 INFO: offsite OK ({source}): {snap} -> proton:nft-builder-backups (verified)"
    return f"{ts},123 ERROR: offsite backup FAIL ({source}): RuntimeError boom"


def test_empty_log_flags_missing():
    s = offsite_status.summarize("", now=NOW)
    assert s["has_any"] is False and s["stale"] is True
    assert "немає жодної" in offsite_status.digest_line(s)


def test_fresh_ok_counts_window_and_age():
    log = "\n".join([
        _line("2026-06-20 18:00:00", "ok", "auto"),   # > 24г тому → поза вікном
        _line("2026-06-21 08:00:00", "ok", "auto"),   # у вікні
        _line("2026-06-21 19:00:00", "ok", "manual"), # у вікні, найсвіжіша
    ])
    s = offsite_status.summarize(log, now=NOW)
    assert s["ok_window"] == 2
    assert s["fail_window"] == 0
    assert s["last_ok_source"] == "manual"
    assert round(s["age_hours"], 1) == 1.0
    assert s["stale"] is False
    line = offsite_status.digest_line(s)
    assert line.startswith("💾 Off-site бекап: ✅ 2 за 24г")
    assert "1.0г тому" in line


def test_stale_when_last_ok_too_old():
    # Остання успішна копія 13 год тому (> 8) → застаріла.
    log = _line("2026-06-21 07:00:00", "ok", "auto")
    s = offsite_status.summarize(log, now=NOW)
    assert s["stale"] is True
    line = offsite_status.digest_line(s)
    assert "⚠️" in line and "застаріла" in line


def test_failures_in_window_flag_warning():
    log = "\n".join([
        _line("2026-06-21 19:00:00", "ok", "auto"),
        _line("2026-06-21 19:30:00", "fail", "auto"),
    ])
    s = offsite_status.summarize(log, now=NOW)
    assert s["fail_window"] == 1 and s["stale"] is False
    line = offsite_status.digest_line(s)
    assert "⚠️" in line and "збоїв: 1" in line


def test_status_line_missing_file_failopen(tmp_path):
    line = offsite_status.status_line(log_path=tmp_path / "absent.log", now=NOW)
    assert "немає жодної" in line


# ── host-level бекап (той самий парсер, інші regex/label) ───────────────────

def _host_line(ts: str, kind: str, source: str, snap: str = "provider_spend_x.db") -> str:
    if kind == "ok":
        return f"{ts},1 INFO: host backup OK ({source}): {snap} -> gdrive:bk/host/db (verified) assets=[workspace] skipped=[]"
    return f"{ts},1 ERROR: host backup FAIL ({source}): RuntimeError boom"


def test_host_summarize_parses_host_lines():
    log = "\n".join([
        _host_line("2026-06-21 08:00:00", "ok", "auto"),
        _host_line("2026-06-21 19:00:00", "ok", "manual"),
    ])
    s = offsite_status.summarize(
        log, now=NOW, ok_re=offsite_status._HOST_OK_RE, fail_re=offsite_status._HOST_FAIL_RE
    )
    assert s["ok_window"] == 2 and s["last_ok_source"] == "manual"
    # offsite-regex НЕ має ловити host-рядки (розділені простори).
    assert offsite_status.summarize(log, now=NOW)["has_any"] is False


def test_host_status_line_label(tmp_path):
    log = tmp_path / "host_backup.log"
    log.write_text(_host_line("2026-06-21 19:00:00", "ok", "auto"), encoding="utf-8")
    line = offsite_status.host_status_line(log_path=log, now=NOW)
    assert line.startswith("🗄 Host-бекап: ✅")


def test_host_status_line_missing_file_failopen(tmp_path):
    line = offsite_status.host_status_line(log_path=tmp_path / "absent.log", now=NOW)
    assert line.startswith("🗄 Host-бекап:") and "немає жодної" in line


# ── metadata-бекап (GitHub) ────────────────────────────────────────────────

def test_metadata_status_line_ok(tmp_path):
    log = tmp_path / "metadata_backup.log"
    log.write_text(
        "2026-06-21 19:00:00,1 INFO: metadata backup OK (auto): abc1234 (59 файлів, +3/-0)",
        encoding="utf-8",
    )
    line = offsite_status.metadata_status_line(log_path=log, now=NOW)
    assert line.startswith("📦 Metadata-бекап (GitHub): ✅")


def test_metadata_status_line_missing_file_failopen(tmp_path):
    line = offsite_status.metadata_status_line(log_path=tmp_path / "absent.log", now=NOW)
    assert line.startswith("📦 Metadata-бекап (GitHub):") and "немає жодної" in line


def test_digest_includes_offsite_line(monkeypatch):
    # alerts.digest_text має містити рядок про бекап.
    from services import alerts
    monkeypatch.setattr(alerts.offsite_status, "status_line", lambda: "💾 Off-site бекап: ✅ 4 за 24г · остання 1.0г тому")
    # Решту важких залежностей дайджесту глушимо до мінімуму.
    monkeypatch.setattr(alerts.stats, "overview", lambda: {
        "users_total": 0, "users_verified": 0, "revenue_usd": 0, "credits_outstanding": 0})
    monkeypatch.setattr(alerts.stats, "new_users", lambda d: 0)
    monkeypatch.setattr(alerts.provider_status, "stability_balance", lambda: None)
    monkeypatch.setattr(alerts.stats, "generations_by_engine", lambda: [])
    monkeypatch.setattr(alerts.margin_report, "gross_margin_report", lambda: {"gross_margin_pct": None})
    monkeypatch.setattr(alerts.margin_report, "break_even_summary", lambda: {"break_even_count": 0})
    monkeypatch.setattr(alerts.stats, "funnel", lambda d: {})
    monkeypatch.setattr(alerts.stats, "quality_summary", lambda d: {})
    monkeypatch.setattr(alerts, "quality_alert_messages", lambda qs, fn: [])
    text = alerts.digest_text()
    assert "💾 Off-site бекап:" in text
