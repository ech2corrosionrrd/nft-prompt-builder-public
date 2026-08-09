"""Тести логіки rarity-слайдерів (без Streamlit-рантайму)."""

from ui.rarity_sliders import tier, _balance_to_100, COMMON_MIN, RARE_MIN


def test_tier_thresholds():
    assert tier(100) == "common"
    assert tier(COMMON_MIN) == "common"
    assert tier(COMMON_MIN - 1) == "rare"
    assert tier(RARE_MIN) == "rare"
    assert tier(RARE_MIN - 1) == "legend"
    assert tier(0) == "legend"


def test_balance_sums_to_exactly_100():
    for case in ([50, 30, 15], [10, 10, 10], [1], [3, 3, 3, 3, 3, 3, 3]):
        out = _balance_to_100(case)
        assert sum(out) == 100
        assert all(x >= 0 for x in out)


def test_balance_zero_input_splits_evenly():
    assert _balance_to_100([0, 0, 0, 0]) == [25, 25, 25, 25]
    # 3 елементи: залишок 1 дістається першому
    assert _balance_to_100([0, 0, 0]) == [34, 33, 33]


def test_balance_empty_is_empty():
    assert _balance_to_100([]) == []


def test_balance_preserves_proportions():
    # 2:1 пропорція зберігається після нормалізації
    out = _balance_to_100([60, 30])
    assert sum(out) == 100
    assert out[0] > out[1]
