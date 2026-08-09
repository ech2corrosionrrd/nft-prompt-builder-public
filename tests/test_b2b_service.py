from services import b2b_service
from services.b2b_service import (
    generate_b2b_api_key,
    list_b2b_keys,
    record_b2b_usage,
    verify_b2b_api_key,
)
from storage import DATA_DIR


def test_does_not_write_into_prod_db():
    """Гард ізоляції: тести НЕ мають створювати ключі в бойовій users.db.

    Раніше стор був JSON-файлом без ізоляції, і кожен прогін pytest додавав туди
    робочий партнерський ключ (накопичилось 11). Якщо `conftest` перестане
    підміняти DB_PATH — падає тут, а не мовчки в проді.
    """
    assert b2b_service.DB_PATH != DATA_DIR / "users.db"


def test_verify_b2b_api_key_valid():
    key = "b2b_test_key_w3ir_2026"
    client = verify_b2b_api_key(key)
    assert client is not None
    assert client["client_name"] == "Staging Partner DAO"
    assert client["quota"] == 1000


def test_verify_b2b_api_key_invalid():
    assert verify_b2b_api_key("invalid_key_123") is None
    assert verify_b2b_api_key(None) is None


def test_generate_and_use_b2b_key():
    new_key = generate_b2b_api_key("Partner Studio", quota=50)
    assert new_key.startswith("w3ir_b2b_")

    client = verify_b2b_api_key(new_key)
    assert client["client_name"] == "Partner Studio"
    assert client["used"] == 0

    success = record_b2b_usage(new_key, 5)
    assert success is True
    assert verify_b2b_api_key(new_key)["used"] == 5


def test_usage_persists_across_calls():
    """Лічильник живе в БД, а не в памʼяті процесу — інкременти накопичуються."""
    key = generate_b2b_api_key("Persist DAO", quota=10)
    for _ in range(3):
        assert record_b2b_usage(key, 2) is True
    assert verify_b2b_api_key(key)["used"] == 6


def test_record_usage_refuses_over_quota():
    """Списання all-or-nothing: понад квоту не проходить і не псує лічильник."""
    key = generate_b2b_api_key("Small Quota DAO", quota=5)
    assert record_b2b_usage(key, 4) is True
    assert record_b2b_usage(key, 2) is False  # 4+2 > 5 — відмова цілком
    assert verify_b2b_api_key(key)["used"] == 4
    assert record_b2b_usage(key, 1) is True  # рівно до межі — можна
    # Квота вичерпана → ключ більше не валідний для нових генерацій.
    assert verify_b2b_api_key(key) is None


def test_record_usage_unknown_key():
    assert record_b2b_usage("nope_not_a_key", 1) is False
    assert record_b2b_usage("", 1) is False


def test_list_b2b_keys_contains_generated():
    key = generate_b2b_api_key("Listed DAO", quota=7)
    listed = {r["api_key"]: r for r in list_b2b_keys()}
    assert key in listed
    assert listed[key]["client_name"] == "Listed DAO"
    assert listed[key]["quota"] == 7
    assert listed[key]["active"] is True
    # Демо-ключ стенду сідиться в таблицю, а не живе паралельним dict у памʼяті.
    assert "b2b_test_key_w3ir_2026" in listed


def test_staging_key_not_seeded_in_production(monkeypatch, tmp_path):
    """Публічний демо-ключ не має зʼявлятись у проді — навіть на свіжій БД.

    Його значення лежить у репо. Без цього гарда відновлення з бекапу, знятого до
    відкликання, тихо повертало б робочий ключ, який бачив кожен читач коду.
    """
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(b2b_service, "DB_PATH", tmp_path / "prod_like.db")

    assert verify_b2b_api_key("b2b_test_key_w3ir_2026") is None
    assert list_b2b_keys() == []

    # Партнерські ключі в проді видаються як завжди.
    key = generate_b2b_api_key("Real Partner", quota=5)
    assert verify_b2b_api_key(key)["client_name"] == "Real Partner"


def test_revoke_and_restore_key():
    """Відкликання: ключ перестає працювати, але рядок і лічильник лишаються."""
    key = generate_b2b_api_key("Leaky DAO", quota=10)
    assert record_b2b_usage(key, 3) is True

    assert b2b_service.set_b2b_key_active(key, False) is True
    assert verify_b2b_api_key(key) is None
    assert record_b2b_usage(key, 1) is False  # відкликаний не списує

    listed = {r["api_key"]: r for r in list_b2b_keys()}
    assert listed[key]["active"] is False
    assert listed[key]["used"] == 3  # історія спожитого не втрачена

    assert b2b_service.set_b2b_key_active(key, True) is True
    assert verify_b2b_api_key(key)["used"] == 3


def test_set_quota_of_existing_key():
    key = generate_b2b_api_key("Growing DAO", quota=1)
    assert record_b2b_usage(key, 1) is True
    assert verify_b2b_api_key(key) is None  # квота вичерпана

    assert b2b_service.set_b2b_key_quota(key, 10) is True
    client = verify_b2b_api_key(key)
    assert client["quota"] == 10
    assert client["used"] == 1  # підняли стелю, спожите не скинули


def test_rename_keeps_key_and_usage():
    """Перейменування — це зміна ЯРЛИКА: ключ і лічильник спожитого лишаються."""
    key = generate_b2b_api_key("Partner #1 (pilot)", quota=10)
    assert record_b2b_usage(key, 4) is True

    assert b2b_service.set_b2b_key_client_name(key, "Real Partner DAO") is True

    client = verify_b2b_api_key(key)  # той самий ключ далі валідний
    assert client["client_name"] == "Real Partner DAO"
    assert client["used"] == 4  # історію спожитого не обнулено


def test_rename_rejects_empty_and_unknown():
    key = generate_b2b_api_key("Some DAO", quota=5)
    assert b2b_service.set_b2b_key_client_name(key, "   ") is False
    assert b2b_service.set_b2b_key_client_name("nope", "X") is False
    assert verify_b2b_api_key(key)["client_name"] == "Some DAO"


def test_revoke_unknown_key():
    assert b2b_service.set_b2b_key_active("nope", False) is False
    assert b2b_service.set_b2b_key_quota("nope", 5) is False


def test_env_override_key(monkeypatch):
    monkeypatch.setenv("W3IR_B2B_KEYS", "env_partner_key")
    client = verify_b2b_api_key("env_partner_key")
    assert client is not None
    assert client["client_name"] == "Partner Client"
