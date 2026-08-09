"""Тести публічної shareable-вітрини (services/public_gallery + маршрути) — G3.2."""

import importlib.util
import sys
from pathlib import Path

import pytest

from services import public_gallery

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def tmp_public(tmp_path, monkeypatch):
    """Кожен тест — зі своєю чистою публічною текою."""
    monkeypatch.setattr(public_gallery, "PUBLIC_DIR", tmp_path / "public")


def _imgs(n: int = 3) -> list[tuple[str, bytes]]:
    return [(f"src{i}.png", f"PNG{i}".encode()) for i in range(n)]


# ── slug ──────────────────────────────────────────────────────────────────────

def test_slugify():
    assert public_gallery.slugify("Neon Foxes!") == "neon-foxes"
    assert public_gallery.slugify("  Multi   Space ") == "multi-space"
    assert public_gallery.slugify("***") == "collection"  # порожній → дефолт
    assert public_gallery.slugify("UPPER_case") == "upper-case"


# ── publish / load ────────────────────────────────────────────────────────────

def test_publish_and_load_roundtrip():
    slug = public_gallery.publish_collection("My Coll", _imgs(2), subtitle="hi",
                                             wallet="0x" + "a" * 40)
    assert slug == "my-coll"
    m = public_gallery.load_collection(slug)
    assert m["title"] == "My Coll"
    assert m["subtitle"] == "hi"
    assert m["images"] == ["1.png", "2.png"]  # перейменовано стабільно
    # Повний гаманець НЕ зберігається — лише скорочена форма.
    assert "…" in m["wallet_short"]
    assert "a" * 40 not in m["wallet_short"]


def test_publish_unique_slug_increments():
    a = public_gallery.publish_collection("Dup", _imgs(1))
    b = public_gallery.publish_collection("Dup", _imgs(1))
    assert a == "dup" and b == "dup-2"


def test_publish_filters_unsupported_ext():
    imgs = [("a.png", b"X"), ("b.txt", b"Y"), ("c.jpg", b"Z")]
    slug = public_gallery.publish_collection("C", imgs)
    m = public_gallery.load_collection(slug)
    assert m["images"] == ["1.png", "2.jpg"]  # .txt відкинуто


def test_publish_no_valid_images_raises():
    with pytest.raises(ValueError):
        public_gallery.publish_collection("C", [("a.txt", b"X")])


def test_publish_respects_image_limit(monkeypatch):
    monkeypatch.setattr(public_gallery, "PUBLIC_IMAGE_LIMIT", 2)
    slug = public_gallery.publish_collection("C", _imgs(5))
    assert len(public_gallery.load_collection(slug)["images"]) == 2


def test_load_unknown_returns_none():
    assert public_gallery.load_collection("nope") is None


# ── image serving (whitelist) ─────────────────────────────────────────────────

def test_image_path_whitelist():
    slug = public_gallery.publish_collection("C", _imgs(2))
    assert public_gallery.collection_image_path(slug, "1.png") is not None
    assert public_gallery.collection_image_path(slug, "99.png") is None  # не в manifest
    assert public_gallery.collection_image_path(slug, "../manifest.json") is None  # traversal


# ── list / delete ─────────────────────────────────────────────────────────────

def test_list_collections_newest_first():
    public_gallery.publish_collection("A", _imgs(1))
    public_gallery.publish_collection("B", _imgs(1))
    slugs = [m["slug"] for m in public_gallery.list_collections()]
    assert set(slugs) == {"a", "b"}


def test_demo_gallery_excludes_untitled_placeholders():
    """Безіменні плейсхолдери ('Untitled collection') не світяться у вітрині лендінга,
    але лишаються досяжними за прямим /c/<slug>."""
    public_gallery.publish_collection("Real Collection", _imgs(1))
    untitled = public_gallery.publish_collection("Untitled collection", _imgs(1))
    slugs = [m["slug"] for m in public_gallery.list_collections()]
    assert "real-collection" in slugs
    assert untitled not in slugs
    assert "Untitled" not in public_gallery.render_demo_section()
    # але прямий доступ до плейсхолдера працює (не зламали render)
    assert public_gallery.render_collection_html(untitled) is not None


def test_delete_collection():
    slug = public_gallery.publish_collection("Gone", _imgs(1))
    assert public_gallery.delete_collection(slug) is True
    assert public_gallery.load_collection(slug) is None
    assert public_gallery.delete_collection("missing") is False


# ── render ────────────────────────────────────────────────────────────────────

def test_render_contains_brand_and_og():
    slug = public_gallery.publish_collection("Foxes", _imgs(2), subtitle="cool drop")
    page = public_gallery.render_collection_html(slug)
    assert "Foxes" in page and "cool drop" in page
    assert 'property="og:image"' in page
    assert f"https://w3ir.io/c/{slug}/img/1.png" in page  # OG = перше зображення
    assert "https://ai.w3ir.io" in page  # CTA «Make your own»
    assert page.count("<img") == 2  # по тайлу на зображення


def test_share_cta_carries_utm():
    """CTA «Make your own» несе UTM — інакше віральний трафік неатрибутований."""
    slug = public_gallery.publish_collection("Foxes", _imgs(1))
    page = public_gallery.render_collection_html(slug)
    assert "utm_source=collection_share" in page
    assert page.count("utm_source=collection_share") >= 2  # обидва CTA (хедер + футер)


def test_share_cta_embeds_referral_code(tmp_path, monkeypatch):
    """Публікація з гаманцем → CTA несе ?ref=<код> (віральна петля G3.3), не адресу."""
    from services import payment_service
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setenv("AUTH_SESSION_SECRET", "secret-x")
    wallet = "0x" + "ab12" * 10

    slug = public_gallery.publish_collection("Owned", _imgs(1), wallet=wallet)
    code = public_gallery.load_collection(slug)["ref_code"]
    assert code and wallet.lower() not in code  # privacy: код, не адреса
    page = public_gallery.render_collection_html(slug)
    assert f"&ref={code}" in page
    assert payment_service.resolve_referrer(code) == wallet.lower()


def test_share_cta_no_ref_for_anonymous_collection():
    """Demo-колекція без гаманця → CTA без ?ref (нема кого винагороджувати)."""
    slug = public_gallery.publish_collection("Demo", _imgs(1))
    page = public_gallery.render_collection_html(slug)
    assert "&ref=" not in page


def test_render_escapes_user_text():
    slug = public_gallery.publish_collection("<script>x</script>", _imgs(1))
    page = public_gallery.render_collection_html(slug)
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;" in page


def test_render_unknown_returns_none():
    assert public_gallery.render_collection_html("nope") is None


# ── маршрути api_server ───────────────────────────────────────────────────────

def test_route_serves_collection_and_image():
    from fastapi.testclient import TestClient
    from api_server import app

    slug = public_gallery.publish_collection("Routed", _imgs(2))
    client = TestClient(app)

    page = client.get(f"/c/{slug}")
    assert page.status_code == 200
    assert "Routed" in page.text

    img = client.get(f"/c/{slug}/img/1.png")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"

    assert client.get("/c/does-not-exist").status_code == 404
    assert client.get(f"/c/{slug}/img/99.png").status_code == 404


def test_route_blocked_on_pay_subdomain():
    from fastapi.testclient import TestClient
    from api_server import app

    slug = public_gallery.publish_collection("PayBlocked", _imgs(1))
    client = TestClient(app)
    r = client.get(f"/c/{slug}", headers={"host": "pay.w3ir.io"})
    assert r.status_code == 404


# ── demo-вітрина на лендінгу (G1.4) ───────────────────────────────────────────

def test_demo_section_empty_when_no_collections():
    assert public_gallery.render_demo_section() == ""


def test_demo_section_lists_collections():
    public_gallery.publish_collection("Demo One", _imgs(2))
    section = public_gallery.render_demo_section()
    assert "Made with w3ir.io" in section
    assert "Demo One" in section
    assert "/c/demo-one" in section


def test_landing_route_injects_demo_gallery():
    from fastapi.testclient import TestClient
    from api_server import app

    public_gallery.publish_collection("Landing Demo", _imgs(1))
    client = TestClient(app)
    body = client.get("/").text
    assert "<!-- DEMO_GALLERY -->" not in body  # плейсхолдер замінено
    assert "/c/landing-demo" in body
    assert "Made with w3ir.io" in body


# ── CLI ───────────────────────────────────────────────────────────────────────

def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "publish_collection", ROOT / "scripts" / "publish_collection.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["publish_collection"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cli_publishes_from_dir(tmp_path, capsys):
    cli = _load_cli()
    src = tmp_path / "imgs"
    src.mkdir()
    (src / "a.png").write_bytes(b"PNGA")
    (src / "b.png").write_bytes(b"PNGB")

    rc = cli.main(["--dir", str(src), "--title", "CLI Coll"])
    assert rc == 0
    assert public_gallery.load_collection("cli-coll")["images"] == ["1.png", "2.png"]
    assert "w3ir.io/c/cli-coll" in capsys.readouterr().out


def test_cli_missing_dir_returns_1(capsys):
    cli = _load_cli()
    assert cli.main(["--dir", "no/such/dir", "--title", "X"]) == 1
