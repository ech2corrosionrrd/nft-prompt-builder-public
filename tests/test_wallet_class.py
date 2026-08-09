"""Класифікація гаманців (services.wallet_class) і зрізи метрик по ній.

Контекст (09.08.2026): метрики злипали власну активність із чужою — виторг
$44.93 читався як попит, хоч усі оплати з наших гаманців, а guard «зовнішнього
трафіку» в e67_gate_check рахував і їх. Тести фіксують саме цю межу: внутрішнє не
має потрапляти у зовнішній зріз.

Межа НЕ про «справжність» оплат: оплата з власного гаманця офіційна, і дохід із
маржею рахуються по всьому виторгу (`test_overview_splits_revenue_by_class`
перевіряє, що `revenue_usd` лишається сумарним).
"""

import pytest

from services import margin_report, payment_service, stats, wallet_class

OPERATOR = "0x" + "11" * 20
ADMIN = "0x" + "22" * 20
DOGFOOD = "0x" + "33" * 20
EXTERNAL = "0x" + "44" * 20
SOLANA = "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn"


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


@pytest.fixture
def internal_env(monkeypatch):
    monkeypatch.setenv("OPERATOR_WALLET", OPERATOR)
    monkeypatch.setenv("ADMIN_WALLETS", f"{ADMIN},{OPERATOR}")
    monkeypatch.setenv("DOGFOOD_WALLETS", DOGFOOD)


# ── класифікація ──────────────────────────────────────────────────────────────

def test_internal_wallets_merges_env_keys_and_team(internal_env):
    assert {OPERATOR, ADMIN, DOGFOOD} <= wallet_class.internal_wallets()
    assert wallet_class.TEAM_WALLETS <= wallet_class.internal_wallets()


def test_team_wallets_are_internal_without_any_env():
    """Гаманці команди зашиті в код: 09.08.2026 «перший зовнішній платник» ($29.96)
    виявився нашим treasury, підписаним так у holder_rewards ще до цього модуля —
    але класифікація читала лише env, тож факт із репо не діяв."""
    treasury = "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn"
    assert wallet_class.is_internal(treasury) is True
    assert wallet_class.is_external(treasury) is False


def test_team_wallets_cover_bonus_exclude_list():
    """Гард проти розходження двох списків командних гаманців (дублювання адрес)."""
    from services import holder_rewards
    assert set(holder_rewards.DEFAULT_BONUS_EXCLUDE) <= set(wallet_class.TEAM_WALLETS)


def test_is_internal_ignores_evm_case(monkeypatch):
    monkeypatch.setenv("DOGFOOD_WALLETS", DOGFOOD.upper().replace("0X", "0x"))
    assert wallet_class.is_internal(DOGFOOD) is True
    assert wallet_class.is_external(DOGFOOD) is False


def test_solana_case_is_significant(monkeypatch):
    """base58 регістрозалежний: lower() зіпсував би pubkey (landmine normalize_addr)."""
    monkeypatch.setenv("DOGFOOD_WALLETS", SOLANA)
    assert wallet_class.is_internal(SOLANA) is True
    assert wallet_class.is_internal(SOLANA.lower()) is False


def test_empty_wallet_is_neither(internal_env):
    assert wallet_class.is_internal(None) is False
    assert wallet_class.is_external("") is False
    assert wallet_class.classify(None) == "unknown"


def test_classify(internal_env):
    assert wallet_class.classify(DOGFOOD) == "internal"
    assert wallet_class.classify(EXTERNAL) == "external"


def test_scope_sql_all_is_noop(internal_env):
    assert wallet_class.scope_sql("all") == ("", [])


def test_scope_sql_external_lists_internal_wallets(internal_env):
    sql, params = wallet_class.scope_sql("external")
    assert "NOT IN" in sql and sql.count("?") == 3 + len(wallet_class.TEAM_WALLETS)
    assert {OPERATOR, ADMIN, DOGFOOD} <= set(params)


def test_scope_sql_internal_without_env_still_filters_team():
    """Без env лишаються командні гаманці — 'internal' не має ставати «всі»."""
    sql, params = wallet_class.scope_sql("internal")
    assert " IN (" in sql and len(params) == len(wallet_class.TEAM_WALLETS)
    sql_ext, params_ext = wallet_class.scope_sql("external")
    assert " NOT IN (" in sql_ext and len(params_ext) == len(wallet_class.TEAM_WALLETS)


def test_scope_sql_internal_empty_list_selects_nothing(monkeypatch):
    """Асиметрія лишається робочою: порожній список → порожня вибірка, не всі."""
    monkeypatch.setattr(wallet_class, "TEAM_WALLETS", frozenset())
    assert wallet_class.scope_sql("internal") == (" AND 1 = 0", [])
    assert wallet_class.scope_sql("external") == ("", [])


def test_scope_sql_rejects_unknown_scope():
    with pytest.raises(ValueError, match="scope"):
        wallet_class.scope_sql("everyone")


# ── зрізи метрик ──────────────────────────────────────────────────────────────

def _seed():
    """Двоє платять (dogfood + зовнішній), обидва генерують і зберігають."""
    for w in (DOGFOOD, EXTERNAL):
        payment_service.complete_wallet_sign_in(w)
        payment_service.record_payment(f"tx-{w[-4:]}", w, 100, 4.99)
        payment_service.deduct_credits(w, 8, engine="OpenAI gpt-image-1", note="image generation")
        payment_service.record_funnel_event(w, "generate", {"count": 1, "source": "pipeline"})
        payment_service.record_funnel_event(w, "curator_save", {"items": 1, "avg_rating": 5.0})
        payment_service.record_funnel_event(w, "export")


def test_overview_splits_revenue_by_class(internal_env):
    _seed()
    ov = stats.overview()
    assert ov["revenue_usd"] == 9.98                 # сумарний як був
    assert ov["revenue_usd_external"] == 4.99        # лише чужі гроші
    assert ov["revenue_usd_internal"] == 4.99
    assert ov["payments_count_external"] == 1
    assert ov["users_external"] == 1
    assert ov["internal_wallets_known"] == 3 + len(wallet_class.TEAM_WALLETS)


def test_overview_without_env_counts_test_wallets_external():
    """Без env-списків зовнішніми лишаються всі, крім командних (ті — в коді)."""
    _seed()
    ov = stats.overview()
    assert ov["revenue_usd_external"] == ov["revenue_usd"] == 9.98
    assert ov["internal_wallets_known"] == len(wallet_class.TEAM_WALLETS)


def test_funnel_external_scope_excludes_dogfood(internal_env):
    _seed()
    all_scope = stats.funnel(days=30)
    ext = stats.funnel(days=30, scope="external")
    assert all_scope["first_debit_wallets"] == 2
    assert ext["first_debit_wallets"] == 1          # guard §2.8 бачить лише чужий трафік
    assert ext["paying_wallets"] == 1
    assert ext["exported_wallets"] == 1
    assert ext["scope"] == "external"


def test_funnel_internal_scope_is_mirror(internal_env):
    _seed()
    internal = stats.funnel(days=30, scope="internal")
    assert internal["first_debit_wallets"] == 1
    assert internal["paying_wallets"] == 1


def test_quality_summary_external_scope(internal_env):
    _seed()
    assert stats.quality_summary(days=30)["generate_events"] == 2
    ext = stats.quality_summary(days=30, scope="external")
    assert ext["generate_events"] == 1
    assert ext["save_events"] == 1
    assert ext["generate_source_images"]["pipeline"] == 1
    assert ext["scope"] == "external"


def test_admin_feeds_mark_internal_rows(internal_env):
    _seed()
    by_wallet = {r["wallet"]: r["internal"] for r in stats.top_wallets(10)}
    assert by_wallet[DOGFOOD] is True
    assert by_wallet[EXTERNAL] is False
    assert {r["wallet"]: r["internal"] for r in stats.recent_payments(10)}[DOGFOOD] is True


def test_margin_report_shows_dogfood_separately(internal_env):
    _seed()
    r = margin_report.gross_margin_report()
    assert r["revenue_usd"] == 9.98
    assert r["revenue_usd_external"] == 4.99
    assert r["revenue_usd_internal"] == 4.99
    assert r["payments_count_external"] == 1
    text = margin_report.format_report_text(r)
    assert "джерело:" in text                 # нейтральна довідка про джерело
    assert "$9.98" in text                    # дохід у звіті — ПОВНИЙ, не зовнішній


def test_margin_report_hides_source_line_without_own_payments():
    _seed()
    text = margin_report.format_report_text(margin_report.gross_margin_report())
    assert "джерело:" not in text         # нема своїх оплат → нема шумного рядка
