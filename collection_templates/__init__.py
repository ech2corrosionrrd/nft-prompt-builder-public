"""Доменні шаблони колекцій (за архетипом). Збираються у COLLECTION_TEMPLATES
у фіксованому порядку ORDER — він задає послідовність дропдауна шаблонів у UI
(visible_templates). Розбито з templates.py 2026-06-27.
"""

from collection_templates import abstract, brand, event, fine_art, landscape, pfp
from collection_templates.base_objects import BASE_OBJECTS

# Порядок шаблонів у UI (історичний, чергує архетипи). Джерело правди порядку.
ORDER: list[str] = [
    'BAYC-style PFP',
    'Cyberpunk PFP',
    'Gremlins Family PFP',
    'Anime Kawaii',
    'Pixel Art 10k',
    '1/1 Fine Art',
    '3D Premium PFP',
    'Dark Fantasy PFP',
    'Pop Art Street PFP',
    'Psychedelic Surreal',
    'Synthwave Retro',
    'Mythical Beasts',
    'Nature Spirits',
    'Horror Undead',
    'Isometric Avatars',
    'Luxury Gold Portrait',
    'Voxel Explorers',
    'Watercolor Dreams',
    'Comic Heroes PFP',
    'Clay Creatures',
    'Photorealistic PFP',
    'Abstract Geometry Series',
    'Brand Icon System',
    'Atmospheric Worlds',
    'Event Badge Series',
    'Sumi-e Ink Studies',
    'Vinyl Toy Squad',
    'Chrome Fashion Icons',
    'Chibi Champs',
    'Glitch Geometry',
    'Retro Poster Series',
    'Art Deco Medallions',
    'Flat Vector Mascots',
    'Line Art Monograms',
    'W3IR Showcase Demo',
]

_MODULES = (pfp, fine_art, abstract, brand, landscape, event)


def _assemble() -> dict[str, dict]:
    pool: dict[str, dict] = {}
    for _mod in _MODULES:
        for _name, _tpl in _mod.TEMPLATES.items():
            if _name in pool:
                raise ValueError(f"дубльований шаблон {_name!r} (модуль {_mod.__name__})")
            pool[_name] = _tpl
    missing = set(ORDER) - set(pool)
    extra = set(pool) - set(ORDER)
    if missing or extra:
        raise ValueError(f"ORDER розійшовся з модулями: missing={missing} extra={extra}")
    # BASE OBJECT — фіксоване ядро серії з base_objects.py; setdefault, тож
    # шаблон може задати власне значення локально й воно виграє.
    unknown = set(BASE_OBJECTS) - set(pool)
    if unknown:
        raise ValueError(f"BASE_OBJECTS має шаблони поза каталогом: {unknown}")
    for _name, _base in BASE_OBJECTS.items():
        pool[_name].setdefault("base_object", _base)
    return {name: pool[name] for name in ORDER}


COLLECTION_TEMPLATES: dict[str, dict] = _assemble()
