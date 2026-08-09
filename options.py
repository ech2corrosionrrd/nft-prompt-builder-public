"""Списки опцій конструктора промптів (ракурс/світло/фон/якість/настрій/формат)
та випадкові ідеї. Винесено з app.py — чисті дані без Streamlit, спільні для
вкладки Constructor (build_panel), pipeline-етапу stage1 і `randomize_settings`.
"""

from __future__ import annotations

_LANG_EN = "en"
_LANG_UA = "uk"


def _label(en: str, uk: str) -> dict[str, str]:
    return {_LANG_EN: en, _LANG_UA: uk}


_CAMERA_ANGLE_OPTIONS = [
    ("Close-up PFP (Портрет великим планом для аватарки)", "Close-up PFP", "PFP-портрет великим планом"),
    ("Full Body Shot (Персонаж у повний зріст)", "Full Body Shot", "Персонаж у повний зріст"),
    ("Isometric 3D View (Ізометричний вигляд, як у стратегіях)", "Isometric 3D View", "Ізометричний 3D-ракурс"),
    ("Macro Shot (Фокус на деталях обличчя/маски)", "Macro Shot", "Макро на деталях обличчя/маски"),
    ("Dynamic Action Pose (Персонаж у русі/динамічна бойова поза)", "Dynamic Action Pose", "Динамічна бойова поза"),
    ("Symmetrical Frontal View (Сувора симетрія по центру)", "Symmetrical Frontal View", "Симетричний фронтальний кадр"),
    ("Three-quarter Bust Portrait", "Three-quarter Bust Portrait", "Портрет 3/4 до пояса"),
    ("Over-the-shoulder Cinematic Shot", "Over-the-shoulder Cinematic Shot", "Кінематографічний кадр через плече"),
    ("Low Angle Hero Shot", "Low Angle Hero Shot", "Геройський ракурс знизу"),
    ("Top-down Diorama View", "Top-down Diorama View", "Діорама зверху"),
    ("Wide Establishing Shot", "Wide Establishing Shot", "Широкий вступний план"),
    ("Dutch Angle Dynamic Frame", "Dutch Angle Dynamic Frame", "Динамічний нахилений кадр"),
]

_LIGHTING_OPTIONS = [
    ("Neon Cinematic Lighting (Контрастний кінематографічний неон)", "Neon Cinematic Lighting", "Контрастний кінематографічний неон"),
    ("Volumetric / God Rays (Драматичні промені світла крізь туман)", "Volumetric / God Rays", "Драматичні промені крізь туман"),
    ("Soft Studio Light (М'яке студійне світло, пастельні тони)", "Soft Studio Light", "М'яке студійне світло"),
    ("Cyber-Glow & Bioluminescence (Біолюмінесценція, світіння в темряві)", "Cyber-Glow & Bioluminescence", "Кібер-світіння та біолюмінесценція"),
    ("Retro Sunset / Synthwave (Тепле закатне світло 80-х)", "Retro Sunset / Synthwave", "Ретро-захід сонця / synthwave"),
    ("High Contrast Chiaroscuro (Глибокі тіні, нуарний стиль)", "High Contrast Chiaroscuro", "Глибокі нуарні тіні"),
    ("Golden Hour Editorial Light", "Golden Hour Editorial Light", "Золота година, editorial"),
    ("Moonlit Blue Rim Light", "Moonlit Blue Rim Light", "Синє місячне контрове світло"),
    ("Hard Flash Fashion Light", "Hard Flash Fashion Light", "Жорсткий fashion-спалах"),
    ("Holographic Rim Lighting", "Holographic Rim Lighting", "Голографічне контрове світло"),
    ("Underwater Caustic Light", "Underwater Caustic Light", "Підводні світлові каустики"),
    ("Ambient Occlusion Studio", "Ambient Occlusion Studio", "Студійне ambient occlusion"),
]

_BACKGROUND_OPTIONS = [
    ("Solid Minimalist Color (Однотонний яскравий NFT-фон)", "Solid Minimalist Color", "Однотонний яскравий NFT-фон"),
    ("Abstract Geometric Patterns (Абстрактна геометрія/сакральні фігури)", "Abstract Geometric Patterns", "Абстрактна геометрія / сакральні фігури"),
    ("Post-Apocalyptic Cyber-City (Руїни мегаполіса майбутнього)", "Post-Apocalyptic Cyber-City", "Постапокаліптичне кібер-місто"),
    ("Cosmic Nebula & Deep Space (Космічна туманність, зірки)", "Cosmic Nebula & Deep Space", "Космічна туманність і зорі"),
    ("Ancient Mystical Temple (Стародавній храм, рунічні стіни)", "Ancient Mystical Temple", "Стародавній містичний храм"),
    ("Glitch Art / Matrix Code (Ефекти цифрових помилок, код matrix)", "Glitch Art / Matrix Code", "Glitch art / код матриці"),
    ("Traditional Japanese Dojo (Японське додзьо, сакура)", "Traditional Japanese Dojo", "Японське додзьо із сакурою"),
    ("Luxury Gallery Interior", "Luxury Gallery Interior", "Інтер'єр преміум-галереї"),
    ("Floating Sky Island", "Floating Sky Island", "Плавучий острів у небі"),
    ("Desert Ruins at Dawn", "Desert Ruins at Dawn", "Пустельні руїни на світанку"),
    ("Underwater Crystal Palace", "Underwater Crystal Palace", "Підводний кришталевий палац"),
    ("Liminal Dream Room", "Liminal Dream Room", "Лімінальна кімната-сон"),
    ("Botanical Solarpunk Greenhouse", "Botanical Solarpunk Greenhouse", "Ботанічна solarpunk-оранжерея"),
    ("Holographic Gradient Stage", "Holographic Gradient Stage", "Голографічна градієнтна сцена"),
    ("Royal Throne Room", "Royal Throne Room", "Королівська тронна зала"),
]

_QUALITY_TIER_OPTIONS = [
    ("Standard Clean (Охайний комерційний NFT-арт)", "Standard Clean", "Охайний комерційний NFT-арт"),
    ("Hyper-Detailed 8k (Екстремальна деталізація мікротекстур)", "Hyper-Detailed 8k", "Екстремальна деталізація 8k"),
    ("Masterpiece Epic Concept Art (Рівень концепт-артів ААА-ігор)", "Masterpiece Epic Concept Art", "Епічний AAA concept art"),
    ("Vintage / Textured Matte (Ефект старої плівки або матового паперу)", "Vintage / Textured Matte", "Вінтажна матова текстура"),
    ("Clean Production Ready", "Clean Production Ready", "Чистий production-ready фініш"),
    ("Ultra Sharp Product Render", "Ultra Sharp Product Render", "Надчіткий product render"),
    ("Editorial Fashion Finish", "Editorial Fashion Finish", "Editorial fashion-фініш"),
    ("Handcrafted Texture Detail", "Handcrafted Texture Detail", "Ручна фактурна деталізація"),
    ("Generative Art Finish", "Generative Art Finish", "Фініш генеративного арту"),
]

_MOOD_OPTIONS = [
    ("Epic & Heroic", "Epic & Heroic", "Епічний і героїчний"),
    ("Dark & Mysterious", "Dark & Mysterious", "Темний і містичний"),
    ("Playful & Whimsical", "Playful & Whimsical", "Грайливий і казковий"),
    ("Luxury & Premium", "Luxury & Premium", "Розкішний і преміальний"),
    ("Chaotic & Glitchy", "Chaotic & Glitchy", "Хаотичний і glitchy"),
    ("Serene & Meditative", "Serene & Meditative", "Спокійний і медитативний"),
    ("Cute & Cozy", "Cute & Cozy", "Милий і затишний"),
    ("Regal & Noble", "Regal & Noble", "Королівський і шляхетний"),
    ("Rebellious & Streetwise", "Rebellious & Streetwise", "Бунтарський і вуличний"),
    ("Melancholic & Poetic", "Melancholic & Poetic", "Меланхолійний і поетичний"),
    ("Dreamy & Surreal", "Dreamy & Surreal", "Сновидний і сюрреалістичний"),
    ("Menacing & Powerful", "Menacing & Powerful", "Загрозливий і потужний"),
]

_ASPECT_RATIO_OPTIONS = [
    ("1:1 (Квадрат для NFT)", "1:1 Square", "1:1 квадрат для NFT"),
    ("16:9 (Пейзаж)", "16:9 Landscape", "16:9 пейзаж"),
    ("4:5 (Для мобільних)", "4:5 Portrait", "4:5 портрет для мобільних"),
    ("9:16 (Vertical story)", "9:16 Vertical story", "9:16 вертикальний story-формат"),
    ("3:4 (Portrait poster)", "3:4 Portrait poster", "3:4 портретний постер"),
]

CAMERA_ANGLES = [value for value, _, _ in _CAMERA_ANGLE_OPTIONS]
LIGHTING = [value for value, _, _ in _LIGHTING_OPTIONS]
BACKGROUNDS = [value for value, _, _ in _BACKGROUND_OPTIONS]
QUALITY_TIERS = [value for value, _, _ in _QUALITY_TIER_OPTIONS]
MOODS = [value for value, _, _ in _MOOD_OPTIONS]
ASPECT_RATIOS = [value for value, _, _ in _ASPECT_RATIO_OPTIONS]

_RANDOM_IDEA_OPTIONS = [
    ("cyber samurai with a plasma katana", "Cyber samurai with a plasma katana", "Кібер-самурай з плазмовою катаною"),
    ("wise owl alchemist in a potion library", "Wise owl alchemist in a potion library", "Мудра сова-алхімік у бібліотеці зілль"),
    ("robot barista in a steam-powered cafe", "Robot barista in a steam-powered cafe", "Робот-бариста у паровій кав'ярні"),
    ("cosmic pirate captain with a drone parrot", "Cosmic pirate captain with a drone parrot", "Космічний пірат з папугою-дроном"),
    ("fox shaman wearing a spirit mask", "Fox shaman wearing a spirit mask", "Лисиця-шаман у масці духів"),
    ("underwater octopus king with a trident", "Underwater octopus king with a trident", "Підводний король-восьминіг з тризубом"),
    ("viking mechanic on a steam drakkar", "Viking mechanic on a steam drakkar", "Вікінг-механік на паровому драккарі"),
    ("cat wizard holding a spellbook", "Cat wizard holding a spellbook", "Кіт-чарівник із книгою заклинань"),
    ("dragon cryptocurrency collector", "Dragon cryptocurrency collector", "Дракон-колекціонер криптовалют"),
    ("ninja panda with a bamboo sword", "Ninja panda with a bamboo sword", "Панда-ніндзя з бамбуковим мечем"),
    ("astronaut gardener with lunar flowers", "Astronaut gardener with lunar flowers", "Астронавт-садівник із місячними квітами"),
    ("wolf detective in a noir city", "Wolf detective in a noir city", "Вовк-детектив у нуарному місті"),
    ("holographic DJ with a portal vinyl record", "Holographic DJ with a portal vinyl record", "Голограмний діджей із вінілом-порталом"),
    ("bear gladiator in a neon arena", "Bear gladiator in a neon arena", "Ведмідь-гладіатор у неоновій арені"),
    ("frog alchemist on a flying lily pad", "Frog alchemist on a flying lily pad", "Жаба-алхімік на летючому лататті"),
    ("skeleton rocker with a flaming guitar", "Skeleton rocker with a flaming guitar", "Скелет-рокер із вогняною гітарою"),
    ("mythic ape collector in a velvet jacket", "Mythic ape collector in a velvet jacket", "Міфічна мавпа-колекціонер у оксамитовому жакеті"),
    ("clockwork raven oracle", "Clockwork raven oracle", "Механічний ворон-оракул"),
    ("crystal fox oracle in a moon temple", "Crystal fox oracle in a moon temple", "Кришталева лисиця-оракул у місячному храмі"),
    ("oni street racer with holographic tattoos", "Oni street racer with holographic tattoos", "Оні-стрітрейсер із голографічними тату"),
]

RANDOM_IDEAS = [value for value, _, _ in _RANDOM_IDEA_OPTIONS]

# Пресети для Етапу 1 (Сингл / Група) — випадаючі списки з accept_new_options.
_CORE_OBJECT_OPTIONS = [
    ("cyber samurai", "Cyber samurai", "Кібер-самурай"),
    ("regal fox collector", "Regal fox collector", "Королівська лисиця-колекціонер"),
    ("neon owl alchemist", "Neon owl alchemist", "Неонова сова-алхімік"),
    ("robot barista", "Robot barista", "Робот-бариста"),
    ("cosmic pirate captain", "Cosmic pirate captain", "Космічний пірат-капітан"),
    ("wise owl alchemist", "Wise owl alchemist", "Мудра сова-алхімік"),
    ("viking mechanic", "Viking mechanic", "Вікінг-механік"),
    ("plasma dragon", "Plasma dragon", "Плазмовий дракон"),
    ("ninja panda", "Ninja panda", "Панда-ніндзя"),
    ("astronaut gardener", "Astronaut gardener", "Астронавт-садівник"),
    ("solarpunk botanist", "Solarpunk botanist", "Solarpunk-ботанік"),
    ("royal llama astronaut", "Royal llama astronaut", "Королівська лама-астронавт"),
    ("mushroom knight", "Mushroom knight", "Грибний лицар"),
    ("lava golem drummer", "Lava golem drummer", "Лавовий голем-барабанщик"),
]

CORE_OBJECT_PRESETS = [value for value, _, _ in _CORE_OBJECT_OPTIONS] + RANDOM_IDEAS

ENGINE_TAG_PRESETS = [
    "--ar 1:1 --s 250 --v 6.0",
    "--ar 1:1 --s 500 --v 7",
    "--ar 16:9 --s 250 --v 6.0",
    "--ar 4:5 --s 300 --v 6.0",
    "--ar 1:1 --s 250 --c 10 --v 6.0",
]

_COLOR_DETAIL_OPTIONS = [
    ("vibrant neon palette, intricate details", "Vibrant neon palette, intricate details", "Яскрава неонова палітра, складні деталі"),
    ("pastel tones, soft gradients", "Pastel tones, soft gradients", "Пастельні тони, м'які градієнти"),
    ("high contrast, deep shadows", "High contrast, deep shadows", "Високий контраст, глибокі тіні"),
    ("bioluminescent glow, dark background", "Bioluminescent glow, dark background", "Біолюмінесцентне світіння, темний фон"),
    ("golden hour warmth, cinematic", "Golden hour warmth, cinematic", "Тепло золотої години, кінематографічно"),
    ("monochrome ink, red accent", "Monochrome ink, red accent", "Монохромна туш, червоний акцент"),
    ("iridescent chrome, holographic details", "Iridescent chrome, holographic details", "Переливчастий хром, голографічні деталі"),
    ("earth tones, handcrafted texture", "Earth tones, handcrafted texture", "Земляні тони, ручна фактура"),
]

COLOR_DETAIL_PRESETS = [value for value, _, _ in _COLOR_DETAIL_OPTIONS]


TRAIT_CATEGORIES = [
    "Голова / Шолом / Маска",
    "Очі / Окуляри",
    "Одяг / Броня",
    "Аксесуари / Зброя",
    "Фон / Аура",
    "Емоція / Вираз обличчя",
]

# Параметри генерації зображень (спільні для вкладок Collection та Images).
IMAGE_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
IMAGE_QUALITIES = ["low", "medium", "high"]


def list_index(options: list[str], value: str) -> int:
    """Індекс value у списку options; 0 якщо немає (для безпечного st.selectbox)."""
    try:
        return options.index(value)
    except ValueError:
        return 0


def trait_key(cat: str) -> str:
    """Ключ session_state для текстового поля категорії трейтів."""
    return f"trait_{cat}"


# Ключі зберігання матриці Етапу 1 (синхрон із ui/stage1_constructor._MATRIX_STORAGE_KEYS).
MATRIX_STORAGE_KEYS = [
    "Варіанти персонажа",
    "Варіанти фону",
    "Варіанти аксесуарів",
]

_MATRIX_TEMPLATE_CAT_MAP: dict[str, str] = {
    # Матриця Етапу 1: Core / Background / Accessory (див. HELP.md § matrix thinking).
    # Голова/емоції з trait-таблиць шаблонів — не «персонаж», а аксесуар або окремий шар.
    "Голова / Шолом / Маска": "Варіанти аксесуарів",
    "Очі / Окуляри": "Варіанти аксесуарів",
    "Одяг / Броня": "Варіанти аксесуарів",
    "Аксесуари / Зброя": "Варіанти аксесуарів",
    "Фон / Аура": "Варіанти фону",
    # Abstract / brand / landscape / event
    "Форма / Силует": "Варіанти аксесуарів",
    "Фон / Поле": "Варіанти фону",
    "Подача / Контекст": "Варіанти аксесуарів",
    "Сцена / Локація": "Варіанти персонажа",
    "Настрій / Освітлення": "Варіанти фону",
    "Рівень / Tier": "Варіанти персонажа",
    "Візуальна подача": "Варіанти аксесуарів",
}

_MATRIX_DEFAULTS: dict[str, list[str]] = {
    "Варіанти персонажа": [
        "cyber samurai",
        "regal fox collector",
        "wise owl alchemist",
        "robot barista",
        "cosmic pirate captain",
        "plasma dragon",
        "ninja panda",
        "viking warrior",
        "neon cat wizard",
        "astronaut gardener",
        "solarpunk botanist",
        "clockwork raven oracle",
        "crystal fox oracle",
        "mushroom knight",
    ],
    "Варіанти фону": [
        "neon city",
        "moon temple",
        "solid blue",
        "solid yellow",
        "cyber forest",
        "cosmic nebula",
        "neon rain",
        "gradient purple",
        "luxury gallery",
        "floating sky island",
        "desert ruins",
        "underwater palace",
        "botanical greenhouse",
    ],
    "Варіанти аксесуарів": [
        "golden crown",
        "viking helmet",
        "sunglasses",
        "gold chain",
        "plasma sword",
        "cigar",
        "microphone",
        "headphones",
        "energy drink",
        "golden cup",
        "holographic cape",
        "crystal staff",
        "robot companion",
        "laser monocle",
        "ancient key",
    ],
}


_MATRIX_LABEL_OPTIONS = [
    ("viking warrior", "Viking warrior", "Вікінг-воїн"),
    ("neon cat wizard", "Neon cat wizard", "Неоновий кіт-чарівник"),
    ("neon city", "Neon city", "Неонове місто"),
    ("moon temple", "Moon temple", "Місячний храм"),
    ("solid blue", "Solid blue", "Суцільний синій фон"),
    ("solid yellow", "Solid yellow", "Суцільний жовтий фон"),
    ("cyber forest", "Cyber forest", "Кібер-ліс"),
    ("cosmic nebula", "Cosmic nebula", "Космічна туманність"),
    ("neon rain", "Neon rain", "Неоновий дощ"),
    ("gradient purple", "Gradient purple", "Фіолетовий градієнт"),
    ("luxury gallery", "Luxury gallery", "Преміум-галерея"),
    ("floating sky island", "Floating sky island", "Плавучий острів у небі"),
    ("desert ruins", "Desert ruins", "Пустельні руїни"),
    ("underwater palace", "Underwater palace", "Підводний палац"),
    ("botanical greenhouse", "Botanical greenhouse", "Ботанічна оранжерея"),
    ("golden crown", "Golden crown", "Золота корона"),
    ("viking helmet", "Viking helmet", "Шолом вікінга"),
    ("sunglasses", "Sunglasses", "Сонцезахисні окуляри"),
    ("gold chain", "Gold chain", "Золотий ланцюг"),
    ("plasma sword", "Plasma sword", "Плазмовий меч"),
    ("cigar", "Cigar", "Сигара"),
    ("microphone", "Microphone", "Мікрофон"),
    ("headphones", "Headphones", "Навушники"),
    ("energy drink", "Energy drink", "Енергетичний напій"),
    ("golden cup", "Golden cup", "Золотий кубок"),
    ("holographic cape", "Holographic cape", "Голографічний плащ"),
    ("crystal staff", "Crystal staff", "Кришталевий посох"),
    ("robot companion", "Robot companion", "Робот-компаньйон"),
    ("laser monocle", "Laser monocle", "Лазерний монокль"),
    ("ancient key", "Ancient key", "Стародавній ключ"),
]


def _build_option_labels() -> dict[str, dict[str, str]]:
    rows = (
        _CAMERA_ANGLE_OPTIONS
        + _LIGHTING_OPTIONS
        + _BACKGROUND_OPTIONS
        + _QUALITY_TIER_OPTIONS
        + _MOOD_OPTIONS
        + _ASPECT_RATIO_OPTIONS
        + _RANDOM_IDEA_OPTIONS
        + _CORE_OBJECT_OPTIONS
        + _COLOR_DETAIL_OPTIONS
        + _MATRIX_LABEL_OPTIONS
    )
    labels = {value: _label(en, uk) for value, en, uk in rows}
    labels.update({
        "low": _label("Low (draft)", "Низька (чернетка)"),
        "medium": _label("Medium (balanced)", "Середня (баланс)"),
        "high": _label("High (final)", "Висока (фінальна)"),
    })
    return labels


OPTION_LABELS = _build_option_labels()


def option_label(value: str, lang: str) -> str:
    """Локалізований підпис для пресету; невідомі/custom значення лишає як є."""
    labels = OPTION_LABELS.get(value)
    if not labels:
        return value
    return labels.get(lang) or labels.get(_LANG_EN) or value


def matrix_trait_options() -> dict[str, list[str]]:
    """Пул значень для multiselect матриці: core-персонажі + traits шаблонів за категоріями."""
    from templates import COLLECTION_TEMPLATES

    pools: dict[str, set[str]] = {k: set() for k in MATRIX_STORAGE_KEYS}
    # Персонаж = головний суб'єкт (idea/core), не шоломи з trait-таблиць.
    pools["Варіанти персонажа"].update(CORE_OBJECT_PRESETS)
    for tpl in COLLECTION_TEMPLATES.values():
        idea = (tpl.get("idea") or "").strip()
        if idea:
            pools["Варіанти персонажа"].add(idea)
        for cat, values in (tpl.get("traits") or {}).items():
            key = _MATRIX_TEMPLATE_CAT_MAP.get(cat)
            if key:
                pools[key].update(values)
    for key in MATRIX_STORAGE_KEYS:
        pools[key].update(_MATRIX_DEFAULTS.get(key, []))
    return {k: sorted(v) for k, v in pools.items()}
