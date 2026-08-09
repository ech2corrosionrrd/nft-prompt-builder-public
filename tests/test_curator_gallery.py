"""Тести фільтра куратора: свіжі (неоцінені) зображення мають бути видимі."""

import streamlit as st

from services import image_qa
from ui import curator_gallery


def _img(path, **kw):
    d = {"path": str(path), "prompt": "cyber fox", "traits": {}}
    d.update(kw)
    return d


def test_unrated_image_visible_with_default_filter(monkeypatch, tmp_path):
    """Регресія: після генерації рейтинг=0; дефолтний фільтр (0) має показувати."""
    monkeypatch.setattr(st, "session_state", {})
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG fake")
    images = [_img(p)]
    # min_rating=0 (новий дефолт) → неоцінене зображення видиме
    assert curator_gallery.filter_images(images, 0, 0.0, "", curator_gallery.TIER_ALL) == [0]
    # min_rating=3 → ховається, поки користувач не оцінить
    assert curator_gallery.filter_images(images, 3, 0.0, "", curator_gallery.TIER_ALL) == []


def test_rated_image_passes_higher_filter(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "session_state", {"pl2_rating_0": 4})
    p = tmp_path / "b.png"
    p.write_bytes(b"\x89PNG fake")
    images = [_img(p)]
    assert curator_gallery.filter_images(images, 3, 0.0, "", curator_gallery.TIER_ALL) == [0]


def test_missing_file_excluded(monkeypatch, tmp_path):
    """Файл не на диску → не показуємо (st.image впав би)."""
    monkeypatch.setattr(st, "session_state", {})
    images = [_img(tmp_path / "nope.png")]
    assert curator_gallery.filter_images(images, 0, 0.0, "", curator_gallery.TIER_ALL) == []


def test_qa_filter_excludes_low_score(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "session_state", {})
    p = tmp_path / "a.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 80)
    images = [_img(p)]
    qa = {str(p): image_qa.QAResult(score=30, issues=["blur"])}
    assert curator_gallery.filter_images(
        images, 0, 0.0, "", curator_gallery.TIER_ALL, min_qa_score=50, qa_by_path=qa,
    ) == []
    assert curator_gallery.filter_images(
        images, 0, 0.0, "", curator_gallery.TIER_ALL, min_qa_score=0, qa_by_path=qa,
    ) == [0]


def test_qa_card_caption_ok():
    cap = curator_gallery.qa_card_caption(image_qa.QAResult(score=100, issues=[]))
    assert "100" in cap
    assert "5" in cap


def test_qa_card_caption_warn_lists_issues():
    cap = curator_gallery.qa_card_caption(
        image_qa.QAResult(score=65, issues=[image_qa.ISSUE_BLURRY]),
    )
    assert "65" in cap
    assert "4" in cap
