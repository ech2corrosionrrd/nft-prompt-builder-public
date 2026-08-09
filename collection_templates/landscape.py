"""Шаблони колекцій: архетип landscape. Збираються в templates.COLLECTION_TEMPLATES
(через collection_templates.__init__._assemble). НЕ змінюй порядок тут — порядок
дропдауна задає ORDER у __init__.py. Нові шаблони: додай сюди + у ORDER.
"""

TEMPLATES: dict[str, dict] = {'Atmospheric Worlds': {'label': '🌄 Atmospheric Worlds',
                        'archetype': 'landscape',
                        'description': 'Атмосферні пейзажі та світи: 5 сцен × 5 настроїв = 25 '
                                       'кадрів. Без персонажів у кадрі — міні-дроп 1/1 art або '
                                       'обкладинки. Конвеєр → Stability/Flux.',
                        'description_en': 'Atmospheric landscapes and worlds: 5 scenes × 5 moods = '
                                          '25 frames. No characters in frame — mini 1/1 art or '
                                          'cover series. Pipeline → Stability/Flux.',
                        'idea': 'epic atmospheric landscape vista without characters',
                        'style': 'Matte Painting Cinematic Landscape (epic environment, film '
                                 'concept art)',
                        'camera': 'Wide Establishing Shot',
                        'lighting': 'Volumetric / God Rays (Драматичні промені світла крізь туман)',
                        'background': 'Cosmic Nebula & Deep Space (Космічна туманність, зірки)',
                        'quality': 'Masterpiece Epic Concept Art (Рівень концепт-артів ААА-ігор)',
                        'mood': 'Serene & Meditative',
                        'aspect_ratio': '16:9 (Пейзаж)',
                        'stylize': 320,
                        'chaos': 28,
                        'collection_size': 25,
                        'traits': {'Сцена / Локація': ['mountain peaks above clouds',
                                                       'ancient forest glade with mist',
                                                       'ocean cliffs at storm horizon',
                                                       'desert dunes under vast sky',
                                                       'aurora tundra with frozen lake'],
                                   'Настрій / Освітлення': ['golden hour warm glow',
                                                            'blue hour soft mist',
                                                            'dramatic storm light breaks',
                                                            'moonlit calm silver tones',
                                                            'volumetric god rays through haze']}},
 'Retro Poster Series': {'label': '🛸 Retro Poster Series',
                         'archetype': 'landscape',
                         'description': 'Вінтажні space-age постери: 5 сцен × 5 палітр = 25. '
                                        'Ретрофутуризм без персонажів.',
                         'description_en': 'Vintage space-age posters: 5 scenes × 5 palettes = 25. '
                                           'Retro-futurism without characters.',
                         'idea': 'retro space-age poster vista without characters',
                         'style': 'Retro Futurism Poster (space-age optimism, grainy print)',
                         'camera': 'Wide Establishing Shot',
                         'lighting': 'Retro Sunset / Synthwave (Тепле закатне світло 80-х)',
                         'background': 'Cosmic Nebula & Deep Space (Космічна туманність, зірки)',
                         'quality': 'Vintage / Textured Matte (Ефект старої плівки або матового '
                                    'паперу)',
                         'mood': 'Epic & Heroic',
                         'aspect_ratio': '16:9 (Пейзаж)',
                         'stylize': 340,
                         'chaos': 24,
                         'collection_size': 25,
                         'traits': {'Сцена / Локація': ['rocket launch pad horizon',
                                                        'flying saucer over city',
                                                        'space station orbit view',
                                                        'alien desert highway',
                                                        'utopian dome colony'],
                                    'Настрій / Освітлення': ['orange sunset grain',
                                                             'teal poster fade',
                                                             'red propaganda bold',
                                                             'purple cosmic glow',
                                                             'cream vintage paper']}}}
