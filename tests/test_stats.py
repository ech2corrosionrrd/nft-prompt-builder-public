"""Тести агрегованої статистики сайту (services.stats над users.db)."""

import pytest

from services import payment_service, stats

A = "0x" + "ab" * 20
B = "0x" + "cd" * 20


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")


def _seed():
    payment_service.complete_wallet_sign_in(A)        # verified (welcome за conftest=0)
    payment_service.record_payment("tx1", A, 100, 4.99)
    payment_service.deduct_credits(A, 4, engine="OpenAI DALL-E 3", note="img")
    payment_service.deduct_credits(A, 1, engine="LLM", note="build")
    payment_service.grant_credits(B, 50, note="бонус")


def test_overview():
    _seed()
    ov = stats.overview()
    assert ov["users_total"] == 2
    assert ov["users_verified"] == 1            # лише A входив підписом
    assert ov["revenue_usd"] == 4.99
    assert ov["payments_count"] == 1
    assert ov["credits_sold"] == 100
    # A: 100 - 5 + 5welcome ... перевіряємо лише що >0 і дорівнює сумі балансів
    assert ov["credits_outstanding"] == payment_service.get_balance(A) + payment_service.get_balance(B)


def test_generations_by_engine():
    _seed()
    by = {e["engine"]: e for e in stats.generations_by_engine()}
    assert by["OpenAI DALL-E 3"]["count"] == 1
    assert by["OpenAI DALL-E 3"]["credits_spent"] == 4
    assert by["LLM"]["credits_spent"] == 1


def test_credits_by_kind():
    _seed()
    kinds = stats.credits_by_kind()
    assert kinds["payment"] == 100
    assert kinds["grant"] == 50
    assert kinds["debit"] == -5     # списано 4+1 (зберігається від'ємним)


def test_top_wallets():
    _seed()
    top = stats.top_wallets()
    assert top[0]["wallet"] == A           # лише A має списання
    assert top[0]["credits_spent"] == 5
    assert all(w["wallet"] != B for w in top)  # B без debit — не у топі витрат


def test_new_users_counts_recent():
    _seed()
    assert stats.new_users(7) == 2         # обидва щойно створені
    assert stats.new_users(0) == 0         # за «0 днів» — нікого


def _backdate_all_transactions(days: int):
    """Зсунути created_at усіх транзакцій назад на N днів (для тесту вікна)."""
    from contextlib import closing
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with closing(payment_service._connect()) as c:
        c.execute("UPDATE transactions SET created_at = ?", (old,))
        c.commit()


def test_funnel_basic():
    _seed()
    fn = stats.funnel(30)
    assert fn["new_verified"] == 1          # лише A входив підписом
    assert fn["paying_wallets"] == 1        # A оплатив
    assert fn["first_debit_wallets"] == 1   # A списував
    assert fn["conversion_verified_to_paying_pct"] == 100.0
    # B verified? ні — grant не ставить verified; churn рахує лише старих verified
    assert fn["churn_proxy_verified_no_debit"] == 0  # A щойно verified (не >30д) і має debit


def test_funnel_conversion_none_without_verified():
    fn = stats.funnel(30)
    assert fn["new_verified"] == 0
    assert fn["conversion_verified_to_paying_pct"] is None


def test_payments_by_package_maps_known():
    _seed()                                  # 4.99 / 100 → start
    pkgs = {p["amount_usd"]: p for p in stats.payments_by_package()}
    assert pkgs[4.99]["package_id"] == "start"
    assert pkgs[4.99]["count"] == 1
    assert pkgs[4.99]["credits"] == 100


def test_payments_by_package_unknown():
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("txX", A, 123, 7.77)  # credits=123, $7.77 — не з PACKAGES
    rows = stats.payments_by_package()
    assert rows[0]["package_id"] == "невідомо"


def test_sybil_candidates_flags_spender_without_payment():
    payment_service.complete_wallet_sign_in(B)
    payment_service.grant_credits(B, 100, note="seed")   # баланс без оплати (грант ≠ payment)
    for _ in range(25):
        payment_service.deduct_credits(B, 1, engine="Flux.1 (Replicate)", note="x")
    # A платить і списує — не sybil; B списав 25 без оплат — sybil
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("tx1", A, 100, 4.99)
    payment_service.deduct_credits(A, 30, engine="Flux.1 (Replicate)", note="ok")
    cand = stats.sybil_candidates(20, 20)
    wallets = {c["wallet"] for c in cand}
    assert B in wallets
    assert A not in wallets
    assert next(c for c in cand if c["wallet"] == B)["credits_spent"] == 25


def test_recent_payments_order():
    payment_service.complete_wallet_sign_in(A)
    payment_service.record_payment("tx1", A, 100, 4.99)
    payment_service.record_payment("tx2", A, 400, 14.99)
    recent = stats.recent_payments(10)
    assert len(recent) == 2
    assert {r["amount_usd"] for r in recent} == {4.99, 14.99}


# ── Інструментація export: воронка generate→export (A8 / напрямок A) ───────────

def test_record_funnel_event_counts_distinct_exporters():
    _seed()  # A має first_debit (генерацію)
    assert payment_service.record_funnel_event(A, "export") is True
    payment_service.record_funnel_event(A, "export")  # повтор тим самим гаманцем
    fn = stats.funnel(30)
    assert fn["exported_wallets"] == 1                 # distinct гаманець, не події
    assert fn["first_debit_wallets"] == 1
    assert fn["conversion_generate_to_export_pct"] == 100.0


def test_funnel_export_zero_when_no_export():
    _seed()
    fn = stats.funnel(30)
    assert fn["exported_wallets"] == 0
    assert fn["conversion_generate_to_export_pct"] == 0.0   # генератор є, експорту нема


def test_conversion_generate_to_export_none_without_generators():
    payment_service.record_funnel_event(A, "export")        # експорт без жодної генерації
    fn = stats.funnel(30)
    assert fn["first_debit_wallets"] == 0
    assert fn["exported_wallets"] == 1
    assert fn["conversion_generate_to_export_pct"] is None  # нема знаменника → None


def test_conversion_never_exceeds_100_cohort_mismatch():
    """Регресія >100%: гаманці, чий ПЕРШИЙ debit поза вікном, але зберігають у вікні.
    Стара формула ділила на first_debit (нові генератори) → saved/first_debit = 2/1 = 200%.
    Когортна підмножина гарантує ≤100%."""
    import sqlite3
    from datetime import datetime, timedelta, timezone

    C = "0x" + "ef" * 20
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    for w in (A, B, C):
        payment_service.complete_wallet_sign_in(w)
        payment_service.grant_credits(w, 100, note="seed")  # баланс, щоб deduct працював
    con = sqlite3.connect(payment_service.DB_PATH)
    for w in (A, B):  # перший debit 60д тому → поза 30д вікном, НЕ в first_debit
        con.execute(
            "INSERT INTO transactions(wallet_address, kind, credits, engine, note, created_at) "
            "VALUES(?,?,?,?,?,?)", (w, "debit", -1, "x", "old", old),
        )
    con.commit()
    con.close()
    for w in (A, B):  # A, B генерують У вікні + зберігають
        payment_service.deduct_credits(w, 1, engine="x", note="now")
        payment_service.record_funnel_event(w, "curator_save")
    payment_service.deduct_credits(C, 1, engine="x", note="now")  # C: перший debit у вікні, без save

    fn = stats.funnel(30)
    assert fn["first_debit_wallets"] == 1      # лише C (A,B перший-debit давній)
    assert fn["curator_save_wallets"] == 2     # A, B зберегли (стара формула: 2/1=200%)
    assert fn["conversion_generate_to_save_pct"] <= 100.0  # ключове: не >100
    assert fn["conversion_generate_to_save_pct"] == 66.7    # |{A,B}∩{A,B,C}|/|{A,B,C}|


def test_record_funnel_event_rejects_empty_fail_open():
    assert payment_service.record_funnel_event("", "export") is False
    assert payment_service.record_funnel_event(A, "") is False


def test_credits_by_kind_since():
    _seed()
    # Усе щойно створене — 7-денне вікно = all-time.
    recent = stats.credits_by_kind_since(7)
    assert recent == stats.credits_by_kind()
    assert recent.get("payment") == 100
    assert recent.get("debit") == -5
    # days=None або 0 — без фільтра (повний зріз).
    assert stats.credits_by_kind_since(None) == stats.credits_by_kind()
    assert stats.credits_by_kind_since(0) == stats.credits_by_kind()
    # Відсунули все на 40 днів — 7-денне вікно порожнє, 90-денне бачить.
    _backdate_all_transactions(40)
    assert stats.credits_by_kind_since(7) == {}
    assert stats.credits_by_kind_since(90).get("payment") == 100
