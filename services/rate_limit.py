"""In-memory rate limiter для FastAPI (один процес / --workers 1).

Для multi-worker — винести в Redis (як nonce-стор).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits[key] if now - t < window]
            if len(recent) >= limit:
                self._hits[key] = recent
                return False
            recent.append(now)
            self._hits[key] = recent
            self._sweep(now, window)
            return True

    def _sweep(self, now: float, window: float) -> None:
        """Прибирає ключі, у яких немає свіжих звернень — інакше словник росте
        безмежно (один запис на кожен IP/бакет назавжди) у довгоживучому процесі.
        Виконується під уже взятим self._lock."""
        stale = [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= window]
        for k in stale:
            del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiter = RateLimiter()


def allow_request(key: str, *, limit: int, window: float = 60.0) -> bool:
    """True — запит дозволено; False — перевищено ліміт."""
    return _limiter.allow(key, limit, window)


def reset_for_tests() -> None:
    """Скидання стану між тестами."""
    _limiter.reset()
