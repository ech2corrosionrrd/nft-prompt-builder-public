"""Тести PinataService: валідація JWT, мапінг мережевих помилок, disk-деплой."""

import json

import httpx
import pytest

import ipfs
from services.ipfs_storage import (
    PinataAuthError,
    PinataError,
    PinataRateLimitError,
    PinataService,
    PinataTimeoutError,
)


def _http_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", ipfs.PINATA_PIN_URL)
    resp = httpx.Response(code, request=req, text="boom")
    return httpx.HTTPStatusError("err", request=req, response=resp)


def test_missing_jwt_raises_auth():
    with pytest.raises(PinataAuthError):
        PinataService("")
    with pytest.raises(PinataAuthError):
        PinataService("   ")


def test_pin_directory_empty_files():
    svc = PinataService("jwt")
    with pytest.raises(PinataError):
        svc.pin_directory([], "name")


def test_pin_directory_success_delegates(monkeypatch):
    captured = {}

    def fake_upload(jwt, files, name):
        captured.update(jwt=jwt, files=files, name=name)
        return "CID123"

    monkeypatch.setattr(ipfs, "upload_directory", fake_upload)
    svc = PinataService("my-jwt")
    cid = svc.pin_directory([("1.png", b"x")], "imgs")
    assert cid == "CID123"
    assert captured["jwt"] == "my-jwt" and captured["name"] == "imgs"


@pytest.mark.parametrize("code,exc", [
    (429, PinataRateLimitError),
    (401, PinataAuthError),
    (403, PinataAuthError),
    (500, PinataError),
])
def test_pin_directory_maps_http_errors(monkeypatch, code, exc):
    def boom(jwt, files, name):
        raise _http_error(code)
    monkeypatch.setattr(ipfs, "upload_directory", boom)
    with pytest.raises(exc):
        PinataService("jwt").pin_directory([("1.png", b"x")], "n")


def test_pin_directory_maps_timeout(monkeypatch):
    def boom(jwt, files, name):
        raise httpx.TimeoutException("slow")
    monkeypatch.setattr(ipfs, "upload_directory", boom)
    with pytest.raises(PinataTimeoutError):
        PinataService("jwt").pin_directory([("1.png", b"x")], "n")


def test_pin_directory_retries_429_then_succeeds(monkeypatch):
    """429 двічі → backoff-ретрай → успіх на 3-й спробі (без реального sleep)."""
    calls = {"n": 0}

    def flaky(jwt, files, name):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429)
        return "OKCID"

    monkeypatch.setattr(ipfs, "upload_directory", flaky)
    svc = PinataService("jwt", max_retries=3, backoff_base=0.01)
    slept = []
    svc._sleep = slept.append  # перехопити backoff
    assert svc.pin_directory([("1.png", b"x")], "n") == "OKCID"
    assert calls["n"] == 3 and len(slept) == 2  # 2 ретраї


def test_pin_directory_429_exhausts_retries(monkeypatch):
    def always_429(jwt, files, name):
        raise _http_error(429)
    monkeypatch.setattr(ipfs, "upload_directory", always_429)
    svc = PinataService("jwt", max_retries=2, backoff_base=0.01)
    svc._sleep = lambda _s: None
    with pytest.raises(PinataRateLimitError):
        svc.pin_directory([("1.png", b"x")], "n")


def test_publish_collection_rewrites_image_and_returns_cid(monkeypatch, tmp_path):
    images = tmp_path / "images"
    meta = tmp_path / "metadata"
    images.mkdir(); meta.mkdir()
    (images / "1.png").write_bytes(b"img1")
    (images / "2.png").write_bytes(b"img2")
    (meta / "1.json").write_text(json.dumps({"name": "#1", "image": "1.png"}), encoding="utf-8")
    (meta / "2.json").write_text(json.dumps({"name": "#2", "image": "2.png"}), encoding="utf-8")

    pinned = {}

    def fake_pin(self, files, name):
        pinned[name.split("-")[-1]] = files
        return "IMGCID" if name.endswith("-images") else "METACID"

    monkeypatch.setattr(PinataService, "pin_directory", fake_pin)

    metadata_cid = PinataService("jwt").publish_collection(images, meta, collection_name="col")
    assert metadata_cid == "METACID"  # повертає лише metadata_cid (str)

    # image-поле переписане на ipfs://IMGCID/<file>
    meta_blobs = dict(pinned["metadata"])
    assert json.loads(meta_blobs["1.json"])["image"] == "ipfs://IMGCID/1.png"
    assert json.loads(meta_blobs["2.json"])["image"] == "ipfs://IMGCID/2.png"


def test_publish_collection_no_images(tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "metadata").mkdir()
    with pytest.raises(PinataError):
        PinataService("jwt").publish_collection(
            tmp_path / "images", tmp_path / "metadata",
        )


def test_ipfs_publish_accepts_uploader(monkeypatch):
    """export_bundle.ipfs_publish маршрутизує через переданий uploader (без jwt-виклику)."""
    from services import export_bundle

    calls = []

    def uploader(files, name):
        calls.append(name)
        return "IMGCID" if name.endswith("-images") else "METACID"

    assets = [{
        "name": "#1", "description": "desc", "prompt": "a neon fox",
        "traits": {"Background": "Blue"}, "filename": "src0.png", "image_bytes": b"x",
    }]
    res = export_bundle.ipfs_publish("opensea", assets, jwt="", uploader=uploader)
    assert res["images_cid"] == "IMGCID" and res["metadata_cid"] == "METACID"
    assert len(calls) == 2
