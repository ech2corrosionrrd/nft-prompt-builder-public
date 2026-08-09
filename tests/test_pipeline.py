"""Тести Web3-конвеєра: prompt_service, ai_service, web3_service та network_config."""

import pytest

import network_config
from services import ai_service, prompt_service, web3_service
from services.prompt_service import PromptObject


# ── Етап 1: PromptObject і режими масштабування ───────────────────────────────

def test_prompt_object_render_full():
    p = PromptObject("cyber samurai", "pixel art", ["neon lighting", "close-up"], "--ar 1:1")
    assert p.render() == "cyber samurai, pixel art, neon lighting, close-up --ar 1:1"


def test_prompt_object_render_core_only():
    assert PromptObject("owl").render() == "owl"


def test_prompt_object_skips_empty_parts():
    p = PromptObject("owl", "  ", ["", "  ", "macro"], "")
    assert p.render() == "owl, macro"


def test_build_single_returns_one_dict():
    result = prompt_service.build_single("fox", "anime", ["soft light"], "--v 6")
    assert len(result) == 1
    assert result[0]["prompt"] == "fox, anime, soft light --v 6"
    assert result[0]["core"] == "fox"


def test_build_group_one_prompt_per_style():
    styles = ["pixel art", "3d render", "oil painting"]
    result = prompt_service.build_group("fox", styles, [], "")
    assert len(result) == 3
    assert [r["traits"]["Style"] for r in result] == styles
    assert result[1]["prompt"] == "fox, 3d render"


def test_build_matrix_product_count():
    categories = {
        "Персонаж": ["fox", "owl"],
        "Фон": ["space", "forest", "city"],
        "Аксесуар": ["crown", "sword"],
    }
    result = prompt_service.build_matrix(categories)
    assert len(result) == 2 * 3 * 2
    assert prompt_service.matrix_size(categories) == 12
    # кожна комбінація унікальна і несе traits
    prompts = {r["prompt"] for r in result}
    assert len(prompts) == 12
    assert result[0]["traits"] == {"Персонаж": "fox", "Фон": "space", "Аксесуар": "crown"}


def test_build_matrix_with_style_and_tags():
    result = prompt_service.build_matrix({"X": ["a"], "Y": ["b"]}, style="pixel art", tags="--ar 1:1")
    assert result[0]["prompt"] == "a, b, pixel art --ar 1:1"


def test_build_matrix_empty_categories():
    assert prompt_service.build_matrix({}) == []
    assert prompt_service.matrix_size({"X": []}) == 0


def test_parse_comma_list():
    assert prompt_service.parse_comma_list(" a, b ,, c ") == ["a", "b", "c"]
    assert prompt_service.parse_comma_list("") == []


def test_from_raw_text_entry_point():
    result = prompt_service.from_raw_text("first prompt\n\n  second prompt  \n")
    assert [r["prompt"] for r in result] == ["first prompt", "second prompt"]
    assert result[0]["traits"] == {}


# ── B6: rule-based підказка двигуна з тексту ідеї ─────────────────────────────

def test_suggest_engine_text_logo_to_gpt_image():
    # лого/типографіка/преміум → OpenAI (рендер тексту)
    assert prompt_service.suggest_engine("minimal logo with bold typography") == ai_service.ENGINE_GPT_IMAGE
    assert prompt_service.suggest_engine("преміум бренд, напис на постері") == ai_service.ENGINE_GPT_IMAGE


def test_suggest_engine_art_to_stability():
    assert prompt_service.suggest_engine("watercolor illustration of a fox") == ai_service.ENGINE_STABILITY
    assert prompt_service.suggest_engine("акварельний малюнок кота, аніме") == ai_service.ENGINE_STABILITY


def test_suggest_engine_photo_to_flux():
    assert prompt_service.suggest_engine("cinematic photorealistic portrait, bokeh") == ai_service.ENGINE_FLUX
    assert prompt_service.suggest_engine("реалістичне фото, кінематографічне світло") == ai_service.ENGINE_FLUX


def test_suggest_engine_priority_text_over_art():
    # «watercolor logo» — text-правило має пріоритет над art
    assert prompt_service.suggest_engine("watercolor logo") == ai_service.ENGINE_GPT_IMAGE


def test_suggest_engine_default_when_no_keyword():
    assert prompt_service.suggest_engine("a cat sitting on a chair") == ai_service.ENGINE_GPT_IMAGE
    assert prompt_service.suggest_engine("") == ai_service.ENGINE_GPT_IMAGE
    assert prompt_service.suggest_engine(None) == ai_service.ENGINE_GPT_IMAGE  # type: ignore[arg-type]


def test_suggest_engine_returns_valid_engine():
    # будь-який результат — реальний двигун зі списку
    for idea in ("logo", "watercolor", "photo", "random text"):
        assert prompt_service.suggest_engine(idea) in ai_service.ENGINES


# ── Етап 1: Image-to-Prompt (парсер відповіді vision-моделі) ──────────────────

def test_parse_prompt_formula_full():
    raw = '{"core": "cyber fox", "style": "pixel art", "details": ["neon light", "close-up"], "tags": "--ar 1:1"}'
    result = ai_service.parse_prompt_formula(raw)
    assert result["core"] == "cyber fox"
    assert result["prompt"] == "cyber fox, pixel art, neon light, close-up --ar 1:1"


def test_parse_prompt_formula_partial_defaults():
    result = ai_service.parse_prompt_formula('{"core": "owl"}')
    assert result["prompt"] == "owl"
    assert result["style"] == ""
    assert result["details"] == []


def test_parse_prompt_formula_details_as_string():
    result = ai_service.parse_prompt_formula('{"core": "owl", "details": "soft light"}')
    assert result["details"] == ["soft light"]


def test_parse_prompt_formula_invalid():
    with pytest.raises(ValueError):
        ai_service.parse_prompt_formula("not json")
    with pytest.raises(ValueError):
        ai_service.parse_prompt_formula('["array"]')
    with pytest.raises(ValueError):
        ai_service.parse_prompt_formula('{"style": "no core here"}')


# ── Етап 2: AIService (мультидвигунна генерація, без мережі) ──────────────────

@pytest.fixture
def no_keys(monkeypatch):
    """Сервіс без жодного ключа: чистимо середовище."""
    for var in ("OPENAI_API_KEY", "STABILITY_API_KEY", "REPLICATE_API_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    return ai_service.AIService(openai_key=None, stability_key=None, replicate_token=None)


def test_ai_service_unknown_engine(no_keys):
    with pytest.raises(ValueError, match="Невідомий двигун"):
        no_keys.generate_image("fox", "Midjourney")


def test_ai_service_missing_keys_raise_clear_errors(no_keys):
    for engine in (ai_service.ENGINE_GPT_IMAGE, ai_service.ENGINE_STABILITY):
        with pytest.raises(ai_service.AIServiceError):
            no_keys.generate_image("fox", engine)
    # Вилучений DALL-E 3 зводиться до gpt-image-1 → теж падає без OpenAI-ключа.
    with pytest.raises(ai_service.AIServiceError):
        no_keys.generate_image("fox", ai_service.ENGINE_DALLE3)
    with pytest.raises(ai_service.AIServiceError):
        no_keys.generate_image("fox", ai_service.ENGINE_FLUX)


def test_ai_service_engine_status(no_keys):
    status = no_keys.engine_status()
    assert set(status) == set(ai_service.ENGINES)
    assert all(status[e] for e in ai_service.ENGINES)  # без ключів — усі недоступні
    ready = ai_service.AIService(openai_key="sk-test", stability_key="st-test", replicate_token=None)
    assert ready.engine_status()[ai_service.ENGINE_GPT_IMAGE] == ""
    assert ready.engine_status()[ai_service.ENGINE_STABILITY] == ""


def test_normalize_engine_retires_dalle():
    """Вилучений DALL-E 2/3 → gpt-image-1; доступні й невідомі — без змін."""
    assert ai_service.normalize_engine(ai_service.ENGINE_DALLE3) == ai_service.ENGINE_GPT_IMAGE
    assert ai_service.normalize_engine("dall-e-3") == ai_service.ENGINE_GPT_IMAGE
    assert ai_service.normalize_engine(ai_service.ENGINE_STABILITY) == ai_service.ENGINE_STABILITY
    assert ai_service.normalize_engine("Midjourney") == "Midjourney"  # невідомий не маскуємо
    # DALL-E більше не серед доступних двигунів.
    assert ai_service.ENGINE_DALLE3 not in ai_service.ENGINES


def test_size_mapping():
    assert ai_service.dalle_size(1024, 1024) == "1024x1024"
    assert ai_service.dalle_size(1536, 1024) == "1792x1024"
    assert ai_service.dalle_size(1024, 1536) == "1024x1792"
    assert ai_service.gpt_image_size(1536, 1024) == "1536x1024"
    assert ai_service.closest_aspect(1024, 1024) == "1:1"
    assert ai_service.closest_aspect(1536, 1024) == "16:9"
    assert ai_service.closest_aspect(1024, 1536) == "9:16"


def test_estimate_cost_positive_for_all_engines():
    for engine in ai_service.ENGINES:
        for orientation in ai_service.SIZE_PRESETS:
            assert ai_service.estimate_cost(engine, orientation) > 0


def test_friendly_error_classifies():
    assert "ліміти" in ai_service._friendly_error("X", RuntimeError("429 rate limit exceeded"))
    assert "недійсний" in ai_service._friendly_error("X", RuntimeError("401 Unauthorized"))
    assert "X: boom" == ai_service._friendly_error("X", RuntimeError("boom"))


# ── Етап 3: трансформація метаданих під стандарт блокчейну ────────────────────

def test_erc721_metadata_structure():
    meta = web3_service.build_erc721_metadata(
        "Token #1", "desc", "ipfs://Qm123", {"Style": "pixel art"},
    )
    assert meta == {
        "name": "Token #1",
        "description": "desc",
        "image": "ipfs://Qm123",
        "attributes": [{"trait_type": "Style", "value": "pixel art"}],
    }
    assert "symbol" not in meta  # ERC-721 ≠ Metaplex


def test_erc721_metadata_translates_ua_trait_keys():
    meta = web3_service.build_erc721_metadata(
        "Token #1", "desc", "ipfs://Qm123", {"Варіанти фону": "space"},
    )
    assert meta["attributes"][0]["trait_type"] == "Background"


def test_metaplex_metadata_structure_and_limits():
    meta = web3_service.build_metaplex_metadata(
        "X" * 50, "SYMBOLTOOLONG", "desc", "ipfs://Qm123",
        {"Фон": "space"}, royalty_bps=750, creator="So1anaAddr",
    )
    assert len(meta["name"]) == web3_service.METAPLEX_NAME_LIMIT
    assert len(meta["symbol"]) == web3_service.METAPLEX_SYMBOL_LIMIT
    assert meta["seller_fee_basis_points"] == 750
    assert meta["properties"]["files"] == [{"uri": "ipfs://Qm123", "type": "image/png"}]
    assert meta["properties"]["creators"] == [{"address": "So1anaAddr", "share": 100}]


def test_metaplex_metadata_without_creator():
    meta = web3_service.build_metaplex_metadata("N", "S", "d", "ipfs://x", {})
    assert "creators" not in meta["properties"]


def test_build_token_metadata_dispatch():
    item = {"name": "T", "description": "d", "image_uri": "ipfs://x", "traits": {"A": "b"}}
    evm = web3_service.build_token_metadata("base", item)
    sol = web3_service.build_token_metadata("solana", item, symbol="S")
    assert "seller_fee_basis_points" not in evm
    assert sol["symbol"] == "S"
    assert evm["attributes"] == sol["attributes"]


# ── Етап 3: Prompt-Lock (формула промпту як незмінний атрибут NFT) ────────────

def test_prompt_lock_in_erc721():
    meta = web3_service.build_erc721_metadata(
        "T", "d", "ipfs://x", {"Style": "pixel"}, prompt="cyber fox, pixel art",
    )
    assert {"trait_type": web3_service.PROMPT_LOCK_TRAIT, "value": "cyber fox, pixel art"} in meta["attributes"]


def test_prompt_lock_in_metaplex():
    meta = web3_service.build_metaplex_metadata(
        "T", "S", "d", "ipfs://x", {}, prompt="owl alchemist",
    )
    assert {"trait_type": web3_service.PROMPT_LOCK_TRAIT, "value": "owl alchemist"} in meta["attributes"]


def test_prompt_lock_omitted_when_empty():
    meta = web3_service.build_erc721_metadata("T", "d", "ipfs://x", {"A": "b"}, prompt="  ")
    assert all(a["trait_type"] != web3_service.PROMPT_LOCK_TRAIT for a in meta["attributes"])


def test_build_token_metadata_carries_prompt_lock():
    item = {"name": "T", "description": "d", "image_uri": "ipfs://x", "traits": {}, "prompt": "fox, anime"}
    for chain in ("base", "solana"):
        meta = web3_service.build_token_metadata(chain, item)
        assert {"trait_type": web3_service.PROMPT_LOCK_TRAIT, "value": "fox, anime"} in meta["attributes"]


# ── Етап 3: Crossmint payload ─────────────────────────────────────────────────

def test_crossmint_payload_prefixes_chain():
    payload = web3_service.build_crossmint_payload("0xabc", "base", {"name": "T"})
    assert payload["recipient"] == "base:0xabc"
    assert payload["metadata"] == {"name": "T"}


def test_crossmint_payload_keeps_explicit_recipient():
    payload = web3_service.build_crossmint_payload("email:u@x.com:base", "solana", {})
    assert payload["recipient"] == "email:u@x.com:base"


def test_thirdweb_requires_web3_package():
    if web3_service._WEB3_AVAILABLE:
        pytest.skip("web3 встановлено — перевірка fallback не потрібна")
    with pytest.raises(ImportError):
        web3_service.mint_thirdweb("0x" + "1" * 64, "0x" + "2" * 40, "0x" + "3" * 40, "ipfs://x")
    with pytest.raises(ImportError):
        web3_service.mint_thirdweb_batch("0x" + "1" * 64, "0x" + "2" * 40, "0x" + "3" * 40, ["ipfs://x"])


# ── network_config: Web3-Origin та temp_assets ────────────────────────────────

def test_web3_headers_default_origin(monkeypatch):
    monkeypatch.delenv("W3IR_ORIGIN", raising=False)
    headers = network_config.web3_headers()
    assert headers["Origin"] == "https://w3ir.io"
    assert headers["Referer"] == "https://w3ir.io/"


def test_web3_headers_env_override_and_merge(monkeypatch):
    monkeypatch.setenv("W3IR_ORIGIN", "https://ai.w3ir.io/")
    headers = network_config.web3_headers({"X-API-KEY": "k"})
    assert headers["Origin"] == "https://ai.w3ir.io"
    assert headers["Referer"] == "https://ai.w3ir.io/"
    assert headers["X-API-KEY"] == "k"


def test_get_app_url_default_and_override(monkeypatch):
    monkeypatch.delenv("W3IR_APP_URL", raising=False)
    assert network_config.get_app_url() == "https://ai.w3ir.io"
    monkeypatch.setenv("W3IR_APP_URL", "https://builder.w3ir.io/")
    assert network_config.get_app_url() == "https://builder.w3ir.io"


def test_publish_static_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(network_config, "TEMP_ASSETS_DIR", tmp_path / "temp_assets")
    monkeypatch.setattr(network_config, "STATIC_DIR", tmp_path / "static")
    monkeypatch.delenv("W3IR_APP_URL", raising=False)

    src = network_config.save_temp_asset(b"img-bytes")
    url = network_config.publish_static_asset(src)
    assert url == f"https://ai.w3ir.io/app/static/{src.name}"
    copy = tmp_path / "static" / src.name
    assert copy.read_bytes() == b"img-bytes"

    # повторна публікація ідемпотентна, оригінал лишається в temp_assets/
    assert network_config.publish_static_asset(src) == url
    assert src.exists()

    assert network_config.cleanup_static_assets() == 1
    assert not copy.exists()
    with pytest.raises(FileNotFoundError):
        network_config.publish_static_asset(tmp_path / "missing.png")


def test_temp_assets_save_read_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(network_config, "TEMP_ASSETS_DIR", tmp_path / "temp_assets")
    p1 = network_config.save_temp_asset(b"png-data-1")
    p2 = network_config.save_temp_asset(b"jpg-data-2", suffix=".jpg")
    assert p1.exists() and p1.suffix == ".png" and p1.name != p2.name
    assert p2.suffix == ".jpg"
    assert network_config.read_asset(p1) == b"png-data-1"

    # cleanup_files чистить лише вміст temp_assets/, чужі шляхи не чіпає
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"x")
    removed = network_config.cleanup_files([p1, outside])
    assert removed == 1
    assert not p1.exists() and outside.exists() and p2.exists()

    assert network_config.cleanup_temp_assets() == 1  # лишався p2
    assert not p2.exists()


def test_read_asset_allows_workspace_rejects_outside(tmp_path, monkeypatch):
    # P0-фікс: pipeline пише в data/workspace/.../assets/ — read_asset мусить
    # дозволяти ці шляхи (раніше падав ValueError → traceback в Export Center).
    temp = tmp_path / "temp_assets"
    data = tmp_path / "data"
    monkeypatch.setattr(network_config, "TEMP_ASSETS_DIR", temp)
    monkeypatch.setattr(network_config, "_DATA_DIR", data)

    ws_asset = data / "workspace" / "w" / "proj" / "assets" / "0.png"
    ws_asset.parent.mkdir(parents=True)
    ws_asset.write_bytes(b"pipeline-png")
    assert network_config.read_asset(ws_asset) == b"pipeline-png"

    temp.mkdir(parents=True)
    t_asset = network_config.save_temp_asset(b"temp-png")
    assert network_config.read_asset(t_asset) == b"temp-png"

    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"nope")
    with pytest.raises(ValueError):
        network_config.read_asset(outside)


def test_export_center_swallows_disallowed_asset_path(tmp_path):
    # P0-фікс шар 2: недозволений/недоступний шлях не валить Export Center —
    # актив лишається без байтів, валідація позначить «missing image».
    from ui import export_center

    bad = tmp_path / "outside.png"
    bad.write_bytes(b"x" * 100)
    out = export_center._assets_with_images([{"name": "a", "path": str(bad)}])
    assert out and not out[0].get("image_bytes")


def test_thirdweb_batch_encodes_multicall():
    if not web3_service._WEB3_AVAILABLE:
        pytest.skip("web3 не встановлено")
    from web3 import Web3
    w3 = Web3()
    contract = w3.eth.contract(
        address="0x" + "2" * 40, abi=web3_service.THIRDWEB_MINT_ABI,
    )
    calls = web3_service.encode_mint_calls(contract, "0x" + "3" * 40, ["ipfs://a", "ipfs://b"])
    assert len(calls) == 2
    assert all(isinstance(c, bytes) and len(c) > 4 for c in calls)
    assert calls[0] != calls[1]  # різні URI → різні calldata
