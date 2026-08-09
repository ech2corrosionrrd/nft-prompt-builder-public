import json
import zipfile

import pytest

import collection
from batch import build_metadata, to_csv, trait_distribution


@pytest.fixture(autouse=True)
def tmp_data_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(collection, "CHECKPOINTS_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(collection, "IMAGES_BASE_DIR", tmp_path / "images")
    monkeypatch.setattr(collection, "EXPORTS_DIR", tmp_path / "exports")
    return tmp_path


def _make_checkpoint(name="test-run", target=4):
    combos = [{"head": f"h{i}", "eyes": f"e{i}"} for i in range(target)]
    return collection.create_checkpoint(
        name, target, "gpt-4o-mini", "Midjourney v7",
        {"idea": "ape", "style": "s", "camera": "c", "lighting": "l",
         "background": "b", "quality": "q", "mood": "m"},
        "--ar 1:1", combos,
    )


# ── Чекпоінти ─────────────────────────────────────────────────────────────────

def test_image_size_for_aspect():
    assert collection.image_size_for_aspect("1:1 (Квадрат для NFT)") == "1024x1024"
    assert collection.image_size_for_aspect("16:9 (Пейзаж)") == "1536x1024"
    assert collection.image_size_for_aspect("4:5 (Для мобільних)") == "1024x1536"
    assert collection.image_size_for_aspect("9:16 (Vertical story)") == "1024x1536"
    assert collection.image_size_for_aspect("3:4 (Portrait poster)") == "1024x1536"


def test_create_and_load_checkpoint():
    _make_checkpoint()
    loaded = collection.load_checkpoint("test-run")
    assert loaded is not None
    assert loaded["target"] == 4
    assert loaded["results"] == []
    assert len(loaded["combos"]) == 4
    assert "test-run" in collection.list_checkpoints()


def test_pending_combos_excludes_done():
    cp = _make_checkpoint()
    cp["results"].append({"id": 2, "traits": cp["combos"][1], "prompt": "p", "negative": ""})
    pending = collection.pending_combos(cp)
    assert [tid for tid, _ in pending] == [1, 3, 4]


def test_delete_checkpoint():
    _make_checkpoint()
    collection.delete_checkpoint("test-run")
    assert collection.load_checkpoint("test-run") is None
    assert collection.list_checkpoints() == []


def test_checkpoint_name_sanitized():
    cp = _make_checkpoint(name='bad/name: "x"')
    assert "/" not in cp["name"] and ":" not in cp["name"]
    assert collection.load_checkpoint('bad/name: "x"') is not None


# ── Зображення: вартість і чекпоінт через файлову систему ─────────────────────

def test_image_cost_table():
    assert collection.image_cost("low", "1024x1024") == 0.011
    assert collection.image_cost("high", "1536x1024") == 0.25
    assert collection.image_cost("unknown", "1024x1024") == 0.05


def test_existing_image_ids():
    folder = collection.images_dir("run-x")
    folder.mkdir(parents=True)
    (folder / "1.png").write_bytes(b"fake")
    (folder / "7.png").write_bytes(b"fake")
    (folder / "junk.png").write_bytes(b"fake")
    assert collection.existing_image_ids("run-x") == {1, 7}
    assert collection.existing_image_ids("no-such-run") == set()


# ── Збірний ZIP ───────────────────────────────────────────────────────────────

def test_build_collection_zip_contents():
    results = [
        {"id": 1, "prompt": "p1", "negative": "", "traits": {"head": "a"}, "rarity_score": 1.0},
        {"id": 2, "prompt": "p2", "negative": "", "traits": {"head": "b"}, "rarity_score": 2.0},
    ]
    folder = collection.images_dir("zip-run")
    folder.mkdir(parents=True)
    (folder / "1.png").write_bytes(b"fake-image")

    metadata = build_metadata(results, "Col", "desc", "ipfs://hash")
    zip_path = collection.build_collection_zip("zip-run", results, metadata, to_csv(results))

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert "prompts.csv" in names
        assert "collection.json" in names
        assert "metadata/1.json" in names and "metadata/2.json" in names
        assert "images/1.png" in names
        assert "images/2.png" not in names  # зображення ще не згенероване
        meta1 = json.loads(zf.read("metadata/1.json"))
        assert meta1["name"] == "Col #1"


# ── Розподіл traits ───────────────────────────────────────────────────────────

def test_trait_distribution_expected_vs_actual():
    rows = [
        {"id": 1, "traits": {"head": "rare"}},
        {"id": 2, "traits": {"head": "common"}},
        {"id": 3, "traits": {"head": "common"}},
        {"id": 4, "traits": {"head": "common"}},
    ]
    weighted = {"head": [("rare", 1.0), ("common", 3.0)]}
    table = trait_distribution(rows, weighted)
    rare = next(r for r in table if r["Trait"] == "rare")
    common = next(r for r in table if r["Trait"] == "common")
    assert rare["Очікувано %"] == 25.0
    assert rare["Фактично %"] == 25.0
    assert rare["К-сть"] == 1
    assert common["Фактично %"] == 75.0


def test_trait_distribution_empty_rows():
    table = trait_distribution([], {"head": ["a"]})
    assert table[0]["Фактично %"] == 0.0
    assert table[0]["К-сть"] == 0
