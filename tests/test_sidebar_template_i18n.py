"""Sidebar: опис шаблону слідує ui_lang (не fallback на іншу мову)."""

from __future__ import annotations

import re

from templates import COLLECTION_TEMPLATES, template_description
from ui import sidebar as sidebar_mod

_CYRILLIC = re.compile(r"[\u0400-\u04FF]")


def test_template_description_en_has_no_cyrillic_fallback():
  tpl = COLLECTION_TEMPLATES["BAYC-style PFP"]
  en = template_description(tpl, "en")
  uk = template_description(tpl, "uk")
  assert en and uk
  assert en != uk
  assert not _CYRILLIC.search(en), "EN UI must not show Ukrainian description text"
  assert _CYRILLIC.search(uk)


def test_template_card_html_uses_ui_lang(monkeypatch):
  tpl = COLLECTION_TEMPLATES["Cyberpunk PFP"]
  monkeypatch.setattr(sidebar_mod, "ui_lang", lambda: "en")
  html = sidebar_mod._template_card_html(tpl)
  assert "Neon cyberpunk" in html
  assert not _CYRILLIC.search(html)

  monkeypatch.setattr(sidebar_mod, "ui_lang", lambda: "uk")
  html_uk = sidebar_mod._template_card_html(tpl)
  assert _CYRILLIC.search(html_uk)
  assert "Neon cyberpunk" not in html_uk
