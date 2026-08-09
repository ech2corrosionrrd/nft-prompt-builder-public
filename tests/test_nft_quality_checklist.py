"""Tests for NFT Quality Checklist service."""

from __future__ import annotations

import json


from services import nft_quality_checklist


def _png_bytes(w: int, h: int) -> bytes:
    # Minimal valid PNG header with IHDR dimensions
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def test_platform_hints_opensea():
    report = nft_quality_checklist.analyze_collection(
        [_asset()], collection_name="OS", platform="opensea", ipfs_pinned=False,
    )
    codes = {i.code for i in report.items}
    assert "platform_hint_opensea" in codes
    assert "platform_hint_blur" in codes
    assert "platform_hint_opensea_ipfs" in codes


def test_platform_hints_sugar():
    report = nft_quality_checklist.analyze_collection(
        [_asset()], collection_name="Sol", platform="sugar",
    )
    codes = {i.code for i in report.items}
    assert "platform_hint_sugar_me" in codes
    assert "platform_hint_tensor" in codes
    assert "platform_selected" in codes


def test_supply_audit_hint_large_drop():
    assets = [_asset() for _ in range(600)]
    report = nft_quality_checklist.analyze_collection(assets, collection_name="Big")
    assert any(i.code == "supply_audit_hint" for i in report.items)


def test_description_long_warns():
    long_text = "x" * 650
    assets = [_asset(desc=long_text)]
    report = nft_quality_checklist.analyze_collection(assets, collection_name="Long")
    codes = {i.code for i in report.items}
    assert "description_long" in codes


def test_telegram_checklist_key():
    cl = nft_quality_checklist.normalize_checklist({"discord": True})
    assert "telegram" in cl
    assert cl["telegram"] is False


def test_checklist_boosts_marketing_and_legal():
    assets = [_asset() for _ in range(3)]
    empty = nft_quality_checklist.analyze_collection(
        assets, collection_name="Boost", checklist=nft_quality_checklist.default_checklist(),
    )
    full = nft_quality_checklist.analyze_collection(
        assets,
        collection_name="Boost",
        checklist={key: True for key in nft_quality_checklist.CHECKLIST_KEYS},
    )
    assert full.category_scores["marketing"] > empty.category_scores["marketing"]
    assert full.category_scores["legal"] > empty.category_scores["legal"]
    assert full.score >= empty.score


def test_normalize_checklist_ignores_unknown_keys():
    raw = {"discord": True, "unknown": True, "twitter": 1}
    cl = nft_quality_checklist.normalize_checklist(raw)
    assert cl["discord"] is True
    assert cl["twitter"] is True
    assert "unknown" not in cl


def test_generate_ai_tips_includes_checklist():
    report = nft_quality_checklist.analyze_collection(
        [_asset()],
        collection_name="AI",
        checklist={"discord": True},
    )
    captured: dict = {}

    def fake_call(system: str, user: str, temperature: float) -> str:
        captured["system"] = system
        captured["user"] = json.loads(user)
        return json.dumps({"tips": [{"category": "marketing", "text": "Grow Discord."}]})

    nft_quality_checklist.generate_ai_tips(
        report, collection_name="AI", call=fake_call, lang="en",
    )
    assert captured["user"]["checklist"]["discord"] is True
    assert "Visual:" in captured["system"]


def test_sample_indices_spreads():
    assert nft_quality_checklist._sample_indices(10) == [0, 2, 4, 7, 9]
    assert nft_quality_checklist._sample_indices(1) == [0]


def test_style_pairs():
    assert nft_quality_checklist._style_pairs(2) == [(0, 1)]
    pairs = nft_quality_checklist._style_pairs(10)
    assert pairs[0] == (0, 9)
    assert len(pairs) >= 2


def test_analyze_thumbnail_mock():
    assets = [_asset() for _ in range(4)]

    def fake_vision(system, user_text, images, response_format, temperature):
        assert len(images) == 4
        return json.dumps({
            "overall_score": 8,
            "readable_at_small_size": True,
            "issues": [],
            "samples": [
                {"token_index": 0, "readable": True, "note": "Clear subject."},
            ],
        })

    result = nft_quality_checklist.analyze_thumbnail_readability(
        assets, call=fake_vision, lang="en",
    )
    assert result["overall_score"] == 8
    assert result["samples_checked"] == 4


def test_run_ai_deep_dive_mock():
    report = nft_quality_checklist.analyze_collection([_asset()], collection_name="Deep")
    thumb_payload = {
        "overall_score": 7,
        "readable_at_small_size": True,
        "issues": [],
        "samples": [],
    }
    style_payload = {
        "overall_score": 6,
        "consistent": True,
        "summary": "Cohesive palette.",
        "pairs": [],
    }

    def fake_vision(system, user_text, images, response_format, temperature):
        name = response_format["json_schema"]["name"]
        if name == "thumbnail_readability":
            return json.dumps(thumb_payload)
        return json.dumps(style_payload)

    def fake_tips(system, user, temperature):
        payload = json.loads(user)
        assert "ai_thumbnail" in payload
        assert "ai_style" in payload
        return json.dumps({"tips": [{"category": "visual", "text": "Boost contrast."}]})

    result = nft_quality_checklist.run_ai_deep_dive(
        report,
        [_asset(), _asset(name="Token #2")],
        collection_name="Deep",
        vision_call=fake_vision,
        tips_call=fake_tips,
        lang="en",
    )
    assert result.thumbnail["overall_score"] == 7
    assert result.style["consistent"] is True
    assert result.tips[0]["text"] == "Boost contrast."


def test_validate_all_metadata_passes():
    assets = [_asset(name=f"Alpha #{i}") for i in range(3)]
    audit = nft_quality_checklist._validate_all_metadata(
        assets, collection_name="Test", platform="metaplex",
    )
    assert audit["tokens_checked"] == 3
    assert audit["json_errors"] == []
    assert audit["image_mismatches"] == []


def test_validate_all_metadata_detects_missing_name(monkeypatch):
    from services import export_bundle

    assets = [_asset()]
    original = export_bundle.build_metadata_list

    def broken(*args, **kwargs):
        meta = original(*args, **kwargs)
        meta[0] = {**meta[0], "name": ""}
        return meta

    monkeypatch.setattr(export_bundle, "build_metadata_list", broken)
    audit = nft_quality_checklist._validate_all_metadata(
        assets, collection_name="X", platform="opensea",
    )
    assert len(audit["json_errors"]) == 1


def test_is_webp():
    assert nft_quality_checklist._is_webp(b"RIFF\x00\x00\x00\x00WEBP")
    assert not nft_quality_checklist._is_webp(b"\x89PNG\r\n\x1a\n")


def test_ipfs_to_https():
    url = nft_quality_checklist._ipfs_to_https("ipfs://bafyTEST/0.json")
    assert url == "https://gateway.pinata.cloud/ipfs/bafyTEST/0.json"


def test_report_export():
    report = nft_quality_checklist.analyze_collection(
        [_asset()], collection_name="ExportTest",
    )
    data = nft_quality_checklist.report_to_dict(report)
    assert data["score"] == report.score
    assert len(data["items"]) == len(report.items)
    md = nft_quality_checklist.format_markdown(report, "ExportTest")
    assert "NFT Quality Report" in md
    assert "ExportTest" in md


def test_ipfs_pinned_with_probe(monkeypatch):
    assets = [_asset()]

    def fake_probe(*args, **kwargs):
        return {"skipped": False, "ok": True, "detail": ""}

    monkeypatch.setattr(nft_quality_checklist, "_probe_ipfs_sample", fake_probe)
    report = nft_quality_checklist.analyze_collection(
        assets,
        collection_name="IPFS",
        platform="opensea",
        ipfs_result={
            "metadata_cid": "bafyMETA",
            "images_cid": "bafyIMG",
            "base_uri": "ipfs://bafyMETA/",
            "image_base_uri": "ipfs://bafyIMG/",
        },
    )
    codes = {i.code for i in report.items}
    assert "ipfs_pinned" in codes
    assert "ipfs_reachable" in codes


def test_local_zip_warns_evm():
    report = nft_quality_checklist.analyze_collection(
        [_asset()], collection_name="Local", platform="opensea", ipfs_pinned=False,
    )
    assert any(i.code == "ipfs_local_zip" for i in report.items)


def _asset(
    *,
    desc: str = "A" * 200,
    traits: dict | None = None,
    rating: int = 4,
    w: int = 2048,
    h: int = 2048,
    name: str = "Token #1",
) -> dict:
    return {
        "name": name,
        "description": desc,
        "prompt": desc,
        "traits": traits or {"Background": "Deep Nebula", "Eyes": "Laser"},
        "curator_rating": rating,
        "image_bytes": _png_bytes(w, h),
    }


def test_analyze_empty_assets():
    report = nft_quality_checklist.analyze_collection([])
    assert report.score == 0
    assert report.band == "risk"
    assert any(i.code == "no_assets" for i in report.items)


def test_analyze_good_collection():
    assets = [_asset() for _ in range(5)]
    report = nft_quality_checklist.analyze_collection(
        assets,
        collection_name="Test Collection",
        platform="metaplex",
        royalty_bps=500,
        ipfs_pinned=False,
    )
    assert report.score >= 75
    assert report.band in ("ready", "minor", "major")
    assert report.summary["token_count"] == 5


def test_score_bands():
    assert nft_quality_checklist.score_band(95) == "ready"
    assert nft_quality_checklist.score_band(80) == "minor"
    assert nft_quality_checklist.score_band(65) == "major"
    assert nft_quality_checklist.score_band(40) == "risk"


def test_low_resolution_warns():
    assets = [_asset(w=512, h=512)]
    report = nft_quality_checklist.analyze_collection(
        assets, collection_name="Lo", upscale_available=True,
    )
    codes = {i.code for i in report.items}
    assert "resolution_low" in codes or "resolution_ok" in codes
    assert "upscale_hint" in codes


def test_hashtags_and_urls():
    desc = "A" * 120 + " #PFP #generative #Solana https://w3ir.io"
    report = nft_quality_checklist.analyze_collection(
        [_asset(desc=desc)], collection_name="Tagged",
    )
    codes = {i.code for i in report.items}
    assert "hashtags_good" in codes or "hashtags_ok" in codes
    assert "external_url_ok" in codes


def test_rarity_skew():
    assets = [
        _asset(traits={"Bg": "Common" if i < 8 else "Rare"})
        for i in range(10)
    ]
    report = nft_quality_checklist.analyze_collection(assets, collection_name="Skew")
    assert any(i.code == "rarity_skewed" for i in report.items)


def test_sugar_symbol_and_price():
    report = nft_quality_checklist.analyze_collection(
        [_asset()], collection_name="X", platform="sugar",
        symbol="WAYTOOLONGSYMBOL", mint_price_sol=0.1,
    )
    codes = {i.code for i in report.items}
    assert "symbol_too_long" in codes
    assert "mint_price_set" in codes


def test_checks_all_assets_not_sample():
    assets = [_asset(w=2048) for _ in range(20)]
    report = nft_quality_checklist.analyze_collection(assets, collection_name="Many")
    assert report.summary.get("images_checked") == 20


def test_generate_ai_tips_mock():
    report = nft_quality_checklist.analyze_collection(
        [_asset()],
        collection_name="Demo",
    )

    def fake_call(system: str, user: str, temperature: float) -> str:
        return json.dumps({
            "tips": [
                {"category": "marketing", "text": "Post a thread before mint."},
            ],
        })

    tips = nft_quality_checklist.generate_ai_tips(
        report, collection_name="Demo", call=fake_call, lang="en",
    )
    assert len(tips) == 1
    assert "thread" in tips[0]["text"]


def test_all_qc_i18n_keys_exist():
    from ui_strings import LANG_EN, LANG_UA, _STRINGS

    # Every item code used in service should have i18n
    sample = nft_quality_checklist.analyze_collection(
        [_asset()], collection_name="X", platform="opensea", ipfs_pinned=True,
    )
    for item in sample.items:
        key = f"qc.item.{item.code}"
        assert key in _STRINGS, f"missing i18n: {key}"
        assert LANG_UA in _STRINGS[key]
        assert LANG_EN in _STRINGS[key]

    for cat in nft_quality_checklist.CATEGORIES:
        assert f"qc.cat.{cat}" in _STRINGS
