"""Тести хелперів курації / pilot (ПЛАН_ЯКОСТІ.md § Q2.4)."""

from services.curation import (
    PILOT_DEFAULT,
    average_rating,
    borderline_indices,
    bulk_approve_indices,
    engine_winner,
    is_low_quality,
    pilot_count,
    pilot_subset,
)


def test_pilot_count_clamps():
    assert pilot_count(100) == PILOT_DEFAULT
    assert pilot_count(3) == 3
    assert pilot_count(0) == 0
    assert pilot_count(100, 5) == 5


def test_pilot_subset_first_n():
    prompts = [{"prompt": str(i)} for i in range(20)]
    out = pilot_subset(prompts, 5)
    assert [p["prompt"] for p in out] == ["0", "1", "2", "3", "4"]


def test_pilot_subset_fewer_than_n():
    prompts = [{"prompt": "a"}, {"prompt": "b"}]
    assert len(pilot_subset(prompts, 10)) == 2


def test_average_rating():
    assert average_rating([5, 4, 0, 3]) == 4.0  # нулі (без оцінки) ігноруються
    assert average_rating([0, 0]) is None
    assert average_rating([]) is None


def test_is_low_quality():
    assert is_low_quality(3.0)
    assert not is_low_quality(4.2)
    assert not is_low_quality(None)
    assert is_low_quality(3.4, threshold=3.5)


def test_bulk_approve_indices():
    ratings = {0: 5, 1: 3, 2: 4, 3: 0}
    assert bulk_approve_indices(ratings, 4) == [0, 2]
    assert bulk_approve_indices(ratings, 1) == [0, 1, 2]
    assert bulk_approve_indices({}, 4) == []


def test_borderline_indices():
    ratings = {0: 3, 1: 4, 2: 3, 3: 0, 4: 2}
    assert borderline_indices(ratings, 3) == [0, 2]
    assert borderline_indices(ratings, 4) == [1]


def test_engine_winner_highest_average():
    items = [("Flux", 5), ("Flux", 3), ("DALL-E", 2), ("DALL-E", 2)]
    assert engine_winner(items) == "Flux"  # avg 4 > 2


def test_engine_winner_ignores_unrated_and_none():
    assert engine_winner([("Flux", 0), ("", 5)]) is None
    assert engine_winner([]) is None


def test_engine_winner_tiebreak_by_sample_size():
    # обидва avg=4, але у Flux більше оцінених → надійніша вибірка
    items = [("Flux", 4), ("Flux", 4), ("Stability", 4)]
    assert engine_winner(items) == "Flux"
