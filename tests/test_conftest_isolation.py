"""Гард: жоден тест не пише в бойові БД і теки.

Історія класу «побічна дія втекла з ізоляції» — четвертий випадок поспіль:
`holder_rewards` заливав фейкові мінти в C:\\Sugar\\data (340ef27), `b2b_service`
створював робочі партнерські ключі в бойовому сторі (d7e5a18), `backup_health`
читав реальну теку бекапів розробника, а `payment_service` дописував синтетичні
транзакції в data/users.db — і вони доїхали в прод з копією БД при міграції на
нового хостингу, зіпсувавши метрики, на яких приймався go/no-go E6/E7.

Кожен із цих випадків знаходили постфактум і руками. Цей файл ловить регресію
одразу: якщо хтось прибере рядок із conftest, тут стане червоно.
"""

from pathlib import Path

from services import b2b_service, payment_service

# Бойові шляхи, у які тест не має права писати за жодних обставин.
_PROD_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_payment_db_is_isolated():
    """Основна БД (кредити/транзакції/платежі/воронка) — поза data/."""
    assert _PROD_DATA_DIR not in Path(payment_service.DB_PATH).parents, (
        f"payment_service.DB_PATH вказує в бойову теку: {payment_service.DB_PATH}. "
        "Перевір автофікстуру _isolate_secrets у conftest.py."
    )


def test_b2b_db_is_isolated():
    """B2B-ключі: без ізоляції тести створюють робочі партнерські ключі."""
    assert _PROD_DATA_DIR not in Path(b2b_service.DB_PATH).parents, (
        f"b2b_service.DB_PATH вказує в бойову теку: {b2b_service.DB_PATH}."
    )


def test_payment_and_b2b_dbs_are_separate_files():
    """У проді обидва — data/users.db; у тестах свідомо різні файли.

    Фіксуємо як факт, а не як бажане: тест, що покладеться на спільну БД
    (напр. звірка b2b_keys із transactions), тут одразу побачить розбіжність
    із продом і не буде «зеленим випадково».
    """
    assert Path(payment_service.DB_PATH) != Path(b2b_service.DB_PATH)


def test_writes_land_in_tmp_not_in_prod_db(tmp_path):
    """Наскрізна перевірка: реальний запис через API не торкається data/users.db."""
    wallet = "0x" + "ab" * 20
    payment_service.complete_wallet_sign_in(wallet)
    payment_service.grant_credits(wallet, 10, note="isolation-check")

    assert Path(payment_service.DB_PATH).is_file()
    assert payment_service.get_balance(wallet) >= 10

    prod_db = _PROD_DATA_DIR / "users.db"
    if prod_db.is_file():
        import sqlite3

        con = sqlite3.connect(prod_db)
        try:
            (n,) = con.execute(
                "SELECT COUNT(*) FROM transactions WHERE note = 'isolation-check'"
            ).fetchone()
        finally:
            con.close()
        assert n == 0, "запис із тесту потрапив у бойову data/users.db"
