import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import secrets_env
from services import b2b_service, payment_service


@pytest.fixture(autouse=True)
def _isolate_secrets(monkeypatch, tmp_path):
    """Жоден тест не бачить живих ключів: ані .env, ані secrets.toml, ані середовища."""
    monkeypatch.setattr(secrets_env, "ROOT", tmp_path / "no-env-here")
    monkeypatch.setattr(secrets_env, "_loaded", False)
    monkeypatch.setattr(secrets_env, "_st_secret", lambda name: None)
    # DB-бекенд: тести завжди на SQLite; живий .env з DATABASE_URL не має гнати
    # їх у реальний Postgres. Postgres-діалект тестується точково (test_db.py).
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Sybil-перевірка вітальних кредитів робить on-chain виклик до Base RPC —
    # вимикаємо, щоб тести не ходили в мережу і були детермінованими.
    monkeypatch.setenv("WELCOME_REQUIRE_BALANCE", "0")
    # SUGAR_PROJECT_PATH веде в сусідній репо (фолбек — C:\Sugar): звідти
    # api_server запускає transfer-nft.mjs. Тримаємо його в tmp, щоб жоден тест
    # не дотягнувся до бойової теки. Історія: коли holder_rewards ще дзеркалив
    # genesis_mints.json, test_holder_sync через цей env залив ФЕЙКОВІ мінти в
    # бойовий C:\Sugar\data (фікс 340ef27); дзеркало знято 03.08.2026, гард —
    # test_sync_does_not_write_into_sugar_data.
    monkeypatch.setenv("SUGAR_PROJECT_PATH", str(tmp_path / "no_sugar_mirror"))
    # B2B-ключі лежать у users.db: без ізоляції `generate_b2b_api_key` у тестах
    # створював би РЕАЛЬНІ робочі партнерські ключі в бойовій БД (попередній
    # файловий стор так і накопичив 11 сміттєвих ключів, кожен з яких проходив
    # автентифікацію на живому API). Гард — test_b2b_service.py.
    monkeypatch.setattr(b2b_service, "DB_PATH", tmp_path / "b2b_users.db")
    # Основна БД (кредити, транзакції, платежі, воронка). Без ізоляції кожен прогін
    # pytest дописував РЕАЛЬНІ рядки в data/users.db: один `pytest -q` = ~36 записів.
    # Синтетичні гаманці з test_billing_guard (0xabcdefab…, 0x12345678…) так доїхали
    # в БД проду з копією при міграції хостингу 26.07 і зіпсували метрики —
    # refund rate виглядав 37.8% замість реальних 7.8%, у payments висів фейковий
    # платіж $4.99. На цих даних приймався go/no-go E6/E7. Шість тест-файлів
    # ізолювали DB_PATH самотужки; тепер це дефолт для всіх, а їхні власні фікстури
    # лишаються сумісними (той самий tmp_path). Гард — test_conftest_isolation.py.
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    # Перевірка свіжості бекапів інакше читає РЕАЛЬНУ теку backups/hourly розробника
    # (на ПК вона протухла на сотні годин) — тест ставав би залежним від машини.
    # Тут саме setenv, а не delenv: видалення змінної повертає дефолт, який і веде
    # в бойову теку. Тести, яким потрібен «живий» бекап, ставлять свою теку самі.
    monkeypatch.setenv("BACKUP_CHECK_DIR", str(tmp_path / "no_backups_here"))
    for var in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "STABILITY_API_KEY",
        "REPLICATE_API_TOKEN",
        "PINATA_JWT",
        "HELIO_API_KEY",
        "HELIO_API_SECRET",
        "HELIO_WEBHOOK_SECRET",
        # Сповіщення: інакше record_payment у тестах шле РЕАЛЬНІ Telegram-повідомлення
        # (import api_server тягне load_dotenv → живі ключі осідають у os.environ).
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "HEALTH_ALERT_WEBHOOK",
        # B3 freemium: інакше живий .env-ліміт зробив би тести недетермінованими.
        "FREEMIUM_DAILY_LIMIT",
        "WORKSPACE_MAX_PROJECTS_PER_WALLET",
        "WORKSPACE_MAX_MB_PER_WALLET",
        "WORKSPACE_PROJECT_WARN_COUNT",
        # B2 каскад: за замовчуванням вимкнено — тести вмикають його точково.
        "IMAGE_CASCADE_ENABLED",
        # Content-safety другий ешелон (Moderation API) — opt-in; ізолюємо, щоб
        # живий .env не робив мережевих викликів у тестах content_safety.
        "MODERATION_API_ENABLED",
        # RPC-каскад холдер-бонусу: живий .env-фолбек не має додавати реальні
        # ендпоінти в детерміновані тести _solana_rpc_urls / wallet_genesis_count.
        "SOLANA_RPC_FALLBACKS",
        # gpt-image throttle: живий .env-ліміт зробив би timing-тести недетермінованими.
        "GPT_IMAGE_MAX_PER_MIN",
        # E3 upscale: ізолюємо від живого .env (оператор вмикає на проді свідомо).
        "EXPORT_UPSCALE_ENABLED",
        "QUALITY_ALERT_MIN_RATING",
        "QUALITY_ALERT_MIN_SAVE_EXPORT_PCT",
        # i18n: дефолт UI — EN; ізолюємо від живого .env (оператор може мати uk).
        "UI_DEFAULT_LANG",
        # Off-site бекап: успіх сповіщається за замовчуванням; ізолюємо від .env,
        # щоб тести були детермінованими (вимикач OFFSITE_NOTIFY_SUCCESS=0).
        "OFFSITE_NOTIFY_SUCCESS",
        # Storage-GC: реальне видалення/пороги диска — env-керовані; ізолюємо,
        # щоб живий .env не впливав на детермінізм тестів storage_gc.
        "STORAGE_GC_ENABLED",
        "STORAGE_GC_TTL_DAYS",
        "STORAGE_DISK_WARN_PCT",
        # Metadata-бекап у GitHub: реальний push — env-керований; ізолюємо.
        "METADATA_BACKUP_ENABLED",
        # Legal base: футер бере базу /legal звідси (дефолт w3ir.io); ізолюємо
        # від живого .env, щоб test_footer був детермінованим.
        "LEGAL_BASE_URL",
        # Пороги «пульсу» бекапів і ліміти партнерських роутів — env-керовані;
        # живий .env зробив би тести недетермінованими.
        "BACKUP_MAX_AGE_HOURS",
        # Пороги алерту про двигун, що масово падає (services/provider_health).
        "PROVIDER_FAILURE_THRESHOLD_PCT",
        "PROVIDER_MIN_ATTEMPTS",
        # Активна проба двигунів (services/provider_probe): ходить у мережу й
        # читає моделі з env — живий .env зробив би тести недетермінованими,
        # а PROVIDER_PROBE_GENERATE=1 ще й ПЛАТНИМИ (реальні генерації).
        "PROVIDER_PROBE_ENABLED",
        "PROVIDER_PROBE_GENERATE",
        "PROVIDER_PROBE_MIN_CREDITS",
        "OPENAI_IMAGE_MODEL",
        "FLUX_MODEL",
        "LAUNCHPAD_MAX_UPLOAD_MB",
        "LAUNCHPAD_RATE_LIMIT",
        "VAULT_STATUS_RATE_LIMIT",
        "W3IR_B2B_KEYS",
        # Pull-бекап із проду: хост/тека/ротація — env-керовані.
        "PROD_BACKUP_HOST",
        "PROD_BACKUP_DIR",
        "PROD_BACKUP_DEST",
        "PROD_BACKUP_KEEP",
        # APP_ENV/ENVIRONMENT: `import api_server` тягне load_dotenv, і бойовий
        # APP_ENV=production осідав у os.environ — тести ставали залежними від
        # .env розробника (напр. демо-ключ B2B не сідиться в проді). Тести, яким
        # потрібен production-режим, вмикають його самі через monkeypatch.
        "APP_ENV",
        "ENVIRONMENT",
        # Класифікація гаманців (services/wallet_class): від цих трьох залежить,
        # що метрики вважають зовнішнім попитом. Живий .env розробника має власні
        # адреси — без ізоляції тести scope-фільтрів залежали б від машини.
        "ADMIN_WALLETS",
        "OPERATOR_WALLET",
        "DOGFOOD_WALLETS",
    ):
        monkeypatch.delenv(var, raising=False)
    # B1 content-safety увімкнено за замовчуванням (вимикається лише "0"). У тестах
    # лишаємо дефолт-on, щоб safety-інтеграція покривалась; вимкнення — точково.
    monkeypatch.delenv("CONTENT_SAFETY_ENABLED", raising=False)
