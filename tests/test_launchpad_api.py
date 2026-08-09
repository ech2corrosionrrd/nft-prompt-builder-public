"""Тести інспекції бандла: чиста функція + партнерський гейт роуту.

Роут `/api/v1/launchpad/inspect-bundle` до 2026-08-07 був відкритий і без стелі
розміру — будь-хто міг вантажити довільні архіви на серверний розбір. Тепер це
партнерський ендпоінт: B2B-ключ + списання квоти + ліміт розміру.
"""
import io
import json
import zipfile

from fastapi.testclient import TestClient

from api_server import app
from services import b2b_service
from services.launchpad_service import MAX_JSON_MEMBER_BYTES, inspect_bundle_zip

STAGING_KEY = "b2b_test_key_w3ir_2026"


def make_test_zip(manifest=None, config=None, assets_count=2):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        if manifest:
            zf.writestr("manifest.json", json.dumps(manifest))
        if config:
            zf.writestr("config.json", json.dumps(config))
        for i in range(assets_count):
            zf.writestr(f"assets/{i}.png", b"fake_png_data")
    return buf.getvalue()


def _valid_zip() -> bytes:
    return make_test_zip(
        manifest={"name": "Test Collection", "symbol": "TEST"},
        config={"number": 10, "symbol": "TEST"},
        assets_count=10,
    )


def _upload(client: TestClient, data: bytes, key: str | None = STAGING_KEY):
    headers = {"X-W3IR-B2B-Key": key} if key else {}
    return client.post(
        "/api/v1/launchpad/inspect-bundle",
        files={"file": ("bundle.zip", data, "application/zip")},
        headers=headers,
    )


def test_inspect_bundle_valid():
    manifest = {"name": "Test Collection", "symbol": "TEST"}
    config = {"number": 10, "symbol": "TEST"}
    zip_bytes = make_test_zip(manifest=manifest, config=config, assets_count=10)

    res = inspect_bundle_zip(zip_bytes)
    assert res["valid"] is True
    assert res["collection_name"] == "Test Collection"
    assert res["symbol"] == "TEST"
    assert res["items_count"] == 10
    assert res["sugar_ready"] is True
    assert res["has_manifest"] is True
    assert res["has_config"] is True


def test_inspect_bundle_invalid():
    res = inspect_bundle_zip(b"not a zip file")
    assert res["valid"] is False
    assert "Invalid ZIP file format" in res["error"]


def test_inspect_bundle_ignores_oversized_json_member():
    """Decompression bomb: стеля на архів не рятує, бо zip розтискається в рази.

    Роздутий manifest.json ігнорується (назва колекції лишається дефолтною), а не
    читається цілком у памʼять.
    """
    huge = {"name": "Bomb", "pad": "A" * (MAX_JSON_MEMBER_BYTES + 1024)}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(huge))
        zf.writestr("config.json", json.dumps({"number": 3}))
        zf.writestr("assets/0.png", b"fake_png_data")
    zip_bytes = buf.getvalue()
    # Суть бомби: архів на кілька КБ розтискається в мегабайти.
    assert len(zip_bytes) < 100 * 1024

    res = inspect_bundle_zip(zip_bytes)
    assert res["valid"] is True
    assert res["collection_name"] == "Custom Collection"


def test_route_requires_b2b_key():
    with TestClient(app) as client:
        assert _upload(client, _valid_zip(), key=None).status_code == 401
        assert _upload(client, _valid_zip(), key="not_a_real_key").status_code == 401


def test_route_meters_quota_on_success():
    """Успішна інспекція списує рівно одиницю квоти партнера."""
    key = b2b_service.generate_b2b_api_key("Launchpad Partner", quota=5)
    with TestClient(app) as client:
        res = _upload(client, _valid_zip(), key=key)
        assert res.status_code == 200
        assert res.json()["collection_name"] == "Test Collection"
    assert b2b_service.verify_b2b_api_key(key)["used"] == 1


def test_route_does_not_charge_for_invalid_bundle():
    """Невдала інспекція не палить квоту (дзеркалить freemium-облік)."""
    key = b2b_service.generate_b2b_api_key("Launchpad Partner", quota=5)
    with TestClient(app) as client:
        assert _upload(client, b"not a zip file", key=key).status_code == 400
    assert b2b_service.verify_b2b_api_key(key)["used"] == 0


def test_route_rejects_when_quota_exhausted():
    key = b2b_service.generate_b2b_api_key("Tiny Partner", quota=1)
    with TestClient(app) as client:
        assert _upload(client, _valid_zip(), key=key).status_code == 200
        # Квота вичерпана → 401 ще до розбору архіву.
        assert _upload(client, _valid_zip(), key=key).status_code == 401


def test_route_rejects_oversized_upload(monkeypatch):
    import api_server

    monkeypatch.setattr(api_server, "_LAUNCHPAD_MAX_UPLOAD_MB", 1)
    key = b2b_service.generate_b2b_api_key("Big Upload Partner", quota=5)
    oversized = b"PK\x03\x04" + b"\x00" * (2 * 1024 * 1024)
    with TestClient(app) as client:
        assert _upload(client, oversized, key=key).status_code == 413
    # Відмова за розміром теж не списує квоту.
    assert b2b_service.verify_b2b_api_key(key)["used"] == 0
