"""Тести RedisNonceStore і фабрики create_nonce_store (через fakeredis)."""

import json

import pytest

from services import auth_gateway as ag

fakeredis = pytest.importorskip("fakeredis")

ADDR = "0xAbC0000000000000000000000000000000000001"


@pytest.fixture
def store():
    return ag.RedisNonceStore(fakeredis.FakeStrictRedis(), ttl=300)


def test_issue_consume_roundtrip(store):
    store.issue("n1", ADDR, "msg-body")
    assert store.consume("n1") == (ADDR.lower(), "msg-body")


def test_single_use(store):
    store.issue("n2", ADDR, "m")
    assert store.consume("n2") == (ADDR.lower(), "m")
    assert store.consume("n2") is None  # GETDEL — другий раз порожньо


def test_unknown_nonce(store):
    assert store.consume("nope") is None


def test_address_lowercased(store):
    store.issue("n3", "0xDEADBEEF00000000000000000000000000000001", "m")
    addr, _ = store.consume("n3")
    assert addr == "0xdeadbeef00000000000000000000000000000001"


def test_redis_key_format_and_ttl():
    client = fakeredis.FakeStrictRedis()
    store = ag.RedisNonceStore(client, ttl=300)
    store.issue("n4", ADDR, "m")
    key = ag._REDIS_PREFIX + "n4"
    assert client.exists(key) == 1
    assert 0 < client.ttl(key) <= 300  # SET ex=ttl застосовано
    obj = json.loads(client.get(key))
    assert obj == {"address": ADDR.lower(), "message": "m"}


def test_expired_nonce_gone(store):
    """Після ручного видалення (емуляція TTL-протермінування) — None."""
    store.issue("n5", ADDR, "m")
    store._r.delete(ag._REDIS_PREFIX + "n5")
    assert store.consume("n5") is None


def test_corrupted_payload_returns_none():
    client = fakeredis.FakeStrictRedis()
    store = ag.RedisNonceStore(client, ttl=300)
    client.set(ag._REDIS_PREFIX + "n6", "not-json")
    assert store.consume("n6") is None


def test_factory_default_is_memory(monkeypatch):
    monkeypatch.delenv("AUTH_NONCE_BACKEND", raising=False)
    assert isinstance(ag.create_nonce_store(), ag.NonceStore)


def test_factory_memory_explicit(monkeypatch):
    monkeypatch.setenv("AUTH_NONCE_BACKEND", "memory")
    assert isinstance(ag.create_nonce_store(), ag.NonceStore)


def test_factory_redis(monkeypatch):
    """AUTH_NONCE_BACKEND=redis → RedisNonceStore (redis.from_url замокано)."""
    monkeypatch.setenv("AUTH_NONCE_BACKEND", "redis")
    fake_client = fakeredis.FakeStrictRedis()

    import redis
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, url, **kw: fake_client))
    store = ag.create_nonce_store()
    assert isinstance(store, ag.RedisNonceStore)
    # контракт працює через фабрику
    store.issue("nf", ADDR, "m")
    assert store.consume("nf") == (ADDR.lower(), "m")
