"""Безпечне логування в проді — приглушення шумних клієнтів і редагування секретів у рядках."""

from __future__ import annotations

import logging
import re

# Патерни для редагування в URL/query та заголовках (Helio apiKey, Telegram bot token тощо).
_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(apiKey=)[^&\s\"']+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(apikey=)[^&\s\"']+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(Bearer\s+)\S+", re.I), r"\1[REDACTED]"),
    (re.compile(r"(token=)[^&\s\"']+", re.I), r"\1[REDACTED]"),
    (re.compile(r"/bot[^/]+/"), "/bot[REDACTED]/"),
)


def redact_secrets(text: str) -> str:
    """Прибирає секрети з рядка логу (URL, Bearer тощо)."""
    out = text
    for pattern, repl in _REDACT_PATTERNS:
        out = pattern.sub(repl, out)
    return out


class RedactSecretsFilter(logging.Filter):
    """Фільтр root-логера: редагує msg і рядкові args перед записом."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            record.args = tuple(
                redact_secrets(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def configure_production_logging() -> None:
    """Приглушує httpx/httpcore і додає фільтр секретів на root-логер."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    root = logging.getLogger()
    if not any(isinstance(f, RedactSecretsFilter) for f in root.filters):
        root.addFilter(RedactSecretsFilter())
