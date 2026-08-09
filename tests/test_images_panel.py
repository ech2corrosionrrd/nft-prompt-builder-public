"""Тести images-вкладки (ui/images_panel.py), винесеної з app.py.

Покриваємо чисту `extract_fenced_prompt` — витяг промпта з код-блоку, плюс
B1-гейт content-safety на класичному шляху генерації (AppTest).
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from ui import images_panel

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_extract_fenced_prompt_basic():
    content = "Ось ваш промпт:\n```\na cyber cat, neon\n```\nдякую"
    assert images_panel.extract_fenced_prompt(content) == "a cyber cat, neon"


def test_extract_fenced_prompt_with_language_tag():
    content = "```text\nprompt body here\n```"
    assert images_panel.extract_fenced_prompt(content) == "prompt body here"


def test_extract_fenced_prompt_no_fence():
    assert images_panel.extract_fenced_prompt("no code block at all") == ""


def test_extract_fenced_prompt_empty():
    assert images_panel.extract_fenced_prompt("") == ""


def test_extract_fenced_prompt_strips_platform_flags():
    # strip_platform_flags має прибрати --ar/--v тощо з тіла блоку
    content = "```\na majestic wolf --ar 1:1 --v 6\n```"
    out = images_panel.extract_fenced_prompt(content)
    assert "majestic wolf" in out
    assert "--ar" not in out


def test_extract_fenced_prompt_first_block_only():
    content = "```\nfirst\n```\nmid\n```\nsecond\n```"
    assert images_panel.extract_fenced_prompt(content) == "first"


def _blocked(at) -> bool:
    """Чи показано помилку модерації контенту (двомовно: moderation / модерац)."""
    return any(
        "moderation" in e.value.lower() or "модерац" in e.value.lower()
        for e in at.error
    )


def test_classic_images_blocks_unsafe_prompt(monkeypatch):
    """Класична вкладка Images відхиляє небезпечний промпт ДО білінгу/OpenAI (B1).

    Регресія security #1: ця вкладка кликала images.generate напряму й оминала
    content-safety (на відміну від pipeline_batch._generate_one).
    """
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")
    monkeypatch.setenv("CONTENT_SAFETY_ENABLED", "1")
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["welcome_seen"] = True
    at.session_state["wallet_address"] = "0x" + "ab" * 20
    at.session_state["api_key_input"] = "sk-not-used"  # safety блокує до виклику
    at.run()
    assert not at.exception, at.exception
    # Значення задаємо ВІДЖЕТОМ після першого run (інакше prompt_options перезапише
    # image_prompt_edit з активного шаблону до інстанціювання text_area).
    at.text_area(key="image_prompt_edit").set_value("child nude, explicit").run()
    at.button(key="img_tab_gen_btn").click().run()
    assert not at.exception, at.exception
    assert _blocked(at), "небезпечний промпт класичної вкладки не заблоковано (B1 bypass)"


def test_classic_images_safe_prompt_not_blocked(monkeypatch):
    """Звичайний промпт НЕ ловить хибне спрацювання safety (проходить далі до білінгу)."""
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")
    monkeypatch.setenv("CONTENT_SAFETY_ENABLED", "1")
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["welcome_seen"] = True
    at.session_state["wallet_address"] = "0x" + "ab" * 20
    at.session_state["api_key_input"] = "sk-not-used"
    at.run()
    at.text_area(key="image_prompt_edit").set_value("a cyber owl, neon city").run()
    at.button(key="img_tab_gen_btn").click().run()
    assert not at.exception, at.exception
    assert not _blocked(at), "безпечний промпт хибно заблоковано safety-фільтром"
