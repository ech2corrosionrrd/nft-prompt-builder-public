import json

import pytest

import ipfs
from batch import build_metadata_metaplex


def test_collect_directory_files(tmp_path):
    (tmp_path / "1.png").write_bytes(b"img1")
    (tmp_path / "2.png").write_bytes(b"img2")
    (tmp_path / "notes.txt").write_text("skip me")
    (tmp_path / "meta.json").write_text("{}")

    files = ipfs.collect_directory_files(tmp_path, "col")
    paths = [p for p, _ in files]
    assert "col/1.png" in paths and "col/2.png" in paths
    assert "col/meta.json" in paths
    assert all("notes.txt" not in p for p in paths)
    assert dict(files)["col/1.png"] == b"img1"


def test_metadata_files_naming():
    metadata = [
        {"name": "Col #1", "image": "1.png", "attributes": []},
        {"name": "Col #12", "image": "12.png", "attributes": []},
    ]
    files = ipfs.metadata_files(metadata, "run")
    paths = [p for p, _ in files]
    assert paths == ["run/1.json", "run/12.json"]
    parsed = json.loads(files[0][1].decode("utf-8"))
    assert parsed["name"] == "Col #1"


def test_extract_cid():
    assert ipfs.extract_cid({"IpfsHash": "QmABC"}) == "QmABC"
    with pytest.raises(ValueError):
        ipfs.extract_cid({"error": "nope"})


def test_upload_directory_rejects_empty():
    with pytest.raises(ValueError):
        ipfs.upload_directory("jwt", [], "pin")


def test_directory_upload_paths_flat_files_get_folder_prefix():
    files = [("1.png", b"a"), ("2.png", b"b")]
    out = ipfs._directory_upload_paths(files, "my-collection-images")
    paths = [p for p, _ in out]
    assert paths == ["my-collection-images/1.png", "my-collection-images/2.png"]


def test_directory_upload_paths_keeps_existing_common_root():
    files = [("col/1.png", b"a"), ("col/2.png", b"b")]
    out = ipfs._directory_upload_paths(files, "ignored")
    assert [p for p, _ in out] == ["col/1.png", "col/2.png"]


def test_directory_upload_paths_single_file_unchanged():
    files = [("only.png", b"x")]
    assert ipfs._directory_upload_paths(files, "pin") == files


def test_get_pinata_jwt(monkeypatch):
    monkeypatch.delenv("PINATA_JWT", raising=False)
    assert ipfs.get_pinata_jwt() is None
    monkeypatch.setenv("PINATA_JWT", "token123")
    assert ipfs.get_pinata_jwt() == "token123"


def test_platform_pinata_eligible_requires_jwt_and_exempt(monkeypatch):
    monkeypatch.delenv("PINATA_JWT", raising=False)
    assert ipfs.platform_pinata_eligible("0xabc") is False
    monkeypatch.setenv("PINATA_JWT", "jwt")
    monkeypatch.setattr("services.freemium.is_exempt", lambda w: False)
    assert ipfs.platform_pinata_eligible("0xabc") is False
    monkeypatch.setattr("services.freemium.is_exempt", lambda w: True)
    assert ipfs.platform_pinata_eligible("0xabc") is True


def test_resolve_upload_jwt_platform_and_own(monkeypatch):
    monkeypatch.setenv("PINATA_JWT", "platform-jwt")
    monkeypatch.setattr("services.freemium.is_exempt", lambda w: True)
    assert ipfs.resolve_upload_jwt("0x1", "platform") == "platform-jwt"
    assert ipfs.resolve_upload_jwt("0x1", "own", "user-jwt") == "user-jwt"
    assert ipfs.resolve_upload_jwt("0x1", "own", "") is None
    monkeypatch.setattr("services.freemium.is_exempt", lambda w: False)
    assert ipfs.resolve_upload_jwt("0x1", "platform") is None


# ── Metaplex ──────────────────────────────────────────────────────────────────

def test_metaplex_metadata_structure():
    rows = [{"id": 3, "traits": {"head": "crown"}, "prompt": "p"}]
    meta = build_metadata_metaplex(
        rows, "Apes", "APES", "desc", "ipfs://QmX", 750, "SoLAddr111",
    )[0]
    assert meta["name"] == "Apes #3"
    assert meta["symbol"] == "APES"
    assert meta["seller_fee_basis_points"] == 750
    assert meta["image"] == "ipfs://QmX/3.png"
    assert meta["properties"]["files"] == [{"uri": "ipfs://QmX/3.png", "type": "image/png"}]
    assert meta["properties"]["category"] == "image"
    assert meta["properties"]["creators"] == [{"address": "SoLAddr111", "share": 100}]
    assert {"trait_type": "head", "value": "crown"} in meta["attributes"]


def test_metaplex_without_creator():
    meta = build_metadata_metaplex([{"id": 1, "traits": {}}], "X")[0]
    assert "creators" not in meta["properties"]
    assert meta["seller_fee_basis_points"] == 500
