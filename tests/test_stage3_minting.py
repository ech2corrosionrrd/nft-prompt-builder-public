"""Тести допоміжних функцій Етапу 3 (експорт)."""

from ui.stage3_minting import collection_name_warnings


def test_collection_name_warnings_empty():
    assert collection_name_warnings("") == []
    assert collection_name_warnings("   ") == []


def test_collection_name_warnings_ascii_ok():
    assert collection_name_warnings("Cosmic Oracles") == []


def test_collection_name_warnings_non_ascii():
    assert collection_name_warnings("Неон Океан") == ["non_ascii"]


def test_collection_name_warnings_spaces():
    assert collection_name_warnings(" Cosmic") == ["spaces"]
    assert collection_name_warnings("Cosmic  Oracles") == ["spaces"]
