"""Style Lock / Collection Bible (ПЛАН_ЯКОСТІ.md § Q2.1).

Чистий модуль без Streamlit: фіксує «біблію стилю» колекції (стиль, світло,
ракурс, правило фону + опційні reference-зображення для майбутнього img2img),
щоб усі токени трималися одного вигляду. Біблія наповнюється з шаблону колекції
(`templates.COLLECTION_TEMPLATES`) і перекривається ручними правками оператора.

Зв'язок із генерацією:
- `bible_text()` → `PromptQualityProfile.style_bible` (контекст для LLM-полірування,
  Q1.4);
- `as_suffix()` → детермінований суфікс, що дописується до кожного промпту
  (через `PromptQualityProfile.extra_suffix`, Q1.1) навіть без LLM.

reference_images зберігаються, але в генерації поки не використовуються
(img2img/reference — Q3.5, відкладено).
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_REFERENCE_IMAGES = 3

# Поля біблії → людський підпис у bible_text() (англійською для LLM).
_TEXT_LABELS = (
    ("style", "Style"),
    ("lighting", "Lighting"),
    ("camera", "Camera framing"),
    ("background_rule", "Background"),
)


@dataclass
class StyleBible:
    """Незмінні правила вигляду колекції."""

    style: str = ""
    lighting: str = ""
    camera: str = ""
    background_rule: str = ""
    reference_images: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Не більше MAX_REFERENCE_IMAGES референсів (контракт Q2.1).
        self.reference_images = list(self.reference_images)[:MAX_REFERENCE_IMAGES]

    def is_empty(self) -> bool:
        return not any(
            getattr(self, name).strip() for name, _ in _TEXT_LABELS
        ) and not self.reference_images

    def to_dict(self) -> dict:
        return {
            "style": self.style,
            "lighting": self.lighting,
            "camera": self.camera,
            "background_rule": self.background_rule,
            "reference_images": list(self.reference_images),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "StyleBible":
        data = data or {}
        return cls(
            style=str(data.get("style", "")),
            lighting=str(data.get("lighting", "")),
            camera=str(data.get("camera", "")),
            background_rule=str(data.get("background_rule", "")),
            reference_images=[str(r) for r in (data.get("reference_images") or [])],
        )

    def bible_text(self) -> str:
        """Опис стилю для LLM-полірування (одне речення на правило)."""
        parts = [
            f"{label}: {getattr(self, name).strip()}"
            for name, label in _TEXT_LABELS
            if getattr(self, name).strip()
        ]
        return ". ".join(parts)

    def as_suffix(self) -> str:
        """Детермінований суфікс (кома-розділений) для дописування до промптів."""
        return ", ".join(
            getattr(self, name).strip()
            for name, _ in _TEXT_LABELS
            if getattr(self, name).strip()
        )


def from_template(template: dict | None) -> StyleBible:
    """Будує біблію з шаблону колекції (ключі style/camera/lighting/background)."""
    template = template or {}
    return StyleBible(
        style=str(template.get("style", "")),
        lighting=str(template.get("lighting", "")),
        camera=str(template.get("camera", "")),
        background_rule=str(template.get("background", "")),
    )


def merge(base: StyleBible, override: StyleBible) -> StyleBible:
    """Зливає шаблонну біблію з ручними правками: непорожнє з override перемагає.

    reference_images: беремо override, якщо там щось є, інакше base.
    """
    def pick(name: str) -> str:
        ov = getattr(override, name).strip()
        return ov or getattr(base, name)

    return StyleBible(
        style=pick("style"),
        lighting=pick("lighting"),
        camera=pick("camera"),
        background_rule=pick("background_rule"),
        reference_images=(
            list(override.reference_images) if override.reference_images
            else list(base.reference_images)
        ),
    )
