"""BASE OBJECT кожного шаблону — фіксоване ядро серії.

Навіщо окремий модуль, а не поле в самому шаблоні: базові об'єкти працюють лише
тоді, коли тримають ОДНАКОВИЙ рівень деталізації. Розкидані по шести файлах,
вони швидко розповзаються — один шаблон описує анатомію й лінії, сусідній
обмежується ярликом на два слова, і колекції другого розсипаються. Тут вони
поруч, і розбіжність видно оком. Застосовуються в `_assemble()` як `setdefault`,
тож шаблон завжди може перевизначити своє значення локально.

**Що таке базовий об'єкт.** Те, що НЕ змінюється між айтемами: вид істоти чи
предмета, кадр, пропорції, характер поверхні й ліній. Саме він дає впізнаваність
колекції; trait-и лише варіюють деталі поверх нього. Формула, якої тут
дотримуємось:

    [єдиний суб'єкт] + [кадр] + [що незмінне в пропорціях] + [що незмінне в поверхні/лініях]

**Чому не просто `idea`.** `idea` — ярлик для UI («unique collector ape»), і
моделі його замало: вона щоразу вигадує нову анатомію й товщину ліній, тож 25
зображень виходять 25 різними мавпами. `idea` лишається фолбеком
(`template_pipeline.base_object_from_template`), але для шаблонів у каталозі
базовий об'єкт заданий явно.

**Довжина має значення.** Разом зі стилем, trait-ами, деталями й фіксаторами це
має вкладатись у вікно текстового енкодера (у CLIP-моделей воно коротке — хвіст
просто обрізається, і фіксатори консистентності зникнуть саме тоді, коли вони
потрібні). Тримаємо ~15-22 слова; стелю стереже test_prompt_structure.
Англійською — продукт і on-chain EN (див. trait_i18n).
"""

BASE_OBJECTS: dict[str, str] = {
    # ── PFP: портретний кадр, головне — однакова геометрія голови й ліній ──
    "BAYC-style PFP": (
        "a single cartoon ape character, head and shoulders only, identical head shape "
        "and shoulder width, flat uniform fur tone, thick even outlines"
    ),
    "Cyberpunk PFP": (
        "a single cyber-augmented humanoid, head and shoulders only, identical face "
        "geometry and implant placement, uniform skin base tone, crisp neon edge accents"
    ),
    "Gremlins Family PFP": (
        "a single punk gremlin goblin creature, head and shoulders only, hyperreal "
        "wrinkled green scaly skin, huge pointed ears, identical ear shape and facial proportions"
    ),
    "Anime Kawaii": (
        "a single cute anime character, head and shoulders only, identical face proportions "
        "and large eye size, clean cel-shaded flat colors, uniform line weight"
    ),
    "Pixel Art 10k": (
        "a single pixel-art character sprite, head and shoulders only, identical grid "
        "alignment and body proportions, limited flat palette, hard pixel edges, no anti-aliasing"
    ),
    "3D Premium PFP": (
        "a single stylized 3D character bust, head and shoulders only, identical facial "
        "topology and bust crop, consistent subsurface skin shading and material finish"
    ),
    "Dark Fantasy PFP": (
        "a single armored dark-fantasy warrior, head and shoulders only, identical helmet "
        "silhouette proportions and shoulder line, muted desaturated palette"
    ),
    "Pop Art Street PFP": (
        "a single pop-art street character, head and shoulders only, identical face "
        "proportions, bold black outlines, flat halftone color fills"
    ),
    "Psychedelic Surreal": (
        "a single surreal creature, head and shoulders only, identical body proportions, "
        "flowing organic linework, saturated gradient fills"
    ),
    "Synthwave Retro": (
        "a single synthwave rider, head and shoulders only, identical helmet and shoulder "
        "proportions, magenta and cyan neon rim light, uniform grain"
    ),
    "Mythical Beasts": (
        "a single mythical beast, head and upper body only, identical head-to-body ratio, "
        "consistent scale pattern and fur texture density"
    ),
    "Nature Spirits": (
        "a single forest guardian spirit, head and shoulders only, identical silhouette "
        "proportions, soft bioluminescent accents, uniform organic texture"
    ),
    "Horror Undead": (
        "a single undead creature, head and shoulders only, identical skull proportions, "
        "consistent decay texture and desaturated flesh tone"
    ),
    "Isometric Avatars": (
        "a single isometric character figure, full body at a fixed isometric angle, "
        "identical height and limb proportions, uniform block shading"
    ),
    "Luxury Gold Portrait": (
        "a single aristocratic portrait bust, head and shoulders only, identical bust crop "
        "and posture, uniform gold-leaf accents and deep lacquer finish"
    ),
    "Voxel Explorers": (
        "a single voxel character figure, full body on a fixed voxel grid, identical cube "
        "size and body proportions, flat per-voxel shading"
    ),
    "Watercolor Dreams": (
        "a single dreamy character, head and shoulders only, identical face proportions, "
        "wet-on-wet watercolor bleed, visible paper grain, soft edges"
    ),
    "Comic Heroes PFP": (
        "a single comic-book hero, head and shoulders only, identical jaw and shoulder "
        "proportions, bold ink outlines, flat primary fills, halftone shadows"
    ),
    "Clay Creatures": (
        "a single handmade clay creature, full body, identical height and limb thickness, "
        "visible fingerprint texture, matte plasticine finish"
    ),
    "Photorealistic PFP": (
        "a single photorealistic human portrait, head and shoulders only, identical framing "
        "and eye-line height, consistent skin rendering and lens perspective"
    ),
    "Vinyl Toy Squad": (
        "a single collectible vinyl designer toy figure, full body standing, identical height "
        "and limb proportions, glossy injection-molded finish, visible seam lines"
    ),
    "Chrome Fashion Icons": (
        "a single fashion editorial avatar, head and shoulders only, identical posture and "
        "crop, liquid chrome material with holographic iridescence"
    ),
    "Chibi Champs": (
        "a single chibi mascot character, full body at a fixed two-heads-tall proportion, "
        "identical head-to-body ratio, soft rounded shapes, thick uniform outlines"
    ),
    "W3IR Showcase Demo": (
        "a single W3IR Genesis avatar, head and shoulders only, identical face geometry, "
        "clean vector shapes, uniform outline weight"
    ),
    "Flat Vector Mascots": (
        "a single flat vector mascot character, head and shoulders only, identical head "
        "shape and body proportions, flat fills with no gradients, bold uniform outlines"
    ),

    # ── Fine art: суб'єкт один, тримаємо щільність мазка й кадр ──
    "1/1 Fine Art": (
        "a single surreal cosmic creature as the sole subject, full-body, consistent "
        "anatomy scale and painterly brush density"
    ),
    "Sumi-e Ink Studies": (
        "a single sumi-e ink subject on empty paper, no characters, consistent brush "
        "pressure, stroke count and negative-space ratio"
    ),

    # ── Abstract: без персонажів; тримаємо масштаб і матеріал ──
    "Abstract Geometry Series": (
        "a single parametric geometric sculpture as the sole subject, floating in empty "
        "space, uniform matte material finish, no characters"
    ),
    "Glitch Geometry": (
        "a single glitched geometric artifact as the sole subject, in empty space, uniform "
        "RGB channel-split intensity and scanline density, no characters"
    ),

    # ── Brand: оптичний розмір і товщина штриха — усе, що робить набір системою ──
    "Brand Icon System": (
        "a single minimalist geometric brand mark, solid balanced silhouette, uniform "
        "stroke weight and corner radius, no text"
    ),
    "Line Art Monograms": (
        "a single monoline mark drawn in one continuous stroke of constant width, "
        "geometric construction, rounded stroke caps, no fills, no text"
    ),

    # ── Landscape: горизонт і глибина замість анатомії ──
    "Atmospheric Worlds": (
        "an epic atmospheric landscape vista with no characters, deep aerial perspective, "
        "layered ridgelines and cloud banks"
    ),
    "Retro Poster Series": (
        "a retro space-age travel poster vista with no characters, flat limited-palette "
        "shapes, bold silhouetted foreground, visible print grain"
    ),

    # ── Event badge: діаметр і рельєф — те, що видає серію медальйонів ──
    "Event Badge Series": (
        "a single commemorative Web3 summit badge medallion, engraved metal with enamel "
        "inlay, beveled rim, no readable text"
    ),
    "Art Deco Medallions": (
        "a single art deco gala medallion, symmetrical stepped geometry, polished metal "
        "with lacquer inlay, no readable text"
    ),
}
