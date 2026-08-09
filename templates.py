"""Готові шаблони NFT-колекцій."""

# COLLECTION_TEMPLATES розбито по архетипах у collection_templates/ (2026-06-27);
# тут лишається логіка/хелпери. Порядок UI задає collection_templates.ORDER.
from collection_templates import COLLECTION_TEMPLATES

# Шаблони, видимі лише адмінам (staging/демо) — приховані від звичайних
# користувачів і в sidebar, і в welcome-гейті (див. visible_templates).
ADMIN_ONLY_TEMPLATES: frozenset[str] = frozenset({"W3IR Showcase Demo"})


def visible_templates(is_admin: bool) -> list[str]:
    """Назви шаблонів для користувача: адмін бачить усі, решта — без admin-only."""
    return [
        name for name in COLLECTION_TEMPLATES
        if is_admin or name not in ADMIN_ONLY_TEMPLATES
    ]


# Пороги supply-badge у sidebar (UX: міні-дроп vs Classic Collection 1k+).
SUPPLY_MINI_MAX = 100
SUPPLY_LARGE_MIN = 1000


def template_supply_badge_args(collection_size: int) -> dict[str, str] | None:
    """Аргументи для i18n-badge шаблону: mini (~25) або large (1k+/10k+).

    Повертає None для «середніх» supply (101–999) — badge не показуємо.
    """
    n = int(collection_size)
    if n <= SUPPLY_MINI_MAX:
        return {"kind": "mini", "short": f"~{n}"}
    if n >= SUPPLY_LARGE_MIN:
        short = "10k+" if n >= 5000 else "1k+"
        return {"kind": "large", "short": short}
    return None


def template_description(tpl: dict, lang: str) -> str:
    """Локалізований опис шаблону для sidebar (uk / en).

    Без перехресного fallback: при en не показуємо uk-текст (і навпаки).
    """
    from ui_strings import LANG_EN, default_ui_lang

    code = (lang or default_ui_lang()).split("-")[0].lower()
    if code == LANG_EN:
        return (tpl.get("description_en") or "").strip()
    return (tpl.get("description") or "").strip()


# Архетипи колекції (ПЛАН_АБСТРАКЦІЯ, ПЛАН_БРЕНД, ПЛАН_LANDSCAPE, ПЛАН_EVENT).
ARCHETYPE_PFP = "pfp"
ARCHETYPE_ABSTRACT = "abstract_geometric"
ARCHETYPE_BRAND = "brand_icon"
ARCHETYPE_LANDSCAPE = "landscape"
ARCHETYPE_EVENT = "event_badge"
ARCHETYPE_FINE_ART = "fine_art"


def template_archetype(tpl: dict) -> str:
    """Архетип шаблону; за замовчуванням — PFP."""
    return str(tpl.get("archetype") or ARCHETYPE_PFP)

# AG1: явний archetype на кожному шаблоні (дефолт — PFP).
for _tpl in COLLECTION_TEMPLATES.values():
    _tpl.setdefault("archetype", ARCHETYPE_PFP)
