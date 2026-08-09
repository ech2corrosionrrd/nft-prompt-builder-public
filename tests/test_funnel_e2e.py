"""Наскрізний headless-тест воронки білдера: промпт → генерація → approve → export ZIP.

Валідує **відсутність глухих кутів**: кожен етап, отримавши контракт попереднього
(`state.pipeline_state`), рендериться без винятку й дає РЕАЛЬНИЙ контрол переходу далі,
а термінальна подія продукту (export-бандл) досяжна й видає валідний ZIP.

Генерація (мережа+білінг) інжектиться як готовий результат (`PIPELINE_IMAGES`) — сама
генерація покрита `test_pipeline`; кнопка `pl2_run` навмисно заблокована без API-ключа,
тож тут перевіряємо ШВИ воронки, а не двигун. Усі інші переходи — справжні кліки UI.
"""

import base64
import io
import zipfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import network_config
from services import payment_service
from state.pipeline_state import (
    APPROVED_CONTENT,
    GENERATED_PROMPTS,
    MINT_ASSETS,
    PIPELINE_IMAGES,
)
from ui.workflow_guide import PIPELINE_STAGE_KEY

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Ізоляція БД: build_zip тригерить record_funnel_event — не писати в реальну users.db."""
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr("services.project_service.WORKSPACE_ROOT", tmp_path / "workspace")

# Мінімальний валідний 1×1 PNG — справжні байти, щоб export прочитав asset.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _png_path(monkeypatch, tmp_path) -> str:
    """Зберігає PNG у пісочницю temp-asset (read_asset пускає лише з TEMP_ASSETS_DIR)."""
    monkeypatch.setattr(network_config, "TEMP_ASSETS_DIR", tmp_path / "temp_assets")
    return str(network_config.save_temp_asset(_PNG, suffix=".png"))


def _seed_through_generation(at: AppTest, img_path: str) -> None:
    """Стан до Етапу 2 включно: гаманець (billing-гейт) + промпт (вихід Етапу 1) +
    готова генерація + позначка approve. Активний етап одразу «images» (Зображення)."""
    at.session_state["welcome_seen"] = True
    at.session_state["wallet_address"] = "0x" + "ab" * 20  # валідний EVM-hex
    at.session_state[GENERATED_PROMPTS] = [
        {"prompt": "a neon owl, cyberpunk", "core": "owl", "style": "cyberpunk",
         "details": "", "tags": [], "traits": {"Background": "Neon"}},
    ]
    at.session_state[PIPELINE_IMAGES] = [
        {"prompt": "a neon owl, cyberpunk", "path": img_path, "engine": "gpt-image-1",
         "traits": {"Background": "Neon"}, "filename": "0.png"},
    ]
    at.session_state["pl2_approve_0"] = True
    at.session_state["pl2_rating_0"] = 5
    at.session_state[PIPELINE_STAGE_KEY] = "images"  # лінійний майстер → одразу Етап 2


def test_funnel_walk_to_export(monkeypatch, tmp_path):
    """welcome→промпт→(генерація)→approve→take→build → валідний ZIP, без глухих кутів."""
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")  # без SIWE-гарду → повний рендер
    img_path = _png_path(monkeypatch, tmp_path)

    at = AppTest.from_file(APP, default_timeout=120)
    _seed_through_generation(at, img_path)
    at.run()
    assert not at.exception, at.exception
    assert any(getattr(b, "key", None) == "pl2_approve_btn" for b in at.button), \
        "Етап 2 (Зображення) не відрендерив кнопку approve — етап заблоковано/не досяжний"

    # Етап 2 → 3: approve наповнює APPROVED_CONTENT + MINT_ASSETS і ОДРАЗУ веде на
    # Export — pl2_approve_btn робить st.rerun() у тому ж циклі (фікс deferred-flip).
    at.button(key="pl2_approve_btn").click().run()
    assert not at.exception, at.exception
    assert at.session_state[APPROVED_CONTENT], \
        "approve не наповнив APPROVED_CONTENT — глухий кут Етап2→3"
    mint_assets = list(at.session_state[MINT_ASSETS])
    assert mint_assets, "approve не синхронізував MINT_ASSETS — зайвий крок take_approved"
    assert at.session_state[PIPELINE_STAGE_KEY] == "mint", \
        "approve не перейшов на Export у тому ж циклі кліку (deferred-flip баг)"

    # Термінальна подія (Export Center) — свіжий AppTest на mint із чергою з approve.
    # AppTest накопичує дерево віджетів при st.rerun()+зміні етапу в одному циклі, тож
    # фазу ZIP будуємо на чистому дереві (у браузері st.rerun() такого не дає).
    at2 = AppTest.from_file(APP, default_timeout=120)
    at2.session_state["welcome_seen"] = True
    at2.session_state["wallet_address"] = "0x" + "ab" * 20
    at2.session_state[APPROVED_CONTENT] = list(at.session_state[APPROVED_CONTENT])
    at2.session_state[MINT_ASSETS] = mint_assets
    at2.session_state[PIPELINE_STAGE_KEY] = "mint"
    at2.run()
    assert not at2.exception, at2.exception
    assert any(getattr(b, "key", None) == "ec_build_zip" for b in at2.button), \
        "Етап 3 (Експорт) не досяжний із чергою assets — глухий кут"

    at2.text_input(key="pl3_coll_name").set_value("Funnel Test").run()
    at2.session_state["ec_platform"] = "opensea"
    at2.button(key="ec_build_zip").click().run()
    assert not at2.exception, at2.exception

    zip_bytes = at2.session_state["ec_zip_bytes"] if "ec_zip_bytes" in at2.session_state else None
    assert zip_bytes, "build_zip не створив ZIP — термінальна подія воронки недосяжна"

    # ZIP валідний і містить зображення.
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
    assert any(n.lower().endswith((".png", ".jpg", ".jpeg")) for n in names), \
        f"у ZIP немає зображення: {names}"

    # Контрол завантаження досяжний: stage3 рендерить download_button рівно коли
    # є pl3_zip_bytes (вже стверджено), а ім'я файлу задається в тому ж блоці.
    assert at2.session_state["ec_zip_name"].endswith(".zip"), \
        "ім'я ZIP не задане — блок завантаження бандла недосяжний"


def test_export_stage_open_with_wallet_upload_path(monkeypatch):
    """З гаманцем Export доступний без approve — upload на етапі; ZIP лише з assets."""
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["welcome_seen"] = True
    at.session_state["wallet_address"] = "0x" + "ab" * 20
    at.session_state[PIPELINE_STAGE_KEY] = "mint"
    at.run()
    assert not at.exception, at.exception
    keys = {getattr(b, "key", None) for b in at.button}
    assert "ec_build_zip" not in keys, \
        "ZIP не повинен бути доступний без черги assets"
    # Gate Export (без гаманця) не показується — етап відкритий для upload.
    gate_msgs = [w.value for w in at.warning if "🔒" in w.value or "locked" in w.value.lower()]
    assert not gate_msgs, f"неочікуваний gate на Export: {gate_msgs}"


def test_curator_bulk_then_save_navigates_immediately(monkeypatch, tmp_path):
    """Grid-куратор (≥2 кадри): «Позначити всі» → «Save & Export» одразу веде на mint.

    Регресія: раніше pl2_approve_btn ставив PENDING-етап без st.rerun(), тож перехід
    відкладався до НАСТУПНОГО кліку — і той клік оброблявся вже на іншому етапі
    (зниклий віджет → виняток + «стрибок у інше меню»). Тут стверджуємо, що етап
    стає 'mint' у ТОМУ Ж циклі кліку, без винятку.
    """
    monkeypatch.setenv("AUTH_GATEWAY_ENFORCE", "0")
    p1, p2 = _png_path(monkeypatch, tmp_path), _png_path(monkeypatch, tmp_path)
    at = AppTest.from_file(APP, default_timeout=120)
    at.session_state["welcome_seen"] = True
    at.session_state["wallet_address"] = "0x" + "ab" * 20
    at.session_state[GENERATED_PROMPTS] = [
        {"prompt": "owl", "core": "owl", "style": "", "details": "", "tags": [], "traits": {}},
    ]
    at.session_state[PIPELINE_IMAGES] = [
        {"prompt": "owl 0", "path": p1, "engine": "gpt-image-1", "traits": {}, "filename": "0.png"},
        {"prompt": "owl 1", "path": p2, "engine": "gpt-image-1", "traits": {}, "filename": "1.png"},
    ]
    at.session_state[PIPELINE_STAGE_KEY] = "images"
    at.run()
    assert not at.exception, at.exception

    # «Позначити всі на екрані» — позначає видимі кадри (rerun усередині).
    at.button(key="pl2_bulk_visible_btn").click().run()
    assert not at.exception, at.exception
    assert at.session_state[PIPELINE_STAGE_KEY] == "images", \
        "перший клік «Позначити всі» не повинен змінювати етап (toggle pending)"
    assert at.session_state["pl2_approve_0"] and at.session_state["pl2_approve_1"], \
        "bulk visible не позначив кадри"

    # «Save & Export» — має перейти на mint у ЦЬОМУ ж циклі (не на наступному кліку).
    at.button(key="pl2_approve_btn").click().run()
    assert not at.exception, at.exception
    stage = at.session_state[PIPELINE_STAGE_KEY] if PIPELINE_STAGE_KEY in at.session_state else None
    assert stage == "mint", f"перехід на Export відкладено (deferred-flip баг): етап={stage}"
    assert at.session_state[APPROVED_CONTENT], "approve не наповнив APPROVED_CONTENT"
