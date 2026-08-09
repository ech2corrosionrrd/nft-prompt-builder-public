import json
import zipfile
import io

import pytest

from batch import (
    add_rarity_scores,
    assign_chunk_positions,
    build_batch_user_prompt,
    build_metadata,
    clean_metadata,
    count_combinations,
    estimate_cost,
    metadata_zip,
    parse_batch_response,
    parse_trait_lines,
    sample_trait_combinations,
    strip_platform_flags,
    supports_temperature,
    to_csv,
)


# ── build_batch_user_prompt ───────────────────────────────────────────────────

def test_build_batch_user_prompt_includes_extra_notes():
    base = {
        "idea": "ape", "style": "s", "camera": "c", "lighting": "l",
        "background": "b", "quality": "q", "mood": "m", "extra_notes": "no text",
    }
    text = build_batch_user_prompt(base, [{"head": "crown"}], "--ar 1:1")
    assert "Додаткові побажання: no text" in text


def test_build_batch_user_prompt_omits_empty_notes():
    base = {
        "idea": "ape", "style": "s", "camera": "c", "lighting": "l",
        "background": "b", "quality": "q", "mood": "m", "extra_notes": "  ",
    }
    text = build_batch_user_prompt(base, [{"head": "crown"}], "--ar 1:1")
    assert "Додаткові побажання" not in text


# ── parse_trait_lines ─────────────────────────────────────────────────────────

def test_parse_trait_lines_plain():
    assert parse_trait_lines("корона\nбейсболка\n") == [("корона", 1.0), ("бейсболка", 1.0)]


def test_parse_trait_lines_with_weights():
    items = parse_trait_lines("корона | 1\nбейсболка | 20\nшолом|5.5")
    assert items == [("корона", 1.0), ("бейсболка", 20.0), ("шолом", 5.5)]


def test_parse_trait_lines_invalid_weight_kept_as_name():
    items = parse_trait_lines("маска | золота")
    assert items == [("маска | золота", 1.0)]


def test_parse_trait_lines_skips_empty():
    assert parse_trait_lines("\n  \n") == []


# ── sample_trait_combinations ─────────────────────────────────────────────────

def test_sample_unique_when_enough_combos():
    traits = {
        "head": [("a", 1), ("b", 1), ("c", 1)],
        "eyes": [("x", 1), ("y", 1), ("z", 1)],
    }
    combos = sample_trait_combinations(traits, 9)
    assert len(combos) == 9
    assert len({tuple(sorted(c.items())) for c in combos}) == 9


def test_sample_fills_duplicates_when_space_exhausted():
    traits = {"head": [("a", 1), ("b", 1)]}
    combos = sample_trait_combinations(traits, 5)
    assert len(combos) == 5
    assert {c["head"] for c in combos} == {"a", "b"}


def test_sample_accepts_plain_strings():
    combos = sample_trait_combinations({"head": ["a", "b"]}, 2)
    assert len(combos) == 2
    assert all(c["head"] in ("a", "b") for c in combos)


def test_sample_empty_traits():
    assert sample_trait_combinations({}, 3) == [{}, {}, {}]


def test_sample_weight_bias():
    traits = {"head": [("rare", 1), ("common", 50)]}
    counts = {"rare": 0, "common": 0}
    for _ in range(200):
        for c in sample_trait_combinations(traits, 1):
            counts[c["head"]] += 1
    assert counts["common"] > counts["rare"]


def test_count_combinations():
    assert count_combinations({"a": [1, 2, 3], "b": [1, 2]}) == 6
    assert count_combinations({}) == 0


# ── parse_batch_response ──────────────────────────────────────────────────────

def test_parse_object_with_prompts():
    raw = '{"prompts": [{"index": 1, "prompt": "p1", "negative": "n1"}]}'
    assert parse_batch_response(raw) == [{"index": 1, "prompt": "p1", "negative": "n1"}]


def test_parse_bare_array():
    raw = '[{"prompt": "p1", "negative": ""}]'
    assert parse_batch_response(raw)[0]["prompt"] == "p1"


def test_parse_fenced_json():
    raw = 'Ось результат:\n```json\n{"prompts": [{"index": 1, "prompt": "p", "negative": "n"}]}\n```'
    assert parse_batch_response(raw)[0]["prompt"] == "p"


def test_parse_rejects_missing_prompt():
    with pytest.raises(ValueError):
        parse_batch_response('{"prompts": [{"index": 1, "negative": "n"}]}')


def test_parse_rejects_invalid_shape():
    with pytest.raises(ValueError):
        parse_batch_response('{"foo": 1}')


# ── rarity ────────────────────────────────────────────────────────────────────

def test_rarity_scores_rarer_is_higher():
    rows = [
        {"id": 1, "traits": {"head": "rare"}},
        {"id": 2, "traits": {"head": "common"}},
        {"id": 3, "traits": {"head": "common"}},
        {"id": 4, "traits": {"head": "common"}},
    ]
    add_rarity_scores(rows)
    assert rows[0]["rarity_score"] > rows[1]["rarity_score"]
    assert rows[1]["rarity_score"] == rows[2]["rarity_score"]


def test_rarity_empty_rows():
    rows: list[dict] = []
    add_rarity_scores(rows)
    assert rows == []


# ── export ────────────────────────────────────────────────────────────────────

def test_to_csv_escapes_quotes_and_commas():
    rows = [{"id": 1, "prompt": 'a "quoted", prompt', "negative": "n", "traits": {"head": "a"}, "rarity_score": 2.5}]
    csv_text = to_csv(rows)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "id,prompt,negative,traits,rarity_score"
    assert '"a ""quoted"", prompt"' in lines[1]


def test_build_metadata_erc721_uses_llm_attributes():
    rows = [{
        "id": 7,
        "traits": {"Голова": "корона", "Очі": "лазерні"},
        "attributes": [
            {"trait_type": "Head", "value": "crown"},
            {"trait_type": "Eyes", "value": "laser"},
        ],
    }]
    meta = build_metadata(rows, "My Apes", "Cool apes", "ipfs://QmHash")
    assert meta[0]["name"] == "My Apes #7"
    assert meta[0]["image"] == "ipfs://QmHash/7.png"
    assert {"trait_type": "Head", "value": "crown"} in meta[0]["attributes"]


def test_build_metadata_fallback_english_categories():
    rows = [{"id": 1, "traits": {"Голова / Шолом / Маска": "корона"}}]
    meta = build_metadata(rows, "Col")
    assert meta[0]["attributes"] == [{"trait_type": "Head / Helmet / Mask", "value": "корона"}]


def test_build_metadata_without_base_uri():
    meta = build_metadata([{"id": 1, "traits": {}}], "X")
    assert meta[0]["image"] == "1.png"


def test_metadata_zip_contains_per_token_files():
    rows = [{"id": 1, "traits": {"a": "b"}}, {"id": 2, "traits": {"a": "c"}}]
    meta = build_metadata(rows, "Col")
    data = metadata_zip(meta)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert names == {"1.json", "2.json", "_collection.json"}
        token = json.loads(zf.read("1.json"))
        assert token["name"] == "Col #1"
        assert "token_id" not in token


def test_clean_metadata_strips_token_id():
    rows = [{"id": 5, "traits": {}}]
    meta = build_metadata(rows, "X")
    assert "token_id" in meta[0]
    exported = clean_metadata(meta)
    assert "token_id" not in exported[0]
    assert exported[0]["name"] == "X #5"


# ── strip_platform_flags ──────────────────────────────────────────────────────

def test_strip_platform_flags():
    prompt = "cyber ape, neon city --ar 1:1 --s 250 --c 10 --v 6.0 --seed 42"
    assert strip_platform_flags(prompt) == "cyber ape, neon city"


def test_strip_platform_flags_no_flags():
    assert strip_platform_flags("clean prompt") == "clean prompt"


# ── cost ──────────────────────────────────────────────────────────────────────

def test_estimate_cost_known_model():
    cost = estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.15 + 0.60)


def test_estimate_cost_unknown_model_uses_fallback():
    assert estimate_cost("unknown", 1_000_000, 0) == pytest.approx(0.50)


# ── supports_temperature ──────────────────────────────────────────────────────

def test_supports_temperature_gpt_models():
    assert supports_temperature("gpt-4o-mini")
    assert supports_temperature("gpt-4o")
    assert supports_temperature("gpt-4.1")


def test_supports_temperature_reasoning_models():
    assert not supports_temperature("o4-mini")
    assert not supports_temperature("o3")
    assert not supports_temperature("o1-preview")


# ── assign_chunk_positions ────────────────────────────────────────────────────

def test_assign_positions_honors_valid_indices():
    items = [{"index": 2, "prompt": "b"}, {"index": 1, "prompt": "a"}]
    assert assign_chunk_positions(items, 2) == [(2, items[0]), (1, items[1])]


def test_assign_positions_duplicate_index_gets_free_slot():
    items = [{"index": 1, "prompt": "a"}, {"index": 1, "prompt": "b"}]
    positions = [pos for pos, _ in assign_chunk_positions(items, 2)]
    assert sorted(positions) == [1, 2]


def test_assign_positions_out_of_range_index():
    items = [{"index": 99, "prompt": "a"}, {"prompt": "b"}]
    positions = [pos for pos, _ in assign_chunk_positions(items, 2)]
    assert sorted(positions) == [1, 2]


def test_assign_positions_truncates_extra_items():
    items = [{"index": i, "prompt": str(i)} for i in range(1, 5)]
    assert len(assign_chunk_positions(items, 2)) == 2
