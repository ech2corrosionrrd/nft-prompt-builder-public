"""Тести LLM-полірування матриці (ПЛАН_ЯКОСТІ.md § Q1.4)."""

import json

from services.prompt_polish import (
    MODE_FULL,
    MODE_LIGHT,
    build_polish_system,
    build_polish_user,
    chunk_count,
    merge_polished,
    polish_prompts,
)


def _draft(prompt, **traits):
    return {"prompt": prompt, "traits": traits}


def test_chunk_count():
    assert chunk_count(0) == 0
    assert chunk_count(15, 15) == 1
    assert chunk_count(16, 15) == 2
    assert chunk_count(30, 10) == 3


def test_build_polish_system_mode_and_bible():
    light = build_polish_system(MODE_LIGHT)
    full = build_polish_system(MODE_FULL, style_bible="neon cyberpunk")
    assert "Lightly refine" in light
    assert "Rewrite into a vivid" in full
    assert "neon cyberpunk" in full


def test_build_polish_system_archetype_hint():
    abstract = build_polish_system(MODE_FULL, archetype="abstract_geometric")
    assert "no characters" in abstract.lower()
    pfp = build_polish_system(MODE_FULL, archetype="pfp")
    assert "Archetype rule" not in pfp


def test_build_polish_user_numbers_and_traits():
    user = build_polish_user([_draft("fox", Animal="fox"), _draft("owl")])
    assert "1. DRAFT: fox" in user
    assert "Animal: fox" in user
    assert "2. DRAFT: owl" in user
    assert "(none)" in user


def test_merge_polished_preserves_traits_and_moves_history():
    originals = [_draft("fox, crown", Animal="fox")]
    parsed = [{"index": 1, "prompt": "a regal fox wearing a golden crown", "negative": "blurry"}]
    out = merge_polished(originals, parsed)
    assert out[0]["prompt"] == "a regal fox wearing a golden crown"
    assert out[0]["negative"] == "blurry"
    assert out[0]["traits"] == {"Animal": "fox"}
    assert out[0]["polish_history"] == ["fox, crown"]
    assert out[0]["version"] == 2  # Q2.6: версія зросла після зміни промпту


def test_merge_polished_ignores_empty_fields():
    originals = [_draft("keep me")]
    out = merge_polished(originals, [{"index": 1, "prompt": "  ", "negative": "  "}])
    assert out[0]["prompt"] == "keep me"
    assert out[0].get("polish_history", []) == []
    assert "negative" not in out[0] or out[0]["negative"] == ""


def _drafts_in(user: str):
    """Рядки «N. DRAFT: …» у user-повідомленні чанку."""
    return [ln for ln in user.splitlines() if "DRAFT:" in ln]


def test_polish_prompts_happy_path_chunks():
    drafts = [_draft(f"d{i}") for i in range(3)]
    seen_users = []

    def fake_call(system, user, temperature):
        seen_users.append(user)
        items = [
            {"index": i + 1, "prompt": f"polished {ln.split('DRAFT: ')[1]}", "negative": "neg"}
            for i, ln in enumerate(_drafts_in(user))
        ]
        return json.dumps({"prompts": items})

    results, errors = polish_prompts(drafts, call=fake_call, chunk_size=2)
    assert errors == []
    assert len(results) == 3
    assert all(r["prompt"].startswith("polished d") for r in results)
    assert all(r["negative"] == "neg" for r in results)
    assert len(seen_users) == 2  # 3 драфти / 2 = 2 чанки


def test_polish_prompts_chunk_error_keeps_originals():
    drafts = [_draft("a"), _draft("b")]

    def boom(system, user, temperature):
        raise RuntimeError("api down")

    results, errors = polish_prompts(drafts, call=boom, chunk_size=5)
    assert len(results) == 2
    assert [r["prompt"] for r in results] == ["a", "b"]  # без змін
    assert len(errors) == 1
    assert "api down" in errors[0]


def test_polish_prompts_empty():
    assert polish_prompts([], call=lambda *a: "{}") == ([], [])
