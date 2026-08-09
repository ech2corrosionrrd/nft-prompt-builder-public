"""Шаблони колекцій: архетип event. Збираються в templates.COLLECTION_TEMPLATES
(через collection_templates.__init__._assemble). НЕ змінюй порядок тут — порядок
дропдауна задає ORDER у __init__.py. Нові шаблони: додай сюди + у ORDER.
"""

TEMPLATES: dict[str, dict] = {'Event Badge Series': {'label': '🎫 Event Badge Series',
                        'archetype': 'event_badge',
                        'description': 'Комеморативні бейджі для івенту/DAO: 5 tier × 5 подач = '
                                       '25. Замініть ідею на назву події (EN); без дат у промпті — '
                                       'metadata вручну.',
                        'description_en': 'Commemorative event badges for conferences/DAOs: 5 '
                                          'tiers × 5 styles = 25. Edit the idea to your event name '
                                          '(EN); dates go in metadata, not prompts.',
                        'idea': 'commemorative Web3 summit badge medallion without readable text',
                        'style': 'Badge / Medallion Engraving (embossed seal, metallic relief, '
                                 'ceremonial emblem)',
                        'camera': 'Symmetrical Frontal View (Сувора симетрія по центру)',
                        'lighting': "Soft Studio Light (М'яке студійне світло, пастельні тони)",
                        'background': 'Solid Minimalist Color (Однотонний яскравий NFT-фон)',
                        'quality': 'Standard Clean (Охайний комерційний NFT-арт)',
                        'mood': 'Luxury & Premium',
                        'aspect_ratio': '1:1 (Квадрат для NFT)',
                        'stylize': 160,
                        'chaos': 10,
                        'collection_size': 25,
                        'traits': {'Рівень / Tier': ['genesis founder tier',
                                                     'speaker tier',
                                                     'vip contributor tier',
                                                     'community member tier',
                                                     'general attendee tier'],
                                   'Візуальна подача': ['circular enamel medallion',
                                                        'ribbon award badge',
                                                        'holographic pass card',
                                                        'minimal lapel pin',
                                                        'ticket stub collectible layout']}},
 'Art Deco Medallions': {'label': '🏛️ Art Deco Medallions',
                         'archetype': 'event_badge',
                         'description': 'Art Deco бейджі та медальйони: 5 tier × 5 орнаментів = '
                                        '25. Преміум івент-колекція.',
                         'description_en': 'Art Deco badges and medallions: 5 tiers × 5 ornaments '
                                           '= 25. Premium event collection.',
                         'idea': 'art deco gala medallion without readable text',
                         'style': 'Art Deco / Art Nouveau (geometric luxury, gold lines, 1920s '
                                  'elegance)',
                         'camera': 'Symmetrical Frontal View (Сувора симетрія по центру)',
                         'lighting': "Soft Studio Light (М'яке студійне світло, пастельні тони)",
                         'background': 'Solid Minimalist Color (Однотонний яскравий NFT-фон)',
                         'quality': 'Vintage / Textured Matte (Ефект старої плівки або матового '
                                    'паперу)',
                         'mood': 'Luxury & Premium',
                         'aspect_ratio': '1:1 (Квадрат для NFT)',
                         'stylize': 200,
                         'chaos': 8,
                         'collection_size': 25,
                         'traits': {'Рівень / Tier': ['platinum patron tier',
                                                      'gold member tier',
                                                      'silver guest tier',
                                                      'bronze attendee tier',
                                                      'ivory invite tier'],
                                    'Візуальна подача': ['sunburst deco medallion',
                                                         'geometric fan emblem',
                                                         'stepped pyramid seal',
                                                         'gatsby fan motif badge',
                                                         'laurel wreath plaque']}}}
