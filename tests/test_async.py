"""Mock-тести для async-функцій генерації (без реальних API-запитів)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from batch import generate_batch_async

BASE = {
    "idea": "ape", "style": "s", "camera": "c",
    "lighting": "l", "background": "b", "quality": "q", "mood": "m",
}


def _completion_mock(items: list[dict], prompt_tokens: int = 100, completion_tokens: int = 50):
    msg = MagicMock()
    msg.content = json.dumps({"prompts": items})
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


@patch("batch.AsyncOpenAI")
def test_generate_batch_async_success(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _completion_mock(
        [{"index": 1, "prompt": "cyber ape, neon city", "negative": "blurry",
          "attributes": [{"trait_type": "Head", "value": "hat"}]}]
    )

    results, usage, errors = asyncio.run(
        generate_batch_async("key", "gpt-4o-mini", "Midjourney v7", BASE, [{"head": "hat"}], "--ar 1:1", 0.7)
    )

    assert len(results) == 1
    assert results[0]["prompt"] == "cyber ape, neon city"
    assert results[0]["negative"] == "blurry"
    assert results[0]["traits"] == {"head": "hat"}
    assert "rarity_score" in results[0]
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert errors == []


@patch("batch.AsyncOpenAI")
def test_generate_batch_async_token_ids_sequential(mock_cls):
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _completion_mock([
        {"index": 1, "prompt": "p1", "negative": "", "attributes": [{"trait_type": "Head", "value": "a"}]},
        {"index": 2, "prompt": "p2", "negative": "", "attributes": [{"trait_type": "Head", "value": "b"}]},
    ])

    combos = [{"head": "a"}, {"head": "b"}]
    results, _, _ = asyncio.run(
        generate_batch_async("key", "gpt-4o-mini", "Midjourney v7", BASE, combos, "", 0.7, chunk_size=2)
    )

    assert [r["id"] for r in results] == [1, 2]


@patch("batch.AsyncOpenAI")
def test_generate_batch_async_total_failure_raises(mock_cls):
    """Якщо всі чанки впали — користувач бачить причину, а не порожній результат."""
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = RuntimeError("rate limit")

    with pytest.raises(RuntimeError, match="rate limit"):
        asyncio.run(
            generate_batch_async("key", "gpt-4o-mini", "Midjourney v7", BASE, [{"head": "hat"}], "", 0.7)
        )


@patch("batch.AsyncOpenAI")
def test_generate_batch_async_partial_failure(mock_cls):
    """Успішні чанки зберігаються, а помилки інших повертаються списком."""
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = [
        _completion_mock([{"index": 1, "prompt": "good prompt", "negative": "",
                           "attributes": [{"trait_type": "Head", "value": "hat"}]}]),
        RuntimeError("API error"),
    ]

    combos = [{"head": "hat"}, {"head": "glasses"}]
    results, usage, errors = asyncio.run(
        generate_batch_async("key", "gpt-4o-mini", "Midjourney v7", BASE, combos, "", 0.7, chunk_size=1)
    )

    assert len(results) == 1
    assert results[0]["prompt"] == "good prompt"
    assert len(errors) == 1 and "API error" in errors[0]


@patch("batch.AsyncOpenAI")
def test_generate_batch_async_duplicate_indices_no_id_collision(mock_cls):
    """Дубльовані index від моделі не створюють дублікати token id."""
    mock_client = AsyncMock()
    mock_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _completion_mock([
        {"index": 2, "prompt": "p-a", "negative": "", "attributes": [{"trait_type": "Head", "value": "a"}]},
        {"index": 2, "prompt": "p-b", "negative": "", "attributes": [{"trait_type": "Head", "value": "b"}]},
    ])

    combos = [{"head": "a"}, {"head": "b"}]
    results, _, _ = asyncio.run(
        generate_batch_async("key", "gpt-4o-mini", "Midjourney v7", BASE, combos, "", 0.7, chunk_size=2)
    )

    assert sorted(r["id"] for r in results) == [1, 2]
