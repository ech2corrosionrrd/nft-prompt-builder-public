"""Тести persist рейтингів куратора (storage)."""

import storage


def test_curator_ratings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "CURATOR_RATINGS_DIR", tmp_path)
    wallet = "0xabc"
    storage.merge_curator_ratings(wallet, {"/img/a.png": 4, "/img/b.png": 5})
    loaded = storage.load_curator_ratings(wallet)
    assert loaded["/img/a.png"] == 4
    assert loaded["/img/b.png"] == 5
    storage.merge_curator_ratings(wallet, {"/img/a.png": 2, "/img/c.png": 3})
    loaded2 = storage.load_curator_ratings(wallet)
    assert loaded2["/img/a.png"] == 2
    assert loaded2["/img/c.png"] == 3
