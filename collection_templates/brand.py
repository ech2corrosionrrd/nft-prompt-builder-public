"""Шаблони колекцій: архетип brand. Збираються в templates.COLLECTION_TEMPLATES
(через collection_templates.__init__._assemble). НЕ змінюй порядок тут — порядок
дропдауна задає ORDER у __init__.py. Нові шаблони: додай сюди + у ORDER.
"""

TEMPLATES: dict[str, dict] = {'Brand Icon System': {'label': '🏷️ Brand Icon System',
                       'archetype': 'brand_icon',
                       'description': 'Бренд-колекція 25 варіантів: один знак/маскот у різних '
                                      'подачах і фонах. Замініть ідею на опис вашого знака; '
                                      'схожість, не піксель-копія лого (без upload). Міні-дроп у '
                                      'Конвеєрі — GPT Image рекомендовано.',
                       'description_en': 'Brand collection of 25 variants: one mark/mascot in '
                                         'different contexts and backgrounds. Replace the idea '
                                         'with your mark description; similarity, not '
                                         'pixel-perfect logo (no upload). Mini Pipeline drop — GPT '
                                         'Image recommended.',
                       'idea': 'minimalist geometric brand mark with a recognizable silhouette',
                       'style': 'Flat UI / App Icon Design (Figma-style vector, crisp app icon)',
                       'camera': 'Symmetrical Frontal View (Сувора симетрія по центру)',
                       'lighting': "Soft Studio Light (М'яке студійне світло, пастельні тони)",
                       'background': 'Solid Minimalist Color (Однотонний яскравий NFT-фон)',
                       'quality': 'Standard Clean (Охайний комерційний NFT-арт)',
                       'mood': 'Luxury & Premium',
                       'aspect_ratio': '1:1 (Квадрат для NFT)',
                       'stylize': 180,
                       'chaos': 12,
                       'collection_size': 25,
                       'traits': {'Подача / Контекст': ['centered app-icon composition on a solid field',
                                                        'emblem on a premium merch mockup',
                                                        'square social-media card with a headline field',
                                                        'minimalist event poster',
                                                        'mark on a clean studio backdrop'],
                                  'Фон / Поле': ['deep navy brand background',
                                                 'warm ivory minimalism',
                                                 'electric cyan gradient',
                                                 'charcoal with light grain',
                                                 'clean white high-key']}}}

# ── Line Art Monograms ────────────────────────────────────────────────────────
# Другий brand-шаблон (архетип мав лише один): монолінійні марки. Тут рамкою
# серії тримається не анатомія, а МЕТРИКА — однакова товщина штриха й оптичний
# розмір. Варіюється лише мотив і поле, тож набір читається як одна система
# знаків, а не як добірка різних логотипів.
TEMPLATES['Line Art Monograms'] = {
    'label': '✒️ Line Art Monograms',
    'description': 'Монолінійні знаки-монограми однієї товщини штриха: набір читається '
                   'як одна система, бо змінюється лише мотив і поле. Другий '
                   'brand-шаблон поряд із Brand Icon System — для лаконічних '
                   'лінійних марок замість заливок.',
    'description_en': 'Single-weight line art monograms: the set reads as one system because '
                      'only the motif and field change. A second brand template next to '
                      'Brand Icon System — for lean linear marks instead of filled shapes.',
    'idea': 'single-weight line art monogram mark',
    'style': 'Minimalist Line Art (clean silhouettes, editorial NFT icon)',
    'camera': 'Symmetrical Frontal View (Сувора симетрія по центру)',
    'lighting': "Soft Studio Light (М'яке студійне світло, пастельні тони)",
    'background': 'Solid Minimalist Color (Однотонний яскравий NFT-фон)',
    'quality': 'Clean Production Ready',
    'mood': 'Luxury & Premium',
    'aspect_ratio': '1:1 (Квадрат для NFT)',
    'stylize': 140,
    'chaos': 6,
    'collection_size': 25,
    'traits': {
        'Подача / Контекст': [
            'interlocking loop motif',
            'nested arch motif',
            'orbit and dot motif',
            'folded ribbon motif',
            'crossed diagonal motif',
        ],
        'Фон / Поле': [
            'warm ivory field',
            'deep ink navy field',
            'soft sage field',
            'graphite grey field',
            'clean white field',
        ],
    },
    'archetype': 'brand_icon',
}
