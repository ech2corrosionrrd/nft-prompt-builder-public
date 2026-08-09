"""Guard: продукт/on-chain метадані — виключно англійська (жодної кирилиці).

Закриває клас багу «укр-текст у метаданих NFT» (аудит 2026-07-11): значення трейтів,
Prompt-Lock, name, description. Дві лінії захисту:
  1. Джерело — шаблони колекцій мають EN traits/idea (кодмод trait_i18n).
  2. Рантайм — to_product_en на межі метаданих транслітерує будь-яку кирилицю,
     що просочилась (введену користувачем), тож інваріант тримається завжди.
"""

import io
import re
import zipfile

import pytest

from collection_templates import COLLECTION_TEMPLATES
from services import export_bundle, template_pipeline
from trait_i18n import strip_uk_hint, to_product_en, transliterate

_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def _walk_strings(obj):
    """Рекурсивно віддає всі рядки з dict/list (для сканування метаданих)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(k)
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)


def _has_cyrillic(obj) -> bool:
    return any(_CYRILLIC.search(s) for s in _walk_strings(obj))


# ── Лінія 1: шаблони EN за побудовою ──────────────────────────────────────────

def test_all_template_traits_and_ideas_are_english():
    """Жоден шаблон не містить укр у traits-значеннях чи idea (кодмод не відкотили)."""
    offenders = []
    for name, tpl in COLLECTION_TEMPLATES.items():
        if _CYRILLIC.search(str(tpl.get("idea", ""))):
            offenders.append((name, "idea", tpl.get("idea")))
        for cat, vals in (tpl.get("traits") or {}).items():
            for v in vals:
                if _CYRILLIC.search(str(v)):
                    offenders.append((name, cat, v))
    assert not offenders, f"укр у traits/idea шаблонів: {offenders[:10]}"


# ── Лінія 2: експорт-метадані EN для кожного шаблону ───────────────────────────

def _item_from_template(tpl: dict) -> dict:
    """Синтетичний токен: по одному (першому) значенню з кожної категорії трейтів."""
    traits = {cat: vals[0] for cat, vals in (tpl.get("traits") or {}).items() if vals}
    prompts = template_pipeline.prompts_from_template(tpl)
    prompt = prompts[0]["prompt"] if prompts else (tpl.get("idea") or "art")
    return {
        "traits": traits,
        "prompt": prompt,
        "description": prompt,
        "engine": "Flux",
        "seed": 1,
        "style": strip_uk_hint(str(tpl.get("style", ""))),
        "image_bytes": b"\x89PNG\r\n\x1a\n" + b"0" * 64,
    }


@pytest.mark.parametrize("tpl_name", list(COLLECTION_TEMPLATES))
@pytest.mark.parametrize("platform", ["opensea", "metaplex", "thirdweb", "generic"])
def test_export_metadata_no_cyrillic(tpl_name, platform):
    """build_metadata_list для будь-якого шаблону/платформи — без кирилиці."""
    tpl = COLLECTION_TEMPLATES[tpl_name]
    item = _item_from_template(tpl)
    meta = export_bundle.build_metadata_list(
        platform, [item, dict(item)], collection_name="My Collection",
    )
    assert not _has_cyrillic(meta), f"{tpl_name}/{platform}: кирилиця у метаданих"


@pytest.mark.parametrize("tpl_name", list(COLLECTION_TEMPLATES))
def test_w3ir_package_no_cyrillic(tpl_name):
    """W3IR mint-state/metadata для будь-якого шаблону — без кирилиці."""
    tpl = COLLECTION_TEMPLATES[tpl_name]
    data = export_bundle.build_w3ir_package_zip([_item_from_template(tpl)], "My Collection")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for n in zf.namelist():
            if n.endswith(".json"):
                assert not _CYRILLIC.search(zf.read(n).decode("utf-8")), f"{tpl_name}: кирилиця у {n}"


# ── Лінія 2b: рантайм-guard транслітерує ввід користувача ──────────────────────

def test_user_entered_cyrillic_is_transliterated():
    """Позасловникова кирилиця (свій трейт користувача) → ASCII on-chain."""
    item = {
        "traits": {"Background / Aura": "мій унікальний фон"},  # немає у словнику
        "prompt": "коте на місяці",
        "description": "опис українською",
        "image_bytes": b"\x89PNG" + b"0" * 64,
    }
    meta = export_bundle.build_metadata_list("opensea", [item], collection_name="Моя Колекція")
    assert not _has_cyrillic(meta)
    # назва транслітерована, а не викинута
    assert meta[0]["name"].startswith("Moia") or "Kolektsiia" in meta[0]["name"]


# ── Юніти trait_i18n ──────────────────────────────────────────────────────────

def test_to_product_en_uses_dictionary():
    assert to_product_en("золота корона") == "gold crown"
    assert to_product_en("Унікальна мавпа-колекціонер") == "unique collector ape"


def test_to_product_en_passthrough_english():
    assert to_product_en("gold crown") == "gold crown"
    assert to_product_en("") == ""


def test_to_product_en_transliterates_unknown():
    out = to_product_en("невідомий трейт користувача")
    assert not _CYRILLIC.search(out)


def test_strip_uk_hint_keeps_english_core():
    assert strip_uk_hint("Close-up PFP (Портрет великим планом)") == "Close-up PFP"
    assert strip_uk_hint("1:1 (Квадрат для NFT)") == "1:1"
    # дужки без кирилиці не чіпаємо
    assert strip_uk_hint("Style (Bored Ape, Doodles)") == "Style (Bored Ape, Doodles)"


def test_transliterate_is_ascii():
    assert transliterate("Привіт Світ").isascii()
    assert transliterate("золота корона") == "zolota korona"
