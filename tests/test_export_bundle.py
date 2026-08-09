"""Тести збірки mint-ready бандла (services/export_bundle) — без мережі/Streamlit."""

import io
import json
import zipfile

import pytest

from services import export_bundle
from services.web3_service import PROMPT_LOCK_TRAIT


def _assets(n: int = 2) -> list[dict]:
    return [
        {
            "name": f"orig {i}",
            "description": "desc",
            "prompt": "a neon fox",
            "traits": {"Background": "Blue", "Eyes": "Laser"},
            "filename": f"src{i}.png",
            "image_bytes": f"PNGDATA{i}".encode(),
        }
        for i in range(n)
    ]


def _zip_names(data: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return set(zf.namelist())


def _zip_read(data: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return zf.read(name)


# ── B8: профіль «W3IR Platform» (.w3ir-nft.zip) ──────────────────────────────

def _w3ir_assets(n: int = 2) -> list[dict]:
    return [
        {
            "name": f"orig {i}",
            "description": "desc",
            "prompt": "a neon fox",
            "engine": "OpenAI gpt-image-1",
            "style": "cyberpunk",
            "seed": 100 + i,
            "traits": {"Background": "Blue", "Eyes": "Laser"},
            "filename": f"src{i}.png",
            "image_bytes": f"PNGDATA{i}".encode(),
        }
        for i in range(n)
    ]


def test_validate_export_assets_blocks_missing_image():
    assets = [{"description": "x", "path": ""}]
    errors, warnings = export_bundle.validate_export_assets(assets)
    assert any(code == "missing_image" for code, _ in errors)


def test_validate_export_assets_warns_empty_description():
    assets = [{"description": "", "prompt": "", "image_bytes": b"x" * 100}]
    errors, warnings = export_bundle.validate_export_assets(assets)
    assert not errors
    assert any(code == "empty_description" for code, _ in warnings)


def test_validate_export_assets_blocks_low_rating():
    assets = [{"description": "x", "image_bytes": b"x" * 100, "curator_rating": 2}]
    errors, _ = export_bundle.validate_export_assets(assets, min_curator_rating=4)
    assert any(code == "low_curator_rating" for code, _ in errors)


def test_validate_export_assets_warns_duplicate_prompt():
    assets = [
        {"description": "a", "prompt": "same fox", "image_bytes": b"x" * 100},
        {"description": "b", "prompt": "Same   Fox", "image_bytes": b"y" * 100},
    ]
    errors, warnings = export_bundle.validate_export_assets(assets)
    assert not errors
    assert any(code == "duplicate_prompt" for code, _ in warnings)


def test_validate_export_assets_blocks_tiny_image():
    assets = [{"description": "x", "image_bytes": b"tiny"}]
    errors, _ = export_bundle.validate_export_assets(assets)
    assert any(code == "corrupt_image" for code, _ in errors)


def test_validate_export_assets_no_assets():
    errors, warnings = export_bundle.validate_export_assets([])
    assert ("no_assets", None) in errors


def test_w3ir_package_structure_and_batch_manifest():
    data = export_bundle.build_w3ir_package_zip(_w3ir_assets(2), "My Coll")
    names = _zip_names(data)
    assert "batch-manifest.json" in names and "README.txt" in names
    for folder in ("items/item-0", "items/item-1"):
        assert {f"{folder}/manifest.json", f"{folder}/mint-state.json",
                f"{folder}/metadata.json"} <= names
    assert "items/item-0/asset/0.png" in names and "items/item-1/asset/1.png" in names
    batch = json.loads(_zip_read(data, "batch-manifest.json"))
    assert batch["version"] == export_bundle.W3IR_PACKAGE_VERSION == 1
    assert batch["itemCount"] == 2
    assert batch["folders"] == ["items/item-0", "items/item-1"]


def test_w3ir_manifest_fields_match_asset():
    data = export_bundle.build_w3ir_package_zip(_w3ir_assets(1), "Coll")
    manifest = json.loads(_zip_read(data, "items/item-0/manifest.json"))
    assert manifest["version"] == 1
    assert manifest["mediaKind"] == "image"
    assert manifest["mime"] == "image/png"
    # assetFile мусить вказувати на реальний файл у asset/
    assert f"items/item-0/asset/{manifest['assetFile']}" in _zip_names(data)


def test_w3ir_mint_state_contract():
    """Дзеркало sanitizeMintState платформи: name, traits[], aiMeta{prompt,model,style,seed}."""
    data = export_bundle.build_w3ir_package_zip(_w3ir_assets(1), "Coll")
    ms = json.loads(_zip_read(data, "items/item-0/mint-state.json"))
    assert ms["name"] == "Coll #1" and ms["name"].strip()
    assert ms["mediaKind"] == "image"
    # traits — масив {trait_type, value}, не dict
    assert isinstance(ms["traits"], list)
    assert {"trait_type": "Background", "value": "Blue"} in ms["traits"]
    # aiMeta з prompt+model (інакше платформа його відкине)
    assert ms["aiMeta"]["prompt"] == "a neon fox"
    assert ms["aiMeta"]["model"] == "OpenAI gpt-image-1"
    assert ms["aiMeta"]["style"] == "cyberpunk"
    assert ms["aiMeta"]["seed"] == 100


def test_w3ir_ai_meta_none_without_engine():
    assets = _w3ir_assets(1)
    del assets[0]["engine"]  # нема model → aiMeta має бути null (їх імпорт інакше відкине)
    data = export_bundle.build_w3ir_package_zip(assets, "Coll")
    ms = json.loads(_zip_read(data, "items/item-0/mint-state.json"))
    assert ms["aiMeta"] is None


def test_w3ir_jpeg_mime():
    assets = _w3ir_assets(1)
    assets[0]["filename"] = "pic.jpg"
    data = export_bundle.build_w3ir_package_zip(assets, "Coll")
    manifest = json.loads(_zip_read(data, "items/item-0/manifest.json"))
    assert manifest["mime"] == "image/jpeg"
    assert manifest["assetFile"].endswith(".jpg")


def test_w3ir_skips_items_without_bytes_and_empty_raises():
    assets = _w3ir_assets(2)
    assets[1].pop("image_bytes")
    data = export_bundle.build_w3ir_package_zip(assets, "Coll")
    batch = json.loads(_zip_read(data, "batch-manifest.json"))
    assert batch["itemCount"] == 1  # айтем без байтів пропущено
    with pytest.raises(ValueError):
        export_bundle.build_w3ir_package_zip([], "Coll")


def test_w3ir_metadata_preview_keeps_prompt_lock():
    """metadata.json — офлайн-прев'ю з повним provenance (Prompt-Lock), хоч імпорт його ігнорує."""
    data = export_bundle.build_w3ir_package_zip(_w3ir_assets(1), "Coll")
    meta = json.loads(_zip_read(data, "items/item-0/metadata.json"))
    assert meta["image"] == "asset/0.png"
    assert PROMPT_LOCK_TRAIT in {a["trait_type"] for a in meta["attributes"]}


def test_opensea_layout_1_indexed():
    data = export_bundle.build_zip("opensea", _assets(2), "My Coll")
    names = _zip_names(data)
    assert "images/1.png" in names and "images/2.png" in names
    assert "metadata/1.json" in names and "metadata/2.json" in names
    assert "collection.json" in names
    assert "README.txt" in names
    meta = json.loads(_zip_read(data, "metadata/1.json"))
    assert meta["name"] == "My Coll #1"
    assert meta["image"] == "1.png"
    trait_types = {a["trait_type"] for a in meta["attributes"]}
    assert PROMPT_LOCK_TRAIT in trait_types  # Prompt-Lock збережено


def test_metaplex_sugar_layout_0_indexed():
    data = export_bundle.build_zip("metaplex", _assets(2), "Apes", symbol="APE", royalty_bps=700)
    names = _zip_names(data)
    assert "assets/0.png" in names and "assets/0.json" in names
    assert "assets/1.json" in names
    assert "collection.json" not in names  # sugar не любить сторонніх файлів
    meta = json.loads(_zip_read(data, "assets/0.json"))
    assert meta["symbol"] == "APE"
    assert meta["seller_fee_basis_points"] == 700
    assert meta["properties"]["files"][0]["uri"] == "0.png"


def test_thirdweb_csv_layout():
    data = export_bundle.build_zip("thirdweb", _assets(2), "Coll")
    names = _zip_names(data)
    assert "images/0.png" in names and "images/1.png" in names
    assert "metadata.csv" in names
    csv_text = _zip_read(data, "metadata.csv").decode()
    header = csv_text.splitlines()[0]
    assert "name" in header and "image" in header
    assert "Background" in header and "Eyes" in header  # колонки трейтів


def test_generic_layout():
    data = export_bundle.build_zip("generic", _assets(1), "G")
    names = _zip_names(data)
    assert "images/1.png" in names
    assert "metadata/1.json" in names
    assert "collection.json" in names


def test_image_base_uri_applied():
    meta = export_bundle.build_metadata_list(
        "opensea", _assets(1), "C", image_base_uri="ipfs://CID/",
    )
    assert meta[0]["image"] == "ipfs://CID/1.png"


def test_build_zip_with_ipfs_result_includes_manifest():
    ipfs_res = {
        "images_cid": "bafyIMG",
        "metadata_cid": "bafyMETA",
        "base_uri": "ipfs://bafyMETA/",
        "image_base_uri": "ipfs://bafyIMG/",
        "count": 1,
        "published_at": "2026-06-26T12:00:00+00:00",
    }
    data = export_bundle.build_zip("opensea", _assets(1), "C", ipfs_result=ipfs_res)
    names = _zip_names(data)
    assert "ipfs-manifest.json" in names
    manifest = json.loads(_zip_read(data, "ipfs-manifest.json"))
    assert manifest["base_uri"] == "ipfs://bafyMETA/"
    meta = json.loads(_zip_read(data, "metadata/1.json"))
    assert meta["image"] == "ipfs://bafyIMG/1.png"


def test_unknown_platform_raises():
    with pytest.raises(ValueError):
        export_bundle.build_zip("foobar", _assets(1), "C")


def test_skips_missing_image_bytes():
    assets = _assets(1)
    del assets[0]["image_bytes"]
    data = export_bundle.build_zip("opensea", assets, "C")
    names = _zip_names(data)
    assert not any(n.startswith("images/") for n in names)
    assert "metadata/1.json" in names  # метадані все одно є


# --- G3.1 attribution «Made with w3ir» -------------------------------------

def test_attribution_in_readme_by_default(monkeypatch):
    monkeypatch.delenv("EXPORT_ATTRIBUTION", raising=False)
    data = export_bundle.build_zip("opensea", _assets(1), "C")
    readme = _zip_read(data, "README.txt").decode()
    assert export_bundle.ATTRIBUTION_TEXT in readme
    assert export_bundle.ATTRIBUTION_URL in readme


def test_attribution_in_metadata_for_evm(monkeypatch):
    monkeypatch.delenv("EXPORT_ATTRIBUTION", raising=False)
    meta = export_bundle.build_metadata_list("opensea", _assets(1), "C")
    assert meta[0]["created_with"] == "w3ir.io"


def test_attribution_skipped_in_metaplex_metadata(monkeypatch):
    """Sugar строго валідує JSON → top-level created_with туди не кладемо."""
    monkeypatch.delenv("EXPORT_ATTRIBUTION", raising=False)
    meta = export_bundle.build_metadata_list("metaplex", _assets(1), "C")
    assert "created_with" not in meta[0]
    # але README для Solana attribution усе одно несе
    data = export_bundle.build_zip("metaplex", _assets(1), "C")
    assert export_bundle.ATTRIBUTION_TEXT in _zip_read(data, "README.txt").decode()


def test_attribution_disabled_by_flag(monkeypatch):
    monkeypatch.setenv("EXPORT_ATTRIBUTION", "0")
    data = export_bundle.build_zip("opensea", _assets(1), "C")
    readme = _zip_read(data, "README.txt").decode()
    assert export_bundle.ATTRIBUTION_TEXT not in readme


def test_zip_readme_localized_uk():
    data = export_bundle.build_zip("opensea", _assets(1), "C", lang="uk")
    readme = _zip_read(data, "README.txt").decode()
    assert "Згенеровано NFT Prompt Builder" in readme
    assert "Цей застосунок сам NFT не мінтить" in readme


def test_zip_readme_localized_en():
    data = export_bundle.build_zip("opensea", _assets(1), "C", lang="en")
    readme = _zip_read(data, "README.txt").decode()
    assert "Generated by NFT Prompt Builder" in readme
    assert "This app does not mint NFTs by itself" in readme


def test_w3ir_zip_readme_localized_uk():
    data = export_bundle.build_w3ir_package_zip(_w3ir_assets(1), "Coll", lang="uk")
    readme = _zip_read(data, "README.txt").decode()
    assert "мінт-платформи W3IR" in readme
    assert "batch-manifest.json" in readme


# ── #8: прев'ю структури бандла (describe_bundle_structure, чиста) ─────────────

def test_describe_structure_opensea_matches_zip():
    """Прев'ю має називати ті ж теки/індексацію, що й реальний build_zip."""
    lines = export_bundle.describe_bundle_structure("opensea", 50, "Cosmic")
    joined = "\n".join(lines)
    assert lines[0] == "Cosmic-opensea.zip"
    # opensea 1-індексовано: перший 1, останній 50
    assert "images/1.png … 50.png" in joined
    assert "metadata/1.json … 50.json" in joined
    assert "collection.json" in joined
    assert lines[-1] == "└─ README.txt"
    # звіряємо з фактичним архівом
    names = _zip_names(export_bundle.build_zip("opensea", _assets(2), "Cosmic"))
    assert "images/1.png" in names and "metadata/2.json" in names and "collection.json" in names


def test_describe_structure_thirdweb_csv():
    lines = export_bundle.describe_bundle_structure("thirdweb", 10, "")
    joined = "\n".join(lines)
    assert lines[0] == "bundle-thirdweb.zip"
    assert "images/0.png … 9.png" in joined  # thirdweb 0-індексовано
    assert "metadata.csv" in joined and "collection.json" not in joined


def test_describe_structure_metaplex_assets_no_collection():
    lines = export_bundle.describe_bundle_structure("metaplex", 5, "C")
    joined = "\n".join(lines)
    assert "assets/0.png … 4.png" in joined and "assets/0.json … 4.json" in joined
    assert "collection.json" not in joined  # sugar не любить сторонніх файлів


def test_describe_structure_w3ir_per_item_folders():
    lines = export_bundle.describe_bundle_structure("w3ir", 50, "Cosmic")
    assert lines[0] == f"Cosmic{export_bundle.W3IR_PACKAGE_EXT}"
    joined = "\n".join(lines)
    assert "items/item-0/manifest.json" in joined
    assert "items/item-49/" in joined  # останній токен
    assert lines[-1] == "└─ batch-manifest.json"


def test_describe_structure_single_and_empty_and_unknown():
    # один токен — без діапазону «…»
    one = "\n".join(export_bundle.describe_bundle_structure("opensea", 1, "C"))
    assert "images/1.png" in one and "…" not in one
    # нуль активів — лише корінь
    assert export_bundle.describe_bundle_structure("opensea", 0, "C") == ["C-opensea.zip"]
    # невідома платформа — порожньо (UI ховає блок)
    assert export_bundle.describe_bundle_structure("nope", 5, "C") == []


# ── B9: профіль «Candy Machine / Sugar-ready» ────────────────────────────────

CREATOR = "8xH4kQ2Vn7Wd3FpRcLmJ9bT5sYfZ"  # фіктивний base58 pubkey


def _candy(assets=None, **kw):
    kw.setdefault("creator", CREATOR)
    return export_bundle.build_candy_machine_package_zip(assets or _assets(3), "Cosmic", **kw)


def test_candy_config_core_fields():
    cfg = export_bundle.build_candy_machine_config(
        25, symbol="W3IRLONGSYM", royalty_bps=750, creator=CREATOR,
    )
    assert cfg["number"] == 25
    assert cfg["symbol"] == "W3IRLONGSY"  # обрізано до 10 (METAPLEX_SYMBOL_LIMIT)
    assert cfg["sellerFeeBasisPoints"] == 750
    assert cfg["creators"] == [{"address": CREATOR, "share": 100}]
    assert cfg["uploadMethod"] == "bundlr"
    assert cfg["isSequential"] is False


def test_candy_config_requires_creator():
    with pytest.raises(ValueError):
        export_bundle.build_candy_machine_config(5, creator="  ")


def test_candy_config_never_leaks_pinata_jwt():
    cfg = export_bundle.build_candy_machine_config(5, creator=CREATOR)
    assert cfg["pinataConfig"] is None
    assert "jwt" not in json.dumps(cfg).lower()


def test_candy_guards_mapping():
    guards = export_bundle.CandyGuards(
        price_sol=0.5, treasury=CREATOR, start_date="2026-07-01T16:00:00Z",
        end_date="2026-07-08T16:00:00Z", mint_limit=5,
    )
    default = guards.to_guard_config()["default"]
    assert default["solPayment"] == {"value": 0.5, "destination": CREATOR}
    assert default["startDate"] == {"date": "2026-07-01T16:00:00Z"}
    assert default["endDate"] == {"date": "2026-07-08T16:00:00Z"}
    assert default["mintLimit"] == {"id": 1, "limit": 5}
    assert default["botTax"]["lastInstruction"] is True


def test_candy_guards_no_options_only_bottax():
    default = export_bundle.CandyGuards().to_guard_config()["default"]
    assert set(default) == {"botTax"}


def test_candy_guards_solpayment_requires_treasury():
    with pytest.raises(ValueError):
        export_bundle.CandyGuards(price_sol=1.0).to_guard_config()


def test_candy_package_structure():
    names = _zip_names(_candy())
    assert "config.json" in names
    assert "README.txt" in names
    assert "assets/collection.json" in names
    assert "assets/collection.png" in names
    assert {"assets/0.png", "assets/1.png", "assets/2.png"} <= names
    assert {"assets/0.json", "assets/1.json", "assets/2.json"} <= names
    # без сторонніх файлів у assets/ (лише png/json + collection.*)
    assets_files = {n for n in names if n.startswith("assets/")}
    assert all(n.endswith((".png", ".json")) for n in assets_files)


def test_candy_token_metadata_is_valid_metaplex():
    meta = json.loads(_zip_read(_candy(), "assets/0.json"))
    assert meta["image"] == "0.png"  # ім'я файлу — Sugar завантажить сам, не ipfs://
    assert meta["symbol"] == ""  # дефолт без symbol
    assert "properties" in meta and meta["properties"]["category"] == "image"
    assert any(a["trait_type"] == PROMPT_LOCK_TRAIT for a in meta["attributes"])


def test_candy_config_in_package_has_number_equal_assets():
    cfg = json.loads(_zip_read(_candy(_assets(4)), "config.json"))
    assert cfg["number"] == 4


def test_candy_allowlist_written_only_when_present():
    with_wl = _candy(guards=export_bundle.CandyGuards(allowlist=[CREATOR]))
    assert "allowlist.json" in _zip_names(with_wl)
    assert json.loads(_zip_read(with_wl, "allowlist.json")) == [CREATOR]
    assert "allowlist.json" not in _zip_names(_candy())


def test_candy_skips_items_without_bytes_and_empty_raises():
    assets = _assets(2)
    assets[1].pop("image_bytes")
    cfg = json.loads(_zip_read(_candy(assets), "config.json"))
    assert cfg["number"] == 1  # айтем без байтів пропущено
    with pytest.raises(ValueError):
        export_bundle.build_candy_machine_package_zip([], "C", creator=CREATOR)


def test_candy_package_requires_creator():
    with pytest.raises(ValueError):
        export_bundle.build_candy_machine_package_zip(_assets(1), "C", creator="")


def test_describe_structure_sugar():
    lines = export_bundle.describe_bundle_structure("sugar", 25, "Cosmic")
    assert lines[0] == f"Cosmic{export_bundle.CANDY_MACHINE_EXT}"
    joined = "\n".join(lines)
    assert "config.json" in joined
    assert "assets/collection.json" in joined
    assert "assets/0.png … 24.png" in joined
    assert lines[-1] == "└─ README.txt"
