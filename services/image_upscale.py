"""Опційний upscale зображень перед export (C4-lite, Фаза E3).

Pillow — опційно; без нього upscale no-op. Увімкнення в UI лише якщо
`EXPORT_UPSCALE_ENABLED=1` (безпечний дефолт off на публіці).
"""

from __future__ import annotations

import io
import os

TARGET_MAX_DEFAULT = 2048


def upscale_available() -> bool:
    """Чи показувати опцію upscale в Export Center."""
    return os.getenv("EXPORT_UPSCALE_ENABLED", "0") == "1"


def maybe_upscale_bytes(
    data: bytes,
    *,
    enabled: bool,
    target_max: int = TARGET_MAX_DEFAULT,
) -> bytes:
    if not enabled or not data:
        return data
    try:
        from PIL import Image
    except ImportError:
        return data
    try:
        img = Image.open(io.BytesIO(data))
    except Exception:
        return data
    w, h = img.size
    if max(w, h) >= target_max:
        return data
    scale = target_max / max(w, h)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    resized = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
    resized = resized.resize(new_size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    resized.save(out, format="PNG")
    return out.getvalue()


def apply_to_assets(
    assets: list[dict],
    *,
    upscale: bool,
    target_max: int = TARGET_MAX_DEFAULT,
) -> list[dict]:
    """Повертає копії активів з опційно upscaled image_bytes."""
    if not upscale:
        return assets
    out: list[dict] = []
    for item in assets:
        row = dict(item)
        data = row.get("image_bytes")
        if data:
            row["image_bytes"] = maybe_upscale_bytes(data, enabled=True, target_max=target_max)
        out.append(row)
    return out


def _max_side_from_bytes(data: bytes) -> int:
    if not data:
        return 0
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        return max(w, h)
    except Exception:
        return 0


def asset_max_side(item: dict) -> int:
    """Найбільша сторона зображення активу (bytes або path)."""
    data = item.get("image_bytes")
    if data:
        return _max_side_from_bytes(data)
    path = item.get("path")
    if path:
        try:
            import network_config

            return _max_side_from_bytes(network_config.read_asset(str(path)))
        except (OSError, ValueError):
            return 0
    return 0


def collection_needs_upscale(
    assets: list[dict],
    *,
    target_max: int = TARGET_MAX_DEFAULT,
) -> bool:
    """True якщо хоча б одне зображення менше target (CN-7 nudge)."""
    if not assets:
        return False
    sides = [asset_max_side(a) for a in assets]
    sides = [s for s in sides if s > 0]
    if not sides:
        return False
    return max(sides) < target_max
