"""Тести фільтрації історії (ui/history_panel.py), винесеної з app.py."""

from ui import history_panel

_HISTORY = [
    {"idea": "cyber cat", "platform": "opensea", "model": "gpt-image-1", "content": "neon kitty"},
    {"idea": "ancient ruin", "platform": "metaplex", "model": "flux", "content": "stone temple"},
    {"idea": "space dog", "platform": "opensea", "model": "flux", "content": "astro pup"},
]


def test_empty_query_returns_all():
    assert history_panel.filter_history(_HISTORY, "") == _HISTORY
    assert history_panel.filter_history(_HISTORY, "   ") == _HISTORY


def test_filter_by_idea_substring():
    out = history_panel.filter_history(_HISTORY, "cat")
    assert len(out) == 1 and out[0]["idea"] == "cyber cat"


def test_filter_is_case_insensitive():
    assert len(history_panel.filter_history(_HISTORY, "CYBER")) == 1


def test_filter_matches_platform_model_and_content():
    assert len(history_panel.filter_history(_HISTORY, "opensea")) == 2
    assert len(history_panel.filter_history(_HISTORY, "flux")) == 2
    assert len(history_panel.filter_history(_HISTORY, "temple")) == 1


def test_no_match_returns_empty():
    assert history_panel.filter_history(_HISTORY, "nonexistent") == []


def test_returns_copy_not_reference():
    """Порожній запит повертає НОВИЙ список (не той самий обʼєкт)."""
    out = history_panel.filter_history(_HISTORY, "")
    assert out == _HISTORY and out is not _HISTORY


def test_handles_missing_keys():
    history = [{"idea": "only idea"}]
    assert len(history_panel.filter_history(history, "idea")) == 1
    assert history_panel.filter_history(history, "missing") == []


def test_history_list_html_has_live_search():
    html_out = history_panel.history_list_html(
        _HISTORY,
        search_placeholder="Search…",
        download_label="Download",
    )
    assert 'type="search"' in html_out
    assert "_w3irHistFilter" in html_out
    assert "Search…" in html_out
    assert "cyber cat" in html_out


def test_history_list_html_escapes_script_content():
    history = [{"idea": "<script>", "content": "</script>", "timestamp": ""}]
    html_out = history_panel.history_list_html(
        history,
        search_placeholder="q",
        download_label="dl",
    )
    assert "<script>" not in html_out.split("<script>", 1)[0]  # payload escaped in JSON
    assert '"idea": "<script>"' in html_out or "\\u003cscript\\u003e" in html_out
