#!/usr/bin/env python3
"""Ручне нарахування кредитів гаманцю (адмін-операція).

Додає кредити на баланс гаманця і логує транзакцію 'grant'. Працює і для EVM
(0x…), і для Solana. На відміну від звіряння Helio це навмисна разова дія, НЕ
ідемпотентна: кожен запуск додає вказану суму.

Нюанс: витратити кредити (deduct) гаманець зможе лише після першого входу
підписом на сайті (verified). Грант сам по собі verified не ставить — про це
скрипт попереджає.

Usage:
  python scripts/grant_credits.py --wallet 0x.. --amount 100
  python scripts/grant_credits.py --wallet 0x.. --amount 50 --note "компенсація"

Вихід: 0 — нараховано; 1 — помилка (невалідна адреса або недодатна сума).

Приклад з кореня проєкту (Windows):
  python scripts/grant_credits.py --wallet 0xABC.. --amount 100
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

# Консоль Windows часто cp1251 — інакше кирилиця валить вивід.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

from services import payment_service  # noqa: E402 — після load_dotenv/sys.path


def main() -> int:
    parser = argparse.ArgumentParser(description="Ручне нарахування кредитів гаманцю")
    parser.add_argument("--wallet", required=True, help="Адреса гаманця (EVM 0x… або Solana)")
    parser.add_argument("--amount", required=True, type=int, help="Скільки кредитів додати (>0)")
    parser.add_argument("--note", default="Ручний грант", help="Примітка для історії транзакцій")
    args = parser.parse_args()

    try:
        balance = payment_service.grant_credits(args.wallet, args.amount, note=args.note)
        wallet = payment_service.normalize_wallet(args.wallet)
    except ValueError as exc:
        print(f"❌ {exc}")
        return 1

    print(f"✅ +{args.amount} кредитів гаманцю {wallet}. Новий баланс: {balance}.")
    if not payment_service.is_wallet_verified(wallet):
        print("⚠️ Гаманець ще не входив підписом — витратити кредити зможе лише після "
              "першого входу на сайті (Connect Wallet).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
