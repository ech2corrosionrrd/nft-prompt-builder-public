"""Тести Style Lock / Collection Bible (ПЛАН_ЯКОСТІ.md § Q2.1)."""

from services.style_bible import (
    MAX_REFERENCE_IMAGES,
    StyleBible,
    from_template,
    merge,
)


def test_is_empty():
    assert StyleBible().is_empty()
    assert not StyleBible(style="pixel art").is_empty()
    assert not StyleBible(reference_images=["a.png"]).is_empty()


def test_reference_images_clamped():
    b = StyleBible(reference_images=["1", "2", "3", "4", "5"])
    assert len(b.reference_images) == MAX_REFERENCE_IMAGES


def test_roundtrip_dict():
    b = StyleBible(style="anime", lighting="soft", camera="close-up", background_rule="solid", reference_images=["r.png"])
    assert StyleBible.from_dict(b.to_dict()) == b


def test_from_dict_tolerates_missing():
    b = StyleBible.from_dict({"style": "x"})
    assert b.style == "x"
    assert b.lighting == ""
    assert b.reference_images == []


def test_bible_text_only_filled_fields():
    text = StyleBible(style="pixel art", camera="symmetrical").bible_text()
    assert "Style: pixel art" in text
    assert "Camera framing: symmetrical" in text
    assert "Lighting" not in text


def test_as_suffix_comma_joined():
    assert StyleBible(style="anime", lighting="soft light").as_suffix() == "anime, soft light"
    assert StyleBible().as_suffix() == ""


def test_from_template_maps_background_key():
    tpl = {"style": "S", "camera": "C", "lighting": "L", "background": "BG"}
    b = from_template(tpl)
    assert (b.style, b.camera, b.lighting, b.background_rule) == ("S", "C", "L", "BG")


def test_merge_override_wins_nonempty():
    base = StyleBible(style="base-style", lighting="base-light", camera="base-cam")
    override = StyleBible(style="my-style", camera="")  # camera порожній → лишається base
    out = merge(base, override)
    assert out.style == "my-style"
    assert out.camera == "base-cam"
    assert out.lighting == "base-light"


def test_merge_reference_images():
    base = StyleBible(reference_images=["base.png"])
    assert merge(base, StyleBible()).reference_images == ["base.png"]
    assert merge(base, StyleBible(reference_images=["new.png"])).reference_images == ["new.png"]
