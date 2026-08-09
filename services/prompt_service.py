"""Етап 1 конвеєра: об'єкт промпту та три режими масштабування.

Чисті функції без Streamlit — тестуються без UI.
Режими: «Сингл» (1 промпт), «Специфічна група» (1 об'єкт × N стилів),
«Генеративна колекція» (матриця ознак через itertools.product).
"""

import itertools
import math
from dataclasses import dataclass, field


@dataclass
class PromptObject:
    """Логічна структура промпту: база → об'єкт → стиль → деталізація → фіксатори → теги.

    `base` і `consistency` — рамка серії (обидві порожні за замовчуванням, тож
    старі виклики рендеряться як раніше):

    * **base** — BASE OBJECT: те, що НЕ змінюється між айтемами колекції (вид
      істоти/предмета, поза, ракурс, пропорції). Стоїть першим свідомо: у
      диффузійних моделей вага токенів спадає зліва направо, тож базовий об'єкт
      має отримати її раніше за змінні trait-и. Саме це дає впізнаваність серії.
    * **consistency** — технічні фіксатори («centered composition, consistent
      proportions and lighting across all variations»). Хвіст промпту, однаковий
      для всіх айтемів: без нього набір виглядає як випадкові картинки, а не як
      одна колекція.

    Порядок частин — не косметика, а те, чим серія тримається купи; міняти його
    треба свідомо (див. tests/test_prompt_structure.py).
    """

    core: str                                          # змінна частина: trait-и айтема
    style: str = ""                                    # стиль
    details: list[str] = field(default_factory=list)   # світло, камера, кольори
    tags: str = ""                                     # технічні параметри для ШІ
    traits: dict[str, str] = field(default_factory=dict)
    # Якість (ПЛАН_ЯКОСТІ.md § Q1.5): negative-prompt, seed для відтворюваності
    # та історія LLM-полірування зберігаються разом із промптом.
    negative: str = ""                                 # negative-prompt
    seed: int | None = None                            # seed (reproducibility)
    polish_history: list[str] = field(default_factory=list)  # сліди polish/правок
    version: int = 1                                    # версія промпту (Q2.6)
    base: str = ""                                     # BASE OBJECT — фіксоване ядро серії
    consistency: str = ""                              # технічні фіксатори консистентності

    def render(self) -> str:
        """Складає промпт; головний об'єкт завжди перший, фіксатори — в хвості.

        `core` має подвійну роль: у матриці це змінні trait-и айтема, а в
        «Сингл» / Image-to-Prompt — сам головний об'єкт. Тому стиль випереджає
        `core` ЛИШЕ коли заданий `base`: там роль головного об'єкта перебирає
        він, і стиль стає частиною тієї ж фіксованої рамки серії. Без `base`
        порядок лишається старим (core → style), інакше зворотний інжиніринг
        промпту почав би віддавати «pixel art, cyber fox» замість «cyber fox…».
        """
        parts: list[str] = []
        if self.base.strip():
            parts.append(self.base.strip())
            if self.style.strip():
                parts.append(self.style.strip())
            parts.append(self.core.strip())
        else:
            parts.append(self.core.strip())
            if self.style.strip():
                parts.append(self.style.strip())
        parts.extend(d.strip() for d in self.details if d.strip())
        if self.consistency.strip():
            parts.append(self.consistency.strip())
        prompt = ", ".join(p for p in parts if p)
        if self.tags.strip():
            prompt += f" {self.tags.strip()}"
        return prompt

    def to_dict(self) -> dict:
        return {
            "prompt": self.render(),
            "core": self.core,
            "style": self.style,
            "details": [d for d in self.details if d.strip()],
            "tags": self.tags,
            "traits": dict(self.traits),
            "negative": self.negative,
            "seed": self.seed,
            "polish_history": list(self.polish_history),
            "version": self.version,
            "base": self.base,
            "consistency": self.consistency,
        }


def parse_comma_list(raw: str) -> list[str]:
    """Розбирає список ознак, введений через кому."""
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def build_single(
    core: str, style: str, details: list[str], tags: str,
    base: str = "", consistency: str = "",
) -> list[dict]:
    """Режим «Сингл»: один промпт."""
    return [PromptObject(
        core, style, list(details), tags, base=base, consistency=consistency,
    ).to_dict()]


def build_group(
    core: str, styles: list[str], details: list[str], tags: str,
    base: str = "", consistency: str = "",
) -> list[dict]:
    """Режим «Специфічна група»: один об'єкт у кількох стилях."""
    return [
        PromptObject(
            core, style, list(details), tags, traits={"Style": style},
            base=base, consistency=consistency,
        ).to_dict()
        for style in styles
    ]


def build_matrix(
    categories: dict[str, list[str]],
    style: str = "",
    details: list[str] | None = None,
    tags: str = "",
    base: str = "",
    consistency: str = "",
) -> list[dict]:
    """Режим «Генеративна колекція»: декартів добуток усіх категорій ознак.

    categories: {"Персонаж": [...], "Фон": [...], "Аксесуар": [...]} —
    порядок ключів визначає порядок частин у промпті.

    base — BASE OBJECT серії: НЕ вісь матриці, а фіксований префікс кожного
    промпту. Тримати його поза categories принципово: як вісь із одного значення
    він множився б на решту (нешкідливо), але за зайнятої осі «персонажа» просто
    зникав би з промпту — і колекція втрачала б спільне ядро.
    """
    cats = {name: values for name, values in categories.items() if values}
    if not cats:
        return []
    names = list(cats)
    results = []
    for combo in itertools.product(*(cats[name] for name in names)):
        traits = dict(zip(names, combo))
        results.append(
            PromptObject(
                ", ".join(combo), style, list(details or []), tags, traits=traits,
                base=base, consistency=consistency,
            ).to_dict()
        )
    return results


def build_layered(
    combos: list[dict[str, str]],
    style: str = "",
    details: list[str] | None = None,
    tags: str = "",
    base: str = "",
    consistency: str = "",
) -> list[dict]:
    """Пошаровий режим: кожен айтем несе по одному значенню з КОЖНОЇ категорії.

    Різниця з `build_matrix` — не в кількості, а в повноті айтема. Матриця
    множить осі між собою, тож коли шість trait-категорій зводяться до трьох
    осей (як у `template_pipeline._TRAIT_TO_MATRIX`), значення однієї осі
    підмінюють одне одного: мавпа отримує корону АБО окуляри АБО худі, а не
    все разом. Для PFP це ламає саму ідею шарів і знецінює rarity — рідкість
    рахується за співпадінням кількох ознак в одному айтемі.

    `combos` беремо з `batch.sample_trait_combinations` (зважений семплінг із
    унікальністю) — та сама логіка, що вже працює в classic-гілці Collection.
    """
    return [
        PromptObject(
            ", ".join(v for v in combo.values() if v),
            style,
            list(details or []),
            tags,
            traits=dict(combo),
            base=base,
            consistency=consistency,
        ).to_dict()
        for combo in combos
    ]


def matrix_size(categories: dict[str, list[str]]) -> int:
    """Кількість комбінацій у матриці без її побудови."""
    sizes = [len(v) for v in categories.values() if v]
    return math.prod(sizes) if sizes else 0


def assign_seeds(prompts: list[dict], base_seed: int) -> list[dict]:
    """Проставляє детермінований seed кожному промпту (Q3.0 reproducibility).

    seed[i] = base_seed + i — той самий base_seed дає ту саму колекцію (для
    двигунів із підтримкою seed: Stability/Flux). Повертає копії, не мутуючи вхід.
    """
    out = []
    for i, p in enumerate(prompts):
        item = dict(p)
        item["seed"] = int(base_seed) + i
        out.append(item)
    return out


def from_raw_text(raw: str) -> list[dict]:
    """Точка входу 1: готові промпти в обхід конструктора, один на рядок."""
    return [
        {"prompt": line.strip(), "core": line.strip(), "style": "", "details": [], "tags": "", "traits": {}}
        for line in (raw or "").splitlines()
        if line.strip()
    ]


# B6 — rule-based підказка двигуна за текстом ідеї (ПЛАН_ЗАПОЗИЧЕНЬ.md).
# Категорія → ключові слова (двомовно, підрядкове порівняння в нижньому регістрі).
# Категорія→двигун мапиться у suggest_engine ЛІНИВО, щоб не імпортувати ai_service
# на рівні модуля (ai_service імпортує prompt_service — був би цикл).
# Пріоритет за порядком: перший збіг виграє (text > art > photo).
_ENGINE_HINT_RULES: list[tuple[str, tuple[str, ...]]] = [
    # Текст/лого/типографіка/преміум — OpenAI найкраще рендерить літери у зображенні.
    ("text", (
        "logo", "typograph", "lettering", "slogan", "poster", "banner", "label",
        "brand", "headline", "premium", "luxury", "app icon", "flat ui", "medallion",
        "badge", "enamel",
        "лого", "типографі", "шрифт", "напис", "текст", "слоган", "постер", "банер",
        "етикетк", "бренд", "вивіск", "преміум", "розкішн", "іконка", "бейдж", "медальйон",
    )),
    # Художнє/ілюстрація/акварель — Stability сильна в стилізованих стилях.
    ("art", (
        "watercolor", "painting", "illustration", "sketch", "drawing", "anime",
        "manga", "cartoon", "comic", "pastel", "oil paint", "concept art", "ink ",
        "chibi", "kawaii", "glitch", "datamosh", "synthwave", "vaporwave", "sumi-e",
        "ink wash", "voxel", "clay", "low poly", "pixel art", "art deco",
        "акварел", "живопис", "ілюстрац", "малюнок", "ескіз", "аніме", "манга",
        "мультяшн", "комікс", "олійн", "пастель", "концепт", "чібі", "глитч",
        "синтвейв", "туш", "воксель", "піксель",
    )),
    # Фотореал/кінематограф/портрет — Flux дає якісний фотореалізм дешево.
    ("photo", (
        "photo", "photoreal", "realistic", "cinematic", "portrait", "hyperreal",
        "dslr", "bokeh", "35mm", "matte painting", "chrome fashion", "holographic",
        "фото", "фотореал", "реалістичн", "кінематограф", "портрет", "гіперреал",
        "хром", "голограф",
    )),
]


def suggest_engine(idea: str) -> str:
    """B6: рекомендує двигун зображення за текстом ідеї (підказка-дефолт, НЕ примус).

    Повертає одну з констант ai_service.ENGINE_*. Без збігу ключових слів —
    універсальний gpt-image-1. Чиста функція; імпорт двигунів лінивий (цикл
    ai_service↔prompt_service). UI показує як рекомендацію, користувач не зобов'язаний.
    """
    from services.ai_service import ENGINE_FLUX, ENGINE_GPT_IMAGE, ENGINE_STABILITY

    by_category = {"text": ENGINE_GPT_IMAGE, "art": ENGINE_STABILITY, "photo": ENGINE_FLUX}
    text = (idea or "").lower()
    for category, keywords in _ENGINE_HINT_RULES:
        if any(kw in text for kw in keywords):
            return by_category[category]
    return ENGINE_GPT_IMAGE
