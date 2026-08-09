"""Шаблони колекцій: архетип abstract. Збираються в templates.COLLECTION_TEMPLATES
(через collection_templates.__init__._assemble). НЕ змінюй порядок тут — порядок
дропдауна задає ORDER у __init__.py. Нові шаблони: додай сюди + у ORDER.
"""

TEMPLATES: dict[str, dict] = {'Abstract Geometry Series': {'label': '🔷 Abstract Geometry Series',
                              'archetype': 'abstract_geometric',
                              'description': 'Генеративна абстракція: форми, градієнти, сакральна '
                                             'геометрія. Матриця 5×5 = 25 композицій — міні-дроп у '
                                             'Конвеєрі.',
                              'description_en': 'Generative abstraction: shapes, gradients, sacred '
                                                'geometry. 5×5 matrix = 25 compositions — mini '
                                                'Pipeline drop.',
                              'idea': 'parametric abstract geometric sculpture',
                              'style': 'Generative Abstract / Parametric (algorithmic shapes, '
                                       'gradients)',
                              'camera': 'Symmetrical Frontal View (Сувора симетрія по центру)',
                              'lighting': 'Holographic Rim Lighting',
                              'background': 'Abstract Geometric Patterns (Абстрактна '
                                            'геометрія/сакральні фігури)',
                              'quality': 'Generative Art Finish',
                              'mood': 'Serene & Meditative',
                              'aspect_ratio': '1:1 (Квадрат для NFT)',
                              'stylize': 420,
                              'chaos': 38,
                              'collection_size': 25,
                              'traits': {'Форма / Силует': ['sphere with a smooth gradient',
                                                            'cube with soft bevels',
                                                            'torus with a neon ring',
                                                            'tetrahedron with an inner glow',
                                                            'fibonacci spiral of particles'],
                                         'Фон / Поле': ['deep black void',
                                                        'pastel mesh gradient',
                                                        'sacred gold grid',
                                                        'neon purple fog',
                                                        'minimalist white space']}},
 'Glitch Geometry': {'label': '📺 Glitch Geometry',
                     'archetype': 'abstract_geometric',
                     'description': 'Glitch / datamosh абстракція: 5 форм × 5 фонів = 25. '
                                    'Crypto-native міні-дроп.',
                     'description_en': 'Glitch / datamosh abstract: 5 forms × 5 fields = 25. '
                                       'Crypto-native mini drop.',
                     'idea': 'glitched geometric artifact without characters',
                     'style': 'Glitch Art / Datamosh (RGB split, scanlines, corrupted pixels)',
                     'camera': 'Symmetrical Frontal View (Сувора симетрія по центру)',
                     'lighting': 'Neon Cinematic Lighting (Контрастний кінематографічний неон)',
                     'background': 'Abstract Geometric Patterns (Абстрактна геометрія/сакральні '
                                   'фігури)',
                     'quality': 'Generative Art Finish',
                     'mood': 'Dark & Mysterious',
                     'aspect_ratio': '1:1 (Квадрат для NFT)',
                     'stylize': 400,
                     'chaos': 42,
                     'collection_size': 25,
                     'traits': {'Форма / Силует': ['RGB split cube',
                                                   'datamosh sphere',
                                                   'scanline pyramid',
                                                   'corrupted torus',
                                                   'pixel burst star'],
                                'Фон / Поле': ['black CRT void',
                                               'magenta glitch grid',
                                               'cyan noise field',
                                               'green terminal matrix',
                                               'white static snow']}}}
