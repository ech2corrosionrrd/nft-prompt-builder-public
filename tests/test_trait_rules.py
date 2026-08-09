"""Тести правил сумісності traits (ПЛАН_ЯКОСТІ.md § Q2.2)."""

from services.trait_rules import (
    combo_allowed,
    count_blocked,
    filter_combos,
    parse_rules,
)


def test_parse_rules_separators_and_case():
    rules = parse_rules("Golden Crown | Viking Helmet\nlaser + sword\na vs b")
    assert frozenset({"golden crown", "viking helmet"}) in rules
    assert frozenset({"laser", "sword"}) in rules
    assert frozenset({"a", "b"}) in rules


def test_parse_rules_ignores_bad_lines():
    rules = parse_rules("\n   \nno-separator-here\nsame | same\n")
    assert rules == []


def test_parse_rules_dedups():
    rules = parse_rules("a | b\nb | a\nA | B")
    assert len(rules) == 1


def test_combo_allowed_no_rules():
    assert combo_allowed({"Head": "crown"}, [])


def test_combo_allowed_blocks_when_both_present():
    rules = parse_rules("crown | helmet")
    assert not combo_allowed({"Head": "Crown", "Alt": "Helmet"}, rules)
    assert combo_allowed({"Head": "Crown", "Alt": "hat"}, rules)


def test_filter_combos_removes_incompatible():
    combos = [
        {"traits": {"Head": "crown", "Body": "armor"}},
        {"traits": {"Head": "crown", "Body": "helmet"}},
        {"traits": {"Head": "hat"}},
    ]
    rules = parse_rules("crown | helmet")
    kept = filter_combos(combos, rules)
    assert len(kept) == 2
    assert all(combo_allowed(c["traits"], rules) for c in kept)


def test_count_blocked():
    combos = [
        {"traits": {"a": "crown", "b": "helmet"}},
        {"traits": {"a": "crown"}},
    ]
    assert count_blocked(combos, parse_rules("crown | helmet")) == 1
    assert count_blocked(combos, []) == 0
