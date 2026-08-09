"""Тести builder.py — i18n системного промпту (BUG-012)."""

from builder import build_system_instruction, build_user_data


def test_build_system_instruction_english():
    msg = build_system_instruction("OpenAI Images", True, True, lang="en")
    assert "Concept name" in msg
    assert "Назва концепту" not in msg
    assert "Write analysis and section headings in English" in msg


def test_build_system_instruction_ukrainian():
    msg = build_system_instruction("OpenAI Images", True, True, lang="uk")
    assert "Назва концепту" in msg
    assert "Concept name" not in msg


def test_build_user_data_english():
    data = build_user_data(
        idea="fox",
        style="Pixel Art",
        camera="Close-up",
        lighting="Neon",
        background="City",
        quality="High",
        mood="Dark",
        platform="OpenAI Images",
        tech="1:1",
        collection_size=100,
        extra_notes="",
        lang="en",
    )
    assert "Subject: fox" in data
    assert "Об'єкт" not in data
