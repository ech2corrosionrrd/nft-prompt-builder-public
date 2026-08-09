"""Тести чистих хелперів пакетної вкладки (ui/batch_panel.py), винесених з app.py."""

from batch import MODEL_PRICES
from ui import batch_panel


def test_estimate_batch_cost_scales_with_count():
    model = next(iter(MODEL_PRICES))
    one = batch_panel.estimate_batch_cost(model, 1)
    ten = batch_panel.estimate_batch_cost(model, 10)
    assert one > 0
    assert abs(ten - one * 10) < 1e-9, "вартість має масштабуватись лінійно з кількістю"


def test_estimate_batch_cost_zero_count():
    model = next(iter(MODEL_PRICES))
    assert batch_panel.estimate_batch_cost(model, 0) == 0


def test_estimate_batch_cost_unknown_model_uses_fallback():
    # невідома модель → дефолтний прайс (0.50/1.50), не виняток
    cost = batch_panel.estimate_batch_cost("totally-unknown-model", 5)
    expected = (5 * 120 * 0.50 + 5 * 350 * 1.50) / 1_000_000
    assert abs(cost - expected) < 1e-12


def test_build_markdown_export_structure():
    results = [
        {"id": 1, "prompt": "neon cat"},
        {"id": 2, "prompt": "stone temple"},
    ]
    md = batch_panel.build_markdown_export(results, "2026-06-20 12:00")
    assert md.startswith("# Batch NFT Prompts")
    assert "Generated: 2026-06-20 12:00" in md
    assert "## #1" in md and "## #2" in md
    assert "neon cat" in md and "stone temple" in md


def test_build_markdown_export_empty():
    md = batch_panel.build_markdown_export([], "2026-06-20 12:00")
    assert "# Batch NFT Prompts" in md
    assert "## #" not in md


def test_build_markdown_export_missing_fields():
    md = batch_panel.build_markdown_export([{}], "ts")
    assert "## #None" in md  # відсутній id → None, без винятку
