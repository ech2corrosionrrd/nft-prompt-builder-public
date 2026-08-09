"""Класифікація гаманців: внутрішні (адмін/оператор/dogfood) vs зовнішні.

**Що цей модуль НЕ робить: не оголошує чиїсь оплати «несправжніми».** Оплата з
власного гаманця через Helio — офіційна: реальний USDC, реальна комісія, кредити,
які далі витрачаються на реальні виклики API. Тому дохід, маржа, ARPU й
utilization рахуються по **всьому** виторгу, і жоден зріз нічого з нього не
віднімає. Платити собі, а не нараховувати кредити скриптом, — свідома практика:
інакше в знаменнику маржі стояли б безкоштовні кредити.

Навіщо тоді шар: одне питання — «чи хтось **поза** проєктом цього хотів» — на
сумарному числі не має відповіді, коли платник і продавець одна особа. Єдиний
обов'язковий споживач зовнішнього зрізу — guard достатності трафіку в
`e67_gate_check`, який і ставився, щоб не ухвалити GO на власній активності.
Історія 09.08.2026 — розбір прод-БД показав, що метрики злипались у трьох місцях:

- «останній generate 19.07» у ПЛАН_ДІЙ був останнім generate **оператора**
  (`OPERATOR_WALLET`), тоді як другий власний гаманець генерував 08.08, а
  єдиний зовнішній платник відпав 11.07;
- виторг $44.93 подавався як зовнішній попит, хоч усі оплати — з наших гаманців;
- `e67_gate_check` називав `first_debit_wallets` «зовнішніми», хоч метрика
  включала внутрішні гаманці — тобто guard достатності трафіку можна було
  закрити власними руками.

Джерело списку — env: `ADMIN_WALLETS` (список), `OPERATOR_WALLET` (один),
`DOGFOOD_WALLETS` (список власних гаманців, що платять РЕАЛЬНИМИ грошима для
перевірки шляху й тому осідають у `payments` як звичайні клієнти). Три ключі, а
не один, бо роль різна: адмін — доступ, оператор — grant-канал, dogfood — лише
класифікація метрик.

Порівняння — через `auth_gateway.normalize_addr` (EVM → нижній регістр, Solana
base58 як є), тим самим правилом, що `admin_access` і `payment_service.
normalize_wallet`: у БД адреси вже нормалізовані на записі, тож у SQL порівнюємо
колонку напряму — **без** `LOWER()`, який зіпсував би Solana-pubkey.
"""

from __future__ import annotations

import os

from services.auth_gateway import normalize_addr

# Зрізи для звітів/гейтів. 'all' — сумісність із поведінкою до класифікації.
SCOPES = ("all", "external", "internal")

# Env-ключі, що дають внутрішні гаманці (кожен — CSV; OPERATOR_WALLET зазвичай один).
INTERNAL_ENV_KEYS = ("ADMIN_WALLETS", "OPERATOR_WALLET", "DOGFOOD_WALLETS")

# Командні/протокольні гаманці — **у коді, не в env**. Причина рівно та, через яку
# знадобився цей модуль: 09.08.2026 «перший зовнішній платник» ($29.96, 4 оплати,
# 128 списань, на якому стояли всі конверсії воронки й «механічно GO E6») виявився
# нашим **treasury** — він два роки як підписаний саме так у `holder_rewards.py` і
# `vault_registry.py`, але класифікація читала лише env, і оператор мусив би
# продублювати адресу руками. Факт, який уже зафіксований у репо, не має залежати
# від того, чи згадав про нього оператор.
#
# Кожен рядок — чому гаманець наш:
TEAM_WALLETS = frozenset({
    "63u6SDZckvzcJhC4V5yJn6bZ15qx1iM8c6iB3Z9xD1tn",  # treasury / team mints
    "DE1gBEaqA11uYdySmF5LRmN8QsvXvnYJYHDVXeAY15Vh",  # deployer (ключ сейфу)
    "7XTEnenjjLi2Pr8ShUPYo1DXKm3WZRLoD2rQpiq7E6qw",  # холодна authority CM+Guard (ПЛАН_КАСТОДІЯ §8)
    "1BWutmTvYPwDtmw9abTkS4Ssr8no61spGAvW1X6NDix",   # Solana-dogfood оператора
})


def internal_wallets() -> set[str]:
    """Нормалізовані внутрішні гаманці: env-списки + командні гаманці з коду."""
    out = {normalize_addr(w) for w in TEAM_WALLETS}
    for key in INTERNAL_ENV_KEYS:
        raw = os.environ.get(key) or ""
        out |= {normalize_addr(w) for w in raw.split(",") if w.strip()}
    return out


def is_internal(wallet: str | None) -> bool:
    """True, якщо гаманець наш (адмін / оператор / dogfood)."""
    if not wallet:
        return False
    return normalize_addr(wallet) in internal_wallets()


def is_external(wallet: str | None) -> bool:
    """True для чужого гаманця. Порожня адреса не є зовнішнім користувачем."""
    if not wallet:
        return False
    return not is_internal(wallet)


def classify(wallet: str | None) -> str:
    """'internal' / 'external' / 'unknown' (порожня адреса) — для рядків звітів."""
    if not wallet:
        return "unknown"
    return "internal" if is_internal(wallet) else "external"


def scope_sql(scope: str = "all", column: str = "wallet_address") -> tuple[str, list[str]]:
    """SQL-хвіст (` AND …`) + параметри для фільтра за класом гаманця.

    Розрахований на дописування до запиту, який уже має `WHERE` (при потребі —
    `WHERE 1 = 1`). Плейсхолдери `?` не міняємо: шим Postgres у `services/db.py`
    перекладає їх сам.

    Порожній список внутрішніх гаманців трактуємо асиметрично: `external` →
    фільтрувати нічого (усі й так зовнішні), а `internal` → свідомо порожня
    вибірка (`AND 1 = 0`). Інакше звіт «внутрішні» тихо показував би всіх —
    найгірший вид помилки для метрики, яку читають як «наше vs чуже». Гілка
    лишається робочою, хоч `TEAM_WALLETS` і не дає списку бути порожнім: вона
    страхує випадок, коли команду колись перенесуть у конфіг.
    """
    if scope not in SCOPES:
        raise ValueError(f"scope має бути одним із {SCOPES}, а не {scope!r}")
    if scope == "all":
        return "", []
    wallets = sorted(internal_wallets())
    if not wallets:
        return (" AND 1 = 0", []) if scope == "internal" else ("", [])
    holes = ", ".join("?" for _ in wallets)
    op = "NOT IN" if scope == "external" else "IN"
    return f" AND {column} {op} ({holes})", wallets
