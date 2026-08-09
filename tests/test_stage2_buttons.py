"""Headless AppTest для кнопкових хендлерів Етапу 2 (Генератор конвеєра).

Закриває сліпу зону headless-smoke: обробник кнопки виконується ЛИШЕ на клік,
тож вільна змінна `wallet`, ужита до її визначення в `render()`, проходила повз
рендер-тести й валила «Очистити батч» NameError у проді (fix 87d63ba). Це аналог
test_batch_tab_generate_succeeds (Batch→build_tech_params), але для конвеєра: той
самий клас регресій, що двічі виліз через клікові хендлери.

Прийом: PIPELINE_IMAGES з НЕіснуючими шляхами — `existing_n > 0` показує кнопку
«Очистити батч», а курар-панель відсіює всі (filter_images пропускає неіснуючі
path) і робить ранній return, не торкаючись st.image. Гаманець заданий (truthy),
щоб реально пройти гілку `autosave(wallet)`, де й жив NameError.
"""

from streamlit.testing.v1 import AppTest

from services import payment_service, project_service
from state.pipeline_state import GENERATED_PROMPTS, PIPELINE_IMAGES
from ui.billing_ui import WALLET_KEY

CLEAR_KEY = "pl2_clear_batch"


def _prompt(text: str) -> dict:
    return {"prompt": text, "core": text, "style": "anime", "details": "", "tags": [], "traits": {}}


def _image(text: str, path: str) -> dict:
    # path навмисно неіснуючий → filter_images відсіює, грід куратора не рендериться.
    return {"prompt": text, "path": path, "traits": {}}


def _stage2(monkeypatch, tmp_path):
    """Рендерить ui.stage2_generator.render() з непорожнім батчем і підключеним гаманцем."""
    monkeypatch.setenv("UI_DEFAULT_LANG", "en")
    monkeypatch.setattr(payment_service, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(project_service, "WORKSPACE_ROOT", tmp_path / "workspace")

    def script():
        from ui import stage2_generator
        stage2_generator.render(api_key="sk-test")

    at = AppTest.from_function(script, default_timeout=60)
    at.session_state[WALLET_KEY] = "0x" + "ab" * 20  # truthy → гілка autosave(wallet)
    at.session_state[GENERATED_PROMPTS] = [_prompt("neon cat"), _prompt("neon dog")]
    at.session_state[PIPELINE_IMAGES] = [
        _image("neon cat", str(tmp_path / "nope1.png")),
        _image("neon dog", str(tmp_path / "nope2.png")),
    ]
    at.run()
    return at


def _clear_button(at):
    return next((b for b in at.button if b.key == CLEAR_KEY), None)


def test_stage2_renders_clear_batch_button(monkeypatch, tmp_path):
    """Непорожній батч → кнопка «Очистити батч» рендериться без винятку."""
    at = _stage2(monkeypatch, tmp_path)
    assert not at.exception, at.exception
    assert _clear_button(at) is not None, "Кнопка pl2_clear_batch не зрендерилась"


def test_stage2_clear_batch_handler_succeeds(monkeypatch, tmp_path):
    """Регресія NameError: клік «Очистити батч» виконує autosave(wallet) і чистить батч.

    Зі старим кодом (`wallet` ужитий до визначення) цей клік валив NameError на
    обчисленні `if wallet` — рендер-тести його не ловили. Перевіряємо САМЕ успіх
    (PIPELINE_IMAGES спорожнів), а не лише відсутність винятку.
    """
    at = _stage2(monkeypatch, tmp_path)
    btn = _clear_button(at)
    assert btn is not None
    btn.click().run()
    assert not at.exception, at.exception
    assert at.session_state[PIPELINE_IMAGES] == [], "Батч не очищено (хендлер не відпрацював?)"
