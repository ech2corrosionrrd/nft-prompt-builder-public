"""Тести P3.5 — generate N archetypes."""

from __future__ import annotations

import json

from services import archetype_generator


def _fake_call(names: list[str]):
  def _call(system: str, user: str, temperature: float) -> str:
      return json.dumps({"names": names})
  return _call


def test_credit_cost_chunks():
    assert archetype_generator.credit_cost(0) == 0
    assert archetype_generator.credit_cost(1) == 1
    assert archetype_generator.credit_cost(15) == 1
    assert archetype_generator.credit_cost(16) == 2
    assert archetype_generator.credit_cost(50) == 4


def test_parse_names_dedupes():
    raw = json.dumps({"names": ["Cyber Fox", "cyber fox", "Neon Cat", ""]})
    assert archetype_generator.parse_names(raw) == ["Cyber Fox", "Neon Cat"]


def test_generate_archetypes_unique():
    batch = [f"archetype {i}" for i in range(20)]
    names, errors = archetype_generator.generate_archetypes(
        20,
        "cyber animals",
        archetype="pfp",
        call=_fake_call(batch),
    )
    assert errors == []
    assert len(names) == 20
    assert len(set(n.casefold() for n in names)) == 20


def test_generate_abstract_system_hint():
    captured: list[str] = []

    def _call(system: str, user: str, temperature: float) -> str:
        captured.append(system)
        return json.dumps({"names": ["gradient torus", "sacred grid"]})

    names, _ = archetype_generator.generate_archetypes(
        2,
        "sacred geometry",
        archetype="abstract_geometric",
        call=_call,
    )
    assert len(names) == 2
    assert "NO characters" in captured[0] or "no characters" in captured[0].lower()


def test_build_user_lists_existing():
    user = archetype_generator.build_user("neon city", 5, existing=["fox", "cat"])
    assert "neon city" in user
    assert "fox" in user
    assert "do NOT repeat" in user
