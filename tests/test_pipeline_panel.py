"""Тести вкладки конвеєра (ui/pipeline_panel.py), винесеної з app.py."""

from ui import pipeline_panel


def test_pipeline_metrics_counts():
    out = pipeline_panel.pipeline_metrics(
        generated_prompts=[1, 2, 3],
        pipeline_images=[1, 2],
        approved_content=[1],
        mint_assets=[],
    )
    assert out == {"prompts": 3, "generated": 2, "approved": 1, "queue": 0}


def test_pipeline_metrics_all_empty():
    out = pipeline_panel.pipeline_metrics([], [], [], [])
    assert out == {"prompts": 0, "generated": 0, "approved": 0, "queue": 0}


def test_pipeline_metrics_keys_stable():
    out = pipeline_panel.pipeline_metrics([], [], [], [])
    assert set(out) == {"prompts", "generated", "approved", "queue"}
