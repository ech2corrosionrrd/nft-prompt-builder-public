"""Тести C4-lite upscale (services/image_upscale.py)."""

from __future__ import annotations

import io

import pytest

from services import image_upscale


def test_disabled_returns_original():
    data = b"\x89PNG\x00"
    assert image_upscale.maybe_upscale_bytes(data, enabled=False) == data


def test_unavailable_env_default():
    assert image_upscale.upscale_available() is False


def test_available_when_env_set(monkeypatch):
    monkeypatch.setenv("EXPORT_UPSCALE_ENABLED", "1")
    assert image_upscale.upscale_available() is True


def test_upscale_small_png():
    pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGB", (512, 768), (40, 80, 120))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out = image_upscale.maybe_upscale_bytes(buf.getvalue(), enabled=True, target_max=2048)
    result = Image.open(io.BytesIO(out))
    assert max(result.size) == 2048


def test_skips_when_already_large():
    pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGB", (2048, 1024), (10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    original = buf.getvalue()
    assert image_upscale.maybe_upscale_bytes(original, enabled=True) == original


def test_apply_to_assets():
    pytest.importorskip("PIL")
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (1, 2, 3)).save(buf, format="PNG")
    assets = [{"image_bytes": buf.getvalue(), "name": "T1"}]
    out = image_upscale.apply_to_assets(assets, upscale=True)
    assert out[0]["image_bytes"] != assets[0]["image_bytes"]
    assert image_upscale.apply_to_assets(assets, upscale=False) == assets
