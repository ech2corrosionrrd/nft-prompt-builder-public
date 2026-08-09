"""Auto-QA Lite для зображень куратора (ПЛАН_NFT_РЕЗУЛЬТАТ.md § C1).

Чисті функції без Streamlit: швидка перевірка blank/blur/corrupt/tiny.
Pillow — опційно (якщо є, точніше blank/blur); без нього — байтові евристики.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

MIN_BYTES = 64
MIN_DIMENSION = 32
BLANK_VAR_THRESHOLD = 25.0
BLUR_EDGE_THRESHOLD = 8.0

ISSUE_CORRUPT = "corrupt"
ISSUE_TINY = "tiny"
ISSUE_BLANK = "blank"
ISSUE_BLURRY = "blurry"


@dataclass
class QAResult:
    score: int
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def analyze_image_bytes(data: bytes) -> QAResult:
    """Оцінка якості зображення за байтами (0–100, менше = гірше)."""
    issues: list[str] = []
    if len(data) < MIN_BYTES:
        return QAResult(score=0, issues=[ISSUE_CORRUPT])
    if not _looks_like_image(data):
        return QAResult(score=0, issues=[ISSUE_CORRUPT])

    dims = _image_dimensions(data)
    if dims and (dims[0] < MIN_DIMENSION or dims[1] < MIN_DIMENSION):
        issues.append(ISSUE_TINY)

    issues.extend(_visual_issues(data))
    score = max(0, 100 - 35 * len(issues))
    return QAResult(score=score, issues=issues)


def analyze_image_path(path: str) -> QAResult:
    try:
        return analyze_image_bytes(Path(path).read_bytes())
    except OSError:
        return QAResult(score=0, issues=[ISSUE_CORRUPT])


def star_rating_from_qa(score: int) -> int:
    """QA 0–100 → зірки 1–5 (технічна евристика: blur/blank/corrupt, не естетика).

    Пороги узгоджені з формулою score=100−35×issues: 0 issues→5★, 1→4★, 2→3★, 3+→1–2★.
    """
    if score >= 90:
        return 5
    if score >= 65:
        return 4
    if score >= 30:
        return 3
    if score > 0:
        return 2
    return 1


def _looks_like_image(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8"


def _image_dimensions(data: bytes) -> tuple[int, int] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return w, h
    return None


def _visual_issues(data: bytes) -> list[str]:
    try:
        import io

        from PIL import Image, ImageFilter, ImageStat
    except ImportError:
        return []

    try:
        gray = Image.open(io.BytesIO(data)).convert("L")
        if ImageStat.Stat(gray).var[0] < BLANK_VAR_THRESHOLD:
            return [ISSUE_BLANK]
        edge_mean = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
        if edge_mean < BLUR_EDGE_THRESHOLD:
            return [ISSUE_BLURRY]
    except Exception:
        return [ISSUE_CORRUPT]
    return []
