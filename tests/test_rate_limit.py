import time

from services.rate_limit import RateLimiter, allow_request, reset_for_tests


def setup_function():
    reset_for_tests()


def test_rate_limit_blocks_after_limit():
    for _ in range(5):
        assert allow_request("test:ip", limit=5, window=60.0)
    assert not allow_request("test:ip", limit=5, window=60.0)


def test_rate_limit_separate_keys():
    assert allow_request("a", limit=1, window=60.0)
    assert not allow_request("a", limit=1, window=60.0)
    assert allow_request("b", limit=1, window=60.0)


def test_stale_keys_are_swept():
    """Ключі без свіжих звернень не накопичуються (захист від витоку памʼяті):
    після проходу вікна старий бакет зникає, щойно надходить новий запит."""
    limiter = RateLimiter()
    limiter.allow("old:ip", limit=10, window=0.05)
    assert "old:ip" in limiter._hits
    time.sleep(0.06)  # «old:ip» виходить за вікно
    limiter.allow("new:ip", limit=10, window=0.05)
    assert "old:ip" not in limiter._hits  # підмели застарілий
    assert "new:ip" in limiter._hits


def test_active_keys_survive_sweep():
    """Свіжі бакети у межах вікна sweep НЕ чіпає (ліміт лишається дієвим)."""
    limiter = RateLimiter()
    limiter.allow("a", limit=10, window=60.0)
    limiter.allow("b", limit=10, window=60.0)
    assert set(limiter._hits) == {"a", "b"}
