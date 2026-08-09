from styles import NFT_STYLES, NFT_STYLE_DESCRIPTIONS
from templates import ADMIN_ONLY_TEMPLATES, COLLECTION_TEMPLATES, visible_templates
from preset_labels import style_description


def test_nft_styles_count():
    assert len(NFT_STYLES) == 29


def test_every_style_has_description_both_langs():
    for value in NFT_STYLES:
        assert value in NFT_STYLE_DESCRIPTIONS, value
        desc = NFT_STYLE_DESCRIPTIONS[value]
        assert desc["en"].strip(), value
        assert desc["uk"].strip(), value


def test_style_description_unknown_returns_empty():
    assert style_description("custom style", "en") == ""


def test_generative_abstract_description_mentions_variety():
    key = next(s for s in NFT_STYLES if "Generative Abstract" in s)
    assert "variety" in style_description(key, "en").lower()
    assert "варіатив" in style_description(key, "uk").lower()


def test_new_styles_present():
    labels = [s.split(" (")[0] for s in NFT_STYLES]
    assert "Low Poly / Voxel 3D" in labels
    assert "Watercolor Ink Illustration" in labels
    assert "Comic Book Western" in labels
    assert "Clay Plasticine Stop-motion" in labels
    assert "Photorealistic Cinematic Portrait" in labels
    assert "Minimalist Line Art" in labels
    assert "Generative Abstract / Parametric" in labels
    assert "Afrofuturism / Solarpunk" in labels
    assert "Retro Futurism Poster" in labels
    assert "Synthwave / Vaporwave / Outrun" in labels
    assert "Chibi / Super-deformed Kawaii" in labels
    assert "Glitch Art / Datamosh" in labels
    assert "Art Deco / Art Nouveau" in labels
    assert "Matte Painting Cinematic Landscape" in labels
    assert "Flat UI / App Icon Design" in labels
    assert "Badge / Medallion Engraving" in labels


def test_every_template_style_in_nft_styles():
    """Кожен шаблон посилається на існуючий пресет стилю."""
    for name, tpl in COLLECTION_TEMPLATES.items():
        assert tpl["style"] in NFT_STYLES, f"{name}: невідомий style «{tpl['style']}»"


def test_new_style_templates_exist():
    keys = {
        "Voxel Explorers",
        "Watercolor Dreams",
        "Comic Heroes PFP",
        "Clay Creatures",
        "Photorealistic PFP",
        "Abstract Geometry Series",
        "Brand Icon System",
        "Atmospheric Worlds",
        "Event Badge Series",
        "Sumi-e Ink Studies",
        "Vinyl Toy Squad",
        "Chrome Fashion Icons",
        "Chibi Champs",
        "Glitch Geometry",
        "Retro Poster Series",
        "Art Deco Medallions",
    }
    assert keys <= set(COLLECTION_TEMPLATES.keys())


def test_admin_only_demo_hidden_from_regular_users():
    """W3IR Showcase Demo — лише адмін; решта шаблонів видима всім."""
    assert "W3IR Showcase Demo" in ADMIN_ONLY_TEMPLATES
    regular = visible_templates(is_admin=False)
    assert "W3IR Showcase Demo" not in regular
    # усі НЕ-admin-only шаблони лишаються видимими звичайному користувачу
    assert set(regular) == set(COLLECTION_TEMPLATES) - set(ADMIN_ONLY_TEMPLATES)


def test_admin_sees_all_templates():
    admin_view = visible_templates(is_admin=True)
    assert "W3IR Showcase Demo" in admin_view
    assert set(admin_view) == set(COLLECTION_TEMPLATES)
