"""Тести services/log_safety.py — редагування секретів у логах."""

from services.log_safety import RedactSecretsFilter, configure_production_logging, redact_secrets


def test_redact_helio_api_key_in_url():
    raw = "GET https://api.hel.io/v1/export/payments?paylinkId=abc&apiKey=SECRET123"
    assert "SECRET123" not in redact_secrets(raw)
    assert "apiKey=[REDACTED]" in redact_secrets(raw)


def test_redact_bearer_token():
    assert redact_secrets("Authorization: Bearer eyJhbGciOi") == "Authorization: Bearer [REDACTED]"


def test_redact_filter_on_log_record():
    filt = RedactSecretsFilter()
    import logging

    record = logging.LogRecord("x", logging.INFO, "", 0, "apiKey=leak", (), None)
    assert filt.filter(record) is True
    assert "leak" not in record.msg


def test_redact_telegram_bot_token_in_url():
    raw = "POST https://api.telegram.org/bot123456:ABC-DEF/sendMessage"
    assert "ABC-DEF" not in redact_secrets(raw)
    assert "/bot[REDACTED]/" in redact_secrets(raw)


def test_configure_production_logging_idempotent():
    import logging

    configure_production_logging()
    configure_production_logging()
    assert logging.getLogger("httpx").level == logging.WARNING
    assert any(isinstance(f, RedactSecretsFilter) for f in logging.getLogger().filters)
