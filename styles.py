"""Пресети художніх стилів NFT — єдине джерело для UI і шаблонів колекцій.

Кожен рядок: (prompt-значення, en-підпис, uk-підпис, en-опис, uk-опис).
Описи — лише для UI; у промпт іде повне prompt-значення (перше поле).
"""

_LANG_EN = "en"
_LANG_UA = "uk"

# fmt: off
_NFT_STYLE_OPTIONS: list[tuple[str, str, str, str, str]] = [
    (
        "3D Premium Render (Octane Render, Unreal Engine 5, Pixar style)",
        "3D Premium Render",
        "Преміальний 3D-рендер",
        "Volumetric 3D — glossy surfaces, cinematic light. Best for premium PFP; moderate trait variety.",
        "Об'ємний 3D — глянець, кінематографічне світло. Для преміум PFP; помірна варіативність traits.",
    ),
    (
        "2D Vector Clean (Bored Ape Yacht Club, Doodles style, чіткі лінії)",
        "2D Vector Clean",
        "Чистий 2D-вектор",
        "Flat 2D with crisp outlines — classic PFP collections. High color/trait variety, consistent silhouettes.",
        "Плоский 2D з чіткими контурами — класичні PFP-колекції. Висока варіативність кольорів і traits.",
    ),
    (
        "Cyberpunk / Sci-Fi (Неон, хромовані деталі, футуризм)",
        "Cyberpunk / Sci-Fi",
        "Кіберпанк / Sci-Fi",
        "Neon, chrome, futuristic cities. Strong mood range; great for trait-heavy sci-fi series.",
        "Неон, хром, футуристичні міста. Широкий настрій; добре для sci-fi серій з багатьма traits.",
    ),
    (
        "Dark Fantasy / Dark Synth (Похмуре фентезі, готика, стрімкі тіні)",
        "Dark Fantasy / Dark Synth",
        "Темне фентезі / dark synth",
        "Gothic fantasy, deep shadows, synth atmosphere. Best for moody character collections.",
        "Готичне фентезі, глибокі тіні, synth-атмосфера. Для похмурих персонажних колекцій.",
    ),
    (
        "Pixel Art / 8-Bit (Ретро-ігри, CryptoPunks стиль)",
        "Pixel Art / 8-Bit",
        "Піксель-арт / 8-біт",
        "Retro 8-bit grid — limited palette, iconic shapes. Very high variety via simple trait swaps.",
        "Ретро 8-біт — обмежена палітра, іконічні форми. Дуже висока варіативність через прості traits.",
    ),
    (
        "Anime / Kawaii / Manga (Японська анімація, яскраві емоції)",
        "Anime / Kawaii / Manga",
        "Аніме / kawaii / манга",
        "Anime linework, expressive faces. Popular PFP niche; high expression and accessory variety.",
        "Аніме-лінії, виразні обличчя. Популярна PFP-ніша; багато варіацій емоцій і аксесуарів.",
    ),
    (
        "Pop Art / Street Art (Графіті, трафарети, стиль Бенксі)",
        "Pop Art / Street Art",
        "Pop art / street art",
        "Bold stencils, graffiti energy, high contrast. Strong backgrounds and color trait variety.",
        "Сміливі трафарети, графіті, високий контраст. Сильна варіативність фонів і кольорів.",
    ),
    (
        "Surrealism / Psychedelic (Гіпнотичні патерни, викривлена реальність)",
        "Surrealism / Psychedelic",
        "Сюрреалізм / психоделія",
        "Dreamlike distortions, hypnotic patterns. Excellent for abstract-leaning series with wild traits.",
        "Сновидні викривлення, гіпнотичні патерни. Для абстрактних серій з екстремальними traits.",
    ),
    (
        "Oil Painting / Classical Art (Класичний живопис, текстурні мазки)",
        "Oil Painting / Classical Art",
        "Олійний живопис / класика",
        "Painterly brushstrokes, museum aesthetic. Softer trait variety; best for fine-art editions.",
        "Живописні мазки, музейна естетика. М'якша варіативність; для fine-art едішенів.",
    ),
    (
        "Low Poly / Voxel 3D (Minecraft, stylized game assets, blocky geometry)",
        "Low Poly / Voxel 3D",
        "Low poly / voxel 3D",
        "Blocky 3D geometry — isometric-friendly. Ideal for shape/color series and game-asset looks.",
        "Блочна 3D-геометрія — добре з ізометрією. Для серій форм/кольорів і game-asset стилю.",
    ),
    (
        "Watercolor Ink Illustration (soft edges, paper texture, hand-painted)",
        "Watercolor Ink Illustration",
        "Акварельна ink-ілюстрація",
        "Soft washes, paper grain, hand-painted feel. Gentle palette variety; dreamy collections.",
        "М'які заливки, фактура паперу, ручний живопис. Ніжна палітра; мрійливі колекції.",
    ),
    (
        "Comic Book Western (bold outlines, halftone, dynamic panels)",
        "Comic Book Western",
        "Вестерн-комікс",
        "Bold ink, halftone dots, dynamic poses. High outfit/action trait variety.",
        "Жирний контур, halftone, динамічні пози. Висока варіативність одягу й поз.",
    ),
    (
        "Clay Plasticine Stop-motion (handmade 3D, soft rounded forms)",
        "Clay Plasticine Stop-motion",
        "Пластиліновий stop-motion",
        "Soft sculpted 3D — tactile, rounded forms. Charming PFP; moderate shape variety.",
        "М'який скульптурний 3D — тактильні округлі форми. Милі PFP; помірна варіативність форм.",
    ),
    (
        "Photorealistic Cinematic Portrait (hyperreal skin, studio photo)",
        "Photorealistic Cinematic Portrait",
        "Фотореалістичний кінопортрет",
        "Hyperreal studio portrait — skin detail, lens depth. Lower abstract variety; premium 1/1 or small sets.",
        "Гіперреалістичний студійний портрет — деталь шкіри, глибина. Менше абстракції; преміум 1/1 або малі сети.",
    ),
    (
        "Minimalist Line Art (clean silhouettes, editorial NFT icon)",
        "Minimalist Line Art",
        "Мінімалістичний line art",
        "Sparse lines, strong silhouettes. Perfect for geometric/icon series with huge color trait space.",
        "Мінімум ліній, чіткі силуети. Ідеально для геометричних/іконкових серій із великою палітрою.",
    ),
    (
        "Generative Abstract / Parametric (algorithmic shapes, gradients)",
        "Generative Abstract / Parametric",
        "Генеративна абстракція / параметрика",
        "Algorithmic shapes, gradients, no fixed character. Highest variety — best for abstract/geometric collections.",
        "Алгоритмічні форми, градієнти, без фіксованого персонажа. Найвища варіативність — для абстрактних/геометричних колекцій.",
    ),
    (
        "Afrofuturism / Solarpunk (warm futurism, botanical tech)",
        "Afrofuturism / Solarpunk",
        "Афрофутуризм / solarpunk",
        "Warm futurism, plants + tech. Rich palette and cultural accessory traits.",
        "Теплий футуризм, рослини + технології. Багата палітра й культурні аксесуарні traits.",
    ),
    (
        "Gothic Luxury / Baroque (ornate frames, velvet, gold)",
        "Gothic Luxury / Baroque",
        "Готична розкіш / бароко",
        "Ornate gold, velvet, baroque frames. Premium mood; jewelry and fabric trait variety.",
        "Орнамент, золото, бароко. Преміум-настрій; варіативність прикрас і тканин.",
    ),
    (
        "Toy Vinyl Collectible (designer toy, glossy plastic)",
        "Toy Vinyl Collectible",
        "Колекційна vinyl toy-іграшка",
        "Designer toy gloss — collectible figurines. Great for character series with outfit swaps.",
        "Глянець designer toy — колекційні фігурки. Для персонажних серій зі зміною одягу.",
    ),
    (
        "Ink Wash / Sumi-e (monochrome brushwork, rice paper)",
        "Ink Wash / Sumi-e",
        "Туш / sumi-e",
        "Monochrome brush on rice paper. Zen minimalism; subtle ink-density and motif variety.",
        "Монохромна туш на рисовому папері. Дзен-мінімалізм; тонка варіативність мотивів і густини туші.",
    ),
    (
        "Holographic Chrome Fashion (reflective materials, runway pose)",
        "Holographic Chrome Fashion",
        "Голографічна chrome fashion",
        "Mirror chrome, runway fashion. Strong material/light traits; editorial PFP.",
        "Дзеркальний хром, подіумна мода. Сильні traits матеріалів і світла; editorial PFP.",
    ),
    (
        "Retro Futurism Poster (space-age optimism, grainy print)",
        "Retro Futurism Poster",
        "Постер ретрофутуризму",
        "Vintage poster print, grain, space-age optimism. Bold graphic series with palette variety.",
        "Вінтажний постер, зернистість, space-age оптимізм. Графічні серії з яскравою палітрою.",
    ),
    (
        "Synthwave / Vaporwave / Outrun (neon grid, palm sunset, retro 80s drive)",
        "Synthwave / Vaporwave",
        "Synthwave / Vaporwave",
        "80s neon grids, palm sunsets, chrome cars. Iconic outrun PFP and poster drops.",
        "Неонові сітки 80-х, пальмові заходи, chrome. Класичні synthwave PFP і постери.",
    ),
    (
        "Chibi / Super-deformed Kawaii (oversized head, tiny body, bold outlines)",
        "Chibi / Super-deformed",
        "Chibi / SD kawaii",
        "Cute SD proportions — huge head, tiny body. High expression and accessory variety.",
        "Милі SD-пропорції — велика голова, маленьке тіло. Багато емоцій і аксесуарів.",
    ),
    (
        "Glitch Art / Datamosh (RGB split, scanlines, corrupted pixels)",
        "Glitch Art / Datamosh",
        "Glitch / datamosh",
        "RGB splits, scanlines, datamosh — crypto-native abstract and edgy PFP.",
        "RGB-розриви, scanlines, datamosh — crypto-native абстракція й edgy PFP.",
    ),
    (
        "Art Deco / Art Nouveau (geometric luxury, gold lines, 1920s elegance)",
        "Art Deco / Art Nouveau",
        "Art Deco / Art Nouveau",
        "1920s luxury geometry, gold lines, poster elegance. Premium badges and portraits.",
        "Розкішна геометрія 1920-х, золоті лінії, постерна елегантність. Преміум-бейджі й портрети.",
    ),
    (
        "Matte Painting Cinematic Landscape (epic environment, film concept art)",
        "Matte Painting Landscape",
        "Matte painting пейзаж",
        "Epic film environments, atmospheric depth, concept-art vistas. No characters required.",
        "Епічні кіносвіти, атмосферна глибина, concept-art види. Без персонажів у кадрі.",
    ),
    (
        "Flat UI / App Icon Design (Figma-style vector, crisp app icon)",
        "Flat UI / App Icon",
        "Flat UI / app icon",
        "Clean vector UI icons, Figma-like flat design. Brand marks and app-store assets.",
        "Чисті vector UI-іконки, flat design. Бренд-знаки та app-store assets.",
    ),
    (
        "Badge / Medallion Engraving (embossed seal, metallic relief, ceremonial emblem)",
        "Badge / Medallion Engraving",
        "Бейдж / медальйон",
        "Embossed seals, metallic relief, ceremonial emblems. Event and DAO collectibles.",
        "Тиснені печатки, металевий рельєф, церемоніальні емблеми. Івент і DAO колекції.",
    ),
]
# fmt: on

NFT_STYLES: list[str] = [row[0] for row in _NFT_STYLE_OPTIONS]
NFT_STYLE_LABELS: dict[str, dict[str, str]] = {
    row[0]: {_LANG_EN: row[1], _LANG_UA: row[2]}
    for row in _NFT_STYLE_OPTIONS
}
NFT_STYLE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    row[0]: {_LANG_EN: row[3], _LANG_UA: row[4]}
    for row in _NFT_STYLE_OPTIONS
}
