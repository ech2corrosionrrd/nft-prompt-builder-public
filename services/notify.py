"""Сповіщення в Telegram — спільне для білінгу (оплати) і вотчдога (збої).

Працює, лише якщо задано TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID; інакше тиха
відмова (повертає False). Помилки мережі проковтуються — сповіщення ніколи не
має валити основну логіку (нарахування платежу чи перевірку здоров'я).
"""

from __future__ import annotations

import logging
import os

import httpx

from services.log_safety import configure_production_logging

configure_production_logging()
logger = logging.getLogger(__name__)


def telegram_configured() -> bool:
    return bool(
        os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        and os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    )


def send_telegram(text: str) -> bool:
    """Надсилає повідомлення боту. True — надіслано; False — не налаштовано/помилка."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        return False
    try:
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10.0,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — сповіщення не має валити основну логіку
        logger.warning("Telegram-сповіщення не надіслано: %s", exc)
        return False
