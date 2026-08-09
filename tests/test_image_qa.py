"""Тести Auto-QA Lite (services/image_qa.py)."""

from __future__ import annotations

import pytest

from services import image_qa


def test_corrupt_too_small():
    r = image_qa.analyze_image_bytes(b"x")
    assert r.score == 0
    assert image_qa.ISSUE_CORRUPT in r.issues


def test_corrupt_bad_magic():
    r = image_qa.analyze_image_bytes(b"\x00" * 128)
    assert image_qa.ISSUE_CORRUPT in r.issues


def test_missing_path_corrupt():
    r = image_qa.analyze_image_path("/nonexistent/path/image.png")
    assert image_qa.ISSUE_CORRUPT in r.issues


def test_png_bytes_heuristic(monkeypatch, tmp_path):
    """Без візуального аналізу — лише магія PNG + розміри IHDR."""
    import struct

    monkeypatch.setattr(image_qa, "_visual_issues", lambda data: [])
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    body = sig + ihdr + b"\x00" * 40
    p = tmp_path / "ok.png"
    p.write_bytes(body)
    r = image_qa.analyze_image_path(str(p))
    assert r.issues == []
    assert r.score == 100


def test_blank_detected_with_pil(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    p = tmp_path / "flat.png"
    Image.new("RGB", (128, 128), (12, 12, 12)).save(p)
    r = image_qa.analyze_image_path(str(p))
    assert image_qa.ISSUE_BLANK in r.issues


def test_noisy_image_ok_with_pil(tmp_path):
    pytest.importorskip("PIL")
    import random

    from PIL import Image

    p = tmp_path / "noise.png"
    img = Image.new("RGB", (128, 128))
    data = [(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)) for _ in range(128 * 128)]
    img.putdata(data)
    img.save(p)
    r = image_qa.analyze_image_path(str(p))
    assert image_qa.ISSUE_BLANK not in r.issues
    assert image_qa.ISSUE_BLURRY not in r.issues


@pytest.mark.parametrize("score, stars", [
    (100, 5), (90, 5), (65, 4), (30, 3), (1, 2), (0, 1),
])
def test_star_rating_from_qa(score, stars):
    assert image_qa.star_rating_from_qa(score) == stars
