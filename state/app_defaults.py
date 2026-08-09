"""Спільні дефолти полів classic-конструктора (app + project_service)."""

from options import ASPECT_RATIOS, BACKGROUNDS, CAMERA_ANGLES, LIGHTING, MOODS, QUALITY_TIERS
from styles import NFT_STYLES

DEFAULTS: dict = {
    "idea": "",
    "style": NFT_STYLES[0],
    "camera": CAMERA_ANGLES[0],
    "lighting": LIGHTING[0],
    "background": BACKGROUNDS[0],
    "quality": QUALITY_TIERS[0],
    "mood": MOODS[0],
    "aspect_ratio": ASPECT_RATIOS[0],
    "stylize": 250,
    "chaos": 0,
    "seed": 0,
    "extra_notes": "",
    "collection_size": 100,
}
