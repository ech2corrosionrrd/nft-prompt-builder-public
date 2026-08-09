"""Структура промпту колекції: BASE OBJECT, порядок частин, фіксатори серії.

Що саме тут захищається (і чому це не косметика):

* **BASE OBJECT присутній завжди.** Раніше базовий об'єкт підставлявся як
  ЗНАЧЕННЯ осі «Варіанти персонажа» і лише коли та вісь порожня — тож у
  landscape/event-шаблонах, де вісь зайнята сценами й tier-ами, він зникав з
  промпту. `Event Badge Series` генерував «genesis founder tier, circular enamel
  medallion…», ніде не згадуючи, що це Web3-бейдж: колекція втрачала спільне ядро.
* **Порядок частин.** У диффузійних моделей вага токенів спадає зліва направо,
  тож фіксована рамка серії (об'єкт + стиль) має випереджати змінні trait-и.
  Промпт, що починається з «light blue gradient», віддає фону більше уваги, ніж
  самому персонажу.
* **Фіксатори консистентності.** Кожен виклик моделі незалежний, тож без
  спільного хвоста композиція й масштаб «пливуть» від айтема до айтема, і 25
  зображень виглядають як 25 випадкових картинок, а не як одна серія.
"""

from services import prompt_service
from services import template_pipeline as tp
from services.prompt_quality import consistency_for_archetype
from templates import COLLECTION_TEMPLATES

# Архетипи, де базовий об'єкт раніше зникав: вісь «персонажа» зайнята шаблоном.
LOST_BASE_TEMPLATES = ("Atmospheric Worlds", "Event Badge Series")


def test_base_object_precedes_traits_and_style():
    """Фіксована рамка (об'єкт + стиль) стоїть перед змінними trait-ами."""
    out = prompt_service.build_matrix(
        {"Фон": ["pink background"], "Аксесуар": ["gold crown"]},
        style="flat vector illustration",
        details=["front-facing view"],
        tags="--ar 1:1",
        base="cartoon fox head",
        consistency="centered composition",
    )
    prompt = out[0]["prompt"]
    assert prompt.startswith("cartoon fox head, flat vector illustration, ")
    assert prompt.index("cartoon fox head") < prompt.index("gold crown")
    assert prompt.index("flat vector illustration") < prompt.index("pink background")
    assert prompt.index("front-facing view") < prompt.index("centered composition")
    assert prompt.endswith("--ar 1:1")


def test_core_stays_first_without_base():
    """Без base порядок старий (core → style): core там і є головним об'єктом.

    Це стосується «Сингла», сирого тексту й Image-to-Prompt — інакше зворотний
    інжиніринг віддавав би «pixel art, cyber fox» замість «cyber fox, pixel art».
    """
    out = prompt_service.build_single("cyber fox", "pixel art", ["neon light"], "--ar 1:1")
    assert out[0]["prompt"] == "cyber fox, pixel art, neon light --ar 1:1"


def test_base_object_never_becomes_a_matrix_axis():
    """Базовий об'єкт не множиться на осі — розмір колекції лишається 5x5=25."""
    cats = {"Сцена": ["a", "b", "c", "d", "e"], "Настрій": ["1", "2", "3", "4", "5"]}
    out = prompt_service.build_matrix(cats, base="epic landscape vista")
    assert len(out) == 25
    assert all(p["prompt"].startswith("epic landscape vista, ") for p in out)
    # base не потрапляє в traits — інакше він осів би в метаданих як ознака.
    assert all("epic landscape vista" not in p["traits"].values() for p in out)


def test_every_template_carries_base_object_into_prompt():
    """Жоден шаблон не губить базовий об'єкт — саме це раніше й ламалось."""
    for name, tpl in COLLECTION_TEMPLATES.items():
        base = tp.base_object_from_template(tpl)
        assert base, f"{name}: немає ані base_object, ані idea"
        first = tp.prompts_from_template(tpl)[0]["prompt"]
        assert first.startswith(base), f"{name}: промпт не починається з базового об'єкта"


def test_templates_that_used_to_lose_base_object():
    """Іменний регрес-гард на два шаблони, де вісь «персонажа» зайнята."""
    for name in LOST_BASE_TEMPLATES:
        tpl = COLLECTION_TEMPLATES[name]
        cats = tp.matrix_categories_from_template(tpl)
        assert cats.get("Варіанти персонажа"), f"{name}: вісь персонажа має бути зайнята"
        assert tp.base_object_from_template(tpl) in tp.prompts_from_template(tpl)[0]["prompt"]


def test_every_template_carries_consistency_fixators():
    """Хвіст фіксаторів однаковий у межах шаблону — це і робить набір серією."""
    for name, tpl in COLLECTION_TEMPLATES.items():
        fixators = tp.consistency_from_template(tpl)
        assert fixators, f"{name}: немає фіксаторів консистентності"
        prompts = tp.prompts_from_template(tpl)
        assert all(fixators in p["prompt"] for p in prompts[:8]), name


def test_consistency_defaults_follow_archetype():
    """Кожен архетип має власні фіксатори — рамка серії різна за природою кадру."""
    assert "square format" in consistency_for_archetype("pfp")
    assert "horizon" in consistency_for_archetype("landscape")
    assert "diameter" in consistency_for_archetype("event_badge")


def test_unknown_archetype_gets_default_consistency():
    from services.prompt_quality import DEFAULT_CONSISTENCY

    assert consistency_for_archetype("no-such-archetype") == DEFAULT_CONSISTENCY
    assert consistency_for_archetype("") == DEFAULT_CONSISTENCY


def test_explicit_consistency_field_wins_over_archetype_default():
    tpl = {"idea": "x", "archetype": "pfp", "consistency": "my own fixators"}
    assert tp.consistency_from_template(tpl) == "my own fixators"


def test_explicit_base_object_field_wins_over_idea():
    tpl = {"idea": "short label", "base_object": "detailed base object description"}
    assert tp.base_object_from_template(tpl) == "detailed base object description"


# ── Пошарова збірка: айтем несе всі шари, а не один ──────────────────────────

def test_layered_item_carries_every_trait_category():
    """Кожен айтем PFP отримує по значенню з КОЖНОЇ категорії, а не одне з усіх.

    Матриця зводить шість trait-категорій до трьох осей, тож значення однієї осі
    підмінюють одне одного: мавпа виходила з короною АБО окулярами АБО худі.
    Rarity рахується за співпадінням кількох ознак в одному айтемі, тож без
    повного набору вона беззмістовна.
    """
    tpl = COLLECTION_TEMPLATES["BAYC-style PFP"]
    prompts = tp.prompts_from_template(tpl)
    expected = set(tpl["traits"])
    for item in prompts[:20]:
        assert set(item["traits"]) == expected, item["traits"]
        assert all(v for v in item["traits"].values())


def test_layered_keeps_the_item_count_matrix_would_give():
    """Пошарова збірка міняє повноту айтема, а не обсяг колекції."""
    for name in ("BAYC-style PFP", "Flat Vector Mascots", "Chibi Champs"):
        tpl = COLLECTION_TEMPLATES[name]
        cats = tp.matrix_categories_from_template(tpl)
        assert len(tp.prompts_from_template(tpl)) == prompt_service.matrix_size(cats)


def test_layered_output_is_deterministic():
    """Той самий шаблон → той самий набір: Streamlit перевиконує скрипт постійно."""
    tpl = COLLECTION_TEMPLATES["BAYC-style PFP"]
    first = [p["traits"] for p in tp.prompts_from_template(tpl)]
    second = [p["traits"] for p in tp.prompts_from_template(tpl)]
    assert first == second


def test_two_axis_templates_still_use_matrix():
    """Де зливати нічого (1-2 категорії), лишається матриця — повний добуток."""
    tpl = COLLECTION_TEMPLATES["Line Art Monograms"]
    assert len(tpl["traits"]) == 2
    prompts = tp.prompts_from_template(tpl)
    assert len(prompts) == 25
    assert len({p["prompt"] for p in prompts}) == 25  # добуток без повторів


def test_build_layered_puts_traits_into_prompt_and_metadata():
    combos = [{"Head": "top hat", "Eyes": "monocle", "Background": "pink"}]
    out = prompt_service.build_layered(
        combos, style="flat vector", base="a fox", consistency="centered",
    )
    assert out[0]["prompt"] == "a fox, flat vector, top hat, monocle, pink, centered"
    assert out[0]["traits"] == combos[0]


def test_prompt_stays_within_encoder_budget():
    """Стеля довжини: хвіст промпту — саме фіксатори, і саме він обрізається першим.

    Текстові енкодери мають скінченне вікно (у CLIP-моделей — коротке). Коли
    промпт переростає його, модель мовчки відкидає кінець, тобто гине рамка
    консистентності — рівно те, заради чого вона додана. Гард не крихкий: ловить
    роздування вдвічі, а не кожне зайве слово.
    """
    for name, tpl in COLLECTION_TEMPLATES.items():
        words = len(tp.prompts_from_template(tpl)[0]["prompt"].split())
        assert words <= 90, f"{name}: промпт роздувся до {words} слів"


def test_base_object_does_not_duplicate_its_fixators():
    """BASE OBJECT не повторює рамкові слова — дублі відбирають вагу в об'єкта."""
    for name, tpl in COLLECTION_TEMPLATES.items():
        base = tp.base_object_from_template(tpl).lower()
        fixators = tp.consistency_from_template(tpl).lower()
        for marker in ("centered", "square format", "across all variations"):
            assert not (marker in base and marker in fixators), \
                f"{name}: «{marker}» і в базовому об'єкті, і у фіксаторах"


def test_fixed_angle_precedes_atmosphere_details():
    """Ракурс (FIXED ANGLE) — частина рамки, тож іде перед світлом і настроєм."""
    tpl = COLLECTION_TEMPLATES["BAYC-style PFP"]
    prompt = tp.prompts_from_template(tpl)[0]["prompt"]
    camera = "Close-up PFP"
    lighting = "Soft Studio Light"
    assert prompt.index(camera) < prompt.index(lighting)
