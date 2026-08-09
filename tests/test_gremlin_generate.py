"""Тести /gremlin/generate і чистої логіки трейтів (контракт Gremlin Passport ↔ W3IR).

Живий Flux/Replicate НЕ викликається — `_gremlin_generate_png` мокається (генерація
платна). Перевіряємо валідацію, побудову промпту й гейт доступу ендпоінта.
"""
import pytest
from fastapi.testclient import TestClient

import api_server
from api_server import app
from services import gremlin_generate as gg

VALID_TRAITS = {"body": "void", "eyes": "glow", "accessory": "none", "backdrop": "nebula"}
KEY = "test-shared-secret"


# ── чисті функції ────────────────────────────────────────────────────────────
def test_validate_traits_ok():
    assert gg.validate_traits(dict(VALID_TRAITS)) == VALID_TRAITS


def test_validate_traits_unknown_value():
    with pytest.raises(gg.TraitError):
        gg.validate_traits({**VALID_TRAITS, "body": "gold"})


def test_validate_traits_missing_key():
    with pytest.raises(gg.TraitError):
        gg.validate_traits({"body": "void", "eyes": "glow", "accessory": "none"})


def test_validate_traits_ignores_extra_keys():
    out = gg.validate_traits({**VALID_TRAITS, "evil": "'; drop table"})
    assert out == VALID_TRAITS
    assert "evil" not in out


def test_validate_traits_non_dict():
    with pytest.raises(gg.TraitError):
        gg.validate_traits("nope")


@pytest.mark.parametrize("bad", [-1, gg.MAX_SEED + 1, 1.5, "3", None, True])
def test_validate_seed_rejects(bad):
    with pytest.raises(gg.TraitError):
        gg.validate_seed(bad)


@pytest.mark.parametrize("good", [0, 42, gg.MAX_SEED])
def test_validate_seed_ok(good):
    assert gg.validate_seed(good) == good


def test_build_prompt_includes_traits_and_omits_none_accessory():
    prompt = gg.build_prompt(VALID_TRAITS)
    assert "gremlin" in prompt.lower()
    assert "void-black" in prompt
    assert "luminous eyes" in prompt
    assert "nebula" in prompt
    # accessory 'none' не додає порожнього сегмента
    assert ", ," not in prompt


def test_build_prompt_includes_accessory_when_set():
    prompt = gg.build_prompt({**VALID_TRAITS, "accessory": "crown"})
    assert "crown" in prompt


# ── ендпоінт: гейт доступу ───────────────────────────────────────────────────
@pytest.fixture
def no_rate_limit(monkeypatch):
    # Ліміт не має заважати самим гейт-перевіркам.
    monkeypatch.setattr(api_server, "allow_request", lambda *a, **k: True)


def test_generate_503_when_key_not_configured(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", "")
    r = TestClient(app).post("/gremlin/generate", json={"traits": VALID_TRAITS, "seed": 1})
    assert r.status_code == 503


def test_generate_401_without_header(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", KEY)
    r = TestClient(app).post("/gremlin/generate", json={"traits": VALID_TRAITS, "seed": 1})
    assert r.status_code == 401


def test_generate_401_with_wrong_key(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", KEY)
    r = TestClient(app).post(
        "/gremlin/generate",
        json={"traits": VALID_TRAITS, "seed": 1},
        headers={"X-Gremlin-Key": "wrong"},
    )
    assert r.status_code == 401


def test_generate_400_on_bad_traits(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", KEY)
    r = TestClient(app).post(
        "/gremlin/generate",
        json={"traits": {**VALID_TRAITS, "body": "gold"}, "seed": 1},
        headers={"X-Gremlin-Key": KEY},
    )
    assert r.status_code == 400


def test_generate_200_returns_png(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", KEY)
    png = b"\x89PNG\r\n\x1a\n fake"
    captured = {}

    def _fake(prompt, seed):
        captured["prompt"] = prompt
        captured["seed"] = seed
        return png

    monkeypatch.setattr(api_server, "_gremlin_generate_png", _fake)
    r = TestClient(app).post(
        "/gremlin/generate",
        json={"traits": VALID_TRAITS, "seed": 7},
        headers={"X-Gremlin-Key": KEY},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == png
    assert captured["seed"] == 7
    assert "gremlin" in captured["prompt"].lower()


def test_generate_503_when_flux_fails(monkeypatch, no_rate_limit):
    monkeypatch.setattr(api_server, "_GREMLIN_API_KEY", KEY)

    def _boom(prompt, seed):
        raise RuntimeError("Flux.1: API-токен не знайдено")

    monkeypatch.setattr(api_server, "_gremlin_generate_png", _boom)
    r = TestClient(app).post(
        "/gremlin/generate",
        json={"traits": VALID_TRAITS, "seed": 1},
        headers={"X-Gremlin-Key": KEY},
    )
    assert r.status_code == 503
