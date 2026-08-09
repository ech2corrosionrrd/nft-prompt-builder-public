"""Тести лінту промптів (ПЛАН_ЯКОСТІ.md § Q2.5)."""

from services.prompt_lint import (
    LINT_DUPLICATE,
    LINT_EMPTY,
    LINT_TOO_LONG,
    LINT_TOO_SHORT,
    MAX_PROMPT_CHARS,
    lint_prompt,
    lint_prompts,
    summary,
)


def test_lint_prompt_empty():
    assert lint_prompt("") == [LINT_EMPTY]
    assert lint_prompt("   ") == [LINT_EMPTY]


def test_lint_prompt_too_short():
    assert LINT_TOO_SHORT in lint_prompt("fox")


def test_lint_prompt_too_long():
    assert LINT_TOO_LONG in lint_prompt("x" * (MAX_PROMPT_CHARS + 1))


def test_lint_prompt_ok():
    assert lint_prompt("a regal cyber fox with neon armor") == []


def test_lint_prompts_flags_duplicates():
    prompts = [
        {"prompt": "cyber fox neon armor"},
        {"prompt": "Cyber   Fox  Neon Armor"},  # той самий після нормалізації
        {"prompt": "owl in the forest at night"},
    ]
    out = lint_prompts(prompts)
    assert out.get(1) == [LINT_DUPLICATE]
    assert 0 not in out  # перший екземпляр — не дубль
    assert 2 not in out


def test_lint_prompts_only_returns_problem_indices():
    prompts = [{"prompt": "a perfectly fine prompt here"}, {"prompt": ""}]
    out = lint_prompts(prompts)
    assert 0 not in out
    assert out[1] == [LINT_EMPTY]


def test_summary_counts():
    prompts = [{"prompt": ""}, {"prompt": "fox"}, {"prompt": "fox"}]
    s = summary(prompts)
    assert s.get(LINT_EMPTY) == 1
    assert s.get(LINT_TOO_SHORT) == 2
    assert s.get(LINT_DUPLICATE) == 1
