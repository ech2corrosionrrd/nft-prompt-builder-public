"""Тести help_center: унікальні anchor id у підзаголовках (BUG-004)."""

from ui.help_center import uniquify_subheadings


def test_uniquify_subheadings_duplicate_cheat_sheet():
    body = "#### Cheat sheet\n\nLine one.\n\n#### Cheat sheet\n\nLine two."
    out = uniquify_subheadings(body, "sec4")
    assert 'id="sec4-cheat-sheet"' in out
    assert 'id="sec4-cheat-sheet-1"' in out
    assert "#### Cheat sheet" not in out


def test_uniquify_subheadings_preserves_body_text():
    body = "Intro line.\n\n#### Quick cheat sheet\n\nSteps here."
    out = uniquify_subheadings(body, "s1")
    assert "Steps here." in out
    assert 'id="s1-quick-cheat-sheet"' in out
