"""CLI: опублікувати колекцію на публічну сторінку /c/<slug> (G3.2).

Бере теку із зображеннями (PNG/JPG/WEBP/GIF) і публікує як shareable-вітрину —
зручно для demo-колекцій (G1.4) та ручної публікації без app-UI.

    python scripts/publish_collection.py --dir export/my-coll/images \\
        --title "Neon Foxes" --subtitle "25 generative 1/1s"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# scripts/ не пакет — додаємо корінь у sys.path, щоб імпортувати services
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import public_gallery  # noqa: E402


def _load_images(directory: Path) -> list[tuple[str, bytes]]:
    files = sorted(p for p in directory.iterdir()
                   if p.suffix.lower() in public_gallery._ALLOWED_EXT)
    return [(p.name, p.read_bytes()) for p in files]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Опублікувати колекцію на /c/<slug>")
    ap.add_argument("--dir", required=True, help="тека із зображеннями")
    ap.add_argument("--title", required=True, help="назва колекції")
    ap.add_argument("--subtitle", default="", help="короткий підпис (опційно)")
    ap.add_argument("--slug", default="", help="бажаний слаг (інакше з назви)")
    args = ap.parse_args(argv)

    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"Тека не знайдена: {directory}")
        return 1
    images = _load_images(directory)
    if not images:
        print(f"У теці немає зображень {sorted(public_gallery._ALLOWED_EXT)}: {directory}")
        return 1

    slug = public_gallery.publish_collection(
        args.title, images, subtitle=args.subtitle, slug=args.slug,
    )
    print(f"Опубліковано ({len(images)} зображень): https://w3ir.io/c/{slug}")
    print(f"Локальна перевірка: http://127.0.0.1:8000/c/{slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
