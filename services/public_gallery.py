"""Публічні shareable-сторінки колекцій (G3.2) — read-only вітрина поза SIWE.

Після експорту користувач може опублікувати колекцію на публічний слаг
`/c/<slug>`: api_server віддає бренд-сторінку із сіткою зображень + OG-прев'ю +
CTA «Make your own». Кожна опублікована колекція = віральна петля (поділився →
привів наступного [[growth-loops]]) і водночас demo-вітрина (G1.4).

Зберігаємо у `data/public/<slug>/`: `manifest.json` + `img/<n>.<ext>`. Той самий
`data/` бачить і застосунок (пише при публікації), і api_server (читає при
віддачі) — БД не потрібна, файли простіші й переживають рестарти.

Чисті функції (без Streamlit/FastAPI) — UI/CLI лише викликають; рендер HTML тут
же, щоб бути тестованим без HTTP. Текст користувача ЕКРАНУЄТЬСЯ (html.escape),
зображення віддаються лише з whitelist у manifest (захист від path-traversal).
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import storage
from services.wallet_auth import short_wallet

PUBLIC_DIR = storage.DATA_DIR / "public"
PUBLIC_IMAGE_LIMIT = 60  # межа кількості зображень на публічній сторінці
_PUBLIC_BASE = "https://w3ir.io"      # де живе публічна вітрина (корінь домену)
_APP_URL = "https://ai.w3ir.io"       # куди веде «Make your own» / Launch app
# CTA shareable-сторінки з UTM — щоб міряти віральний трафік (CF Web Analytics ловить
# UTM на ai.w3ir.io ще до SIWE-редіректу). Повний гаманець власника НЕ зберігаємо
# (privacy), тож per-referrer ref= тут не додаємо — лише джерело.
_APP_CTA = f"{_APP_URL}/?utm_source=collection_share&utm_medium=cta&utm_campaign=viral"
_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif",
}


def slugify(text: str) -> str:
    """kebab-case слаг із назви: лише [a-z0-9-], без країв-дефісів, ≤64."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return s[:64].strip("-") or "collection"


def media_type(filename: str) -> str:
    return _MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def _unique_slug(base: str) -> str:
    """Гарантує унікальність слага: base, base-2, base-3, … (нова публікація)."""
    slug, n = base, 1
    while (PUBLIC_DIR / slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


def publish_collection(
    title: str,
    images: list[tuple[str, bytes]],
    *,
    subtitle: str = "",
    wallet: str = "",
    slug: str = "",
) -> str:
    """Публікує колекцію на новий публічний слаг. Повертає слаг.

    images — список (ім'я_файлу, байти). Бере перші PUBLIC_IMAGE_LIMIT із
    допустимими розширеннями, перейменовує на 1.<ext>, 2.<ext>… (стабільний
    порядок). Повний гаманець НЕ зберігається — лише скорочена форма.
    """
    valid = [
        (name, data) for name, data in images
        if data and Path(name).suffix.lower() in _ALLOWED_EXT
    ][:PUBLIC_IMAGE_LIMIT]
    if not valid:
        raise ValueError("Немає зображень із підтримуваним розширенням для публікації.")

    final_slug = _unique_slug(slugify(slug or title))
    coll_dir = PUBLIC_DIR / final_slug
    img_dir = coll_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    image_names: list[str] = []
    for i, (name, data) in enumerate(valid, start=1):
        ext = Path(name).suffix.lower()
        fname = f"{i}{ext}"
        (img_dir / fname).write_bytes(data)
        image_names.append(fname)

    # Реферал-код власника (G3.3): опаковий, НЕ розкриває гаманець — замикає
    # віральну петлю (хтось зробить свою → автор отримає бонус після її оплати).
    ref_code = ""
    if wallet:
        try:
            from services import payment_service
            ref_code = payment_service.referral_code_for(wallet)
        except Exception:
            ref_code = ""

    manifest = {
        "slug": final_slug,
        "title": (title or "Untitled collection").strip()[:120],
        "subtitle": (subtitle or "").strip()[:200],
        "wallet_short": short_wallet(wallet),
        "ref_code": ref_code,
        "images": image_names,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (coll_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return final_slug


def load_collection(slug: str) -> dict | None:
    """Манифест колекції за слагом або None. Слаг санітизується (анти-traversal)."""
    safe = slugify(slug)
    path = PUBLIC_DIR / safe / "manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def collection_image_path(slug: str, filename: str) -> Path | None:
    """Безпечний шлях до зображення колекції для віддачі.

    Віддаємо лише файли, перелічені у manifest['images'] (whitelist) — жодного
    шляху від клієнта в ФС, тож path-traversal неможливий.
    """
    manifest = load_collection(slug)
    if not manifest or filename not in manifest.get("images", []):
        return None
    path = PUBLIC_DIR / slugify(slug) / "img" / filename
    return path if path.is_file() else None


def _is_demo_worthy(m: dict) -> bool:
    """Колекція годиться для ПУБЛІЧНОЇ вітрини лендінга: має зображення і НЕ
    безіменний плейсхолдер. Дефолтний `title='Untitled collection'` = недороблена
    /dogfood-публікація — не світимо її зовнішнім відвідувачам (лишається досяжною
    за прямим `/c/<slug>`, але не в demo-сітці)."""
    if not m.get("images"):
        return False
    title = (m.get("title") or "").strip().lower()
    return bool(title) and not title.startswith("untitled")


def list_collections(limit: int = 12) -> list[dict]:
    """Опубліковані колекції для demo-вітрини G1.4 (найновіші перші).

    Плейсхолдери без назви відсіюються (`_is_demo_worthy`) ДО ліміту, щоб вітрина
    не показувала «Untitled collection» зовнішнім відвідувачам."""
    if not PUBLIC_DIR.is_dir():
        return []
    out: list[dict] = []
    for child in PUBLIC_DIR.iterdir():
        if child.is_dir():
            m = load_collection(child.name)
            if m and _is_demo_worthy(m):
                out.append(m)
    out.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return out[:limit]


def delete_collection(slug: str) -> bool:
    """Видаляє публічну колекцію (адмін/очистка). True, якщо щось видалено."""
    import shutil

    coll_dir = PUBLIC_DIR / slugify(slug)
    if coll_dir.is_dir():
        shutil.rmtree(coll_dir, ignore_errors=True)
        return True
    return False


def render_demo_section(limit: int = 6) -> str:
    """HTML demo-секції для лендінга (G1.4) — картки останніх колекцій або ''.

    Порожній рядок, якщо публікацій ще немає (лендінг просто не показує секцію).
    Кожна картка — перше зображення + назва, лінк на `/c/<slug>` (той самий домен).
    """
    cols = list_collections(limit)
    if not cols:
        return ""
    cards = []
    for m in cols:
        s = slugify(m["slug"])
        first = html.escape(m["images"][0])
        title = html.escape(m.get("title", "Collection"))
        n = len(m.get("images", []))
        cards.append(
            f'<a href="/c/{s}" class="card group block overflow-hidden rounded-2xl '
            f'border border-[var(--border)] bg-[var(--surface)]">'
            f'<img src="/c/{s}/img/{first}" alt="{title}" loading="lazy" '
            f'class="aspect-square w-full object-cover" />'
            f'<div class="p-3"><div class="truncate text-sm font-semibold">{title}</div>'
            f'<div class="text-xs text-[var(--lo)]">{n} items</div></div></a>'
        )
    return (
        '<section class="mx-auto max-w-6xl px-6 pb-16">'
        '<h2 class="text-center text-2xl font-bold tracking-tight sm:text-3xl">Made with w3ir.io</h2>'
        '<p class="mx-auto mt-2 max-w-xl text-center text-[var(--muted)]">'
        'Real collections built in the app. Click any — then make your own.</p>'
        '<div class="mt-10 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">'
        + "\n".join(cards)
        + "</div></section>"
    )


# ── Рендер публічної сторінки ─────────────────────────────────────────────────

def render_collection_html(slug: str) -> str | None:
    """HTML публічної сторінки колекції (бренд-стиль як landing.html) або None.

    OG-прев'ю — перше зображення (абсолютний URL), CTA «Make your own» → застосунок.
    Увесь текст користувача екранується.
    """
    m = load_collection(slug)
    if not m:
        return None
    title = html.escape(m.get("title", "Collection"))
    subtitle = html.escape(m.get("subtitle", ""))
    wallet_short = html.escape(m.get("wallet_short", ""))
    images = m.get("images", [])
    safe_slug = slugify(slug)
    og_image = f"{_PUBLIC_BASE}/c/{safe_slug}/img/{images[0]}" if images else f"{_PUBLIC_BASE}/og-card.png"
    page_url = f"{_PUBLIC_BASE}/c/{safe_slug}"

    tiles = "\n".join(
        f'        <img src="/c/{safe_slug}/img/{html.escape(name)}" alt="{title} #{i}" loading="lazy" '
        f'class="aspect-square w-full rounded-xl border border-[var(--border)] object-cover" />'
        for i, name in enumerate(images, start=1)
    )
    by_line = f'<p class="mt-1 text-sm text-[var(--lo)]">by {wallet_short}</p>' if wallet_short else ""
    sub_line = f'<p class="mt-3 text-[var(--muted)]">{subtitle}</p>' if subtitle else ""
    # CTA → застосунок: UTM (джерело) + опц. ref-код власника (віральна петля G3.3).
    ref_code = m.get("ref_code", "")
    cta = _APP_CTA + (f"&ref={ref_code}" if ref_code else "")

    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — made with w3ir.io</title>
  <meta name="description" content="An NFT collection of {len(images)} items, made with w3ir.io. Make your own in minutes." />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{title} — made with w3ir.io" />
  <meta property="og:description" content="An NFT collection made with w3ir.io. Make your own in minutes." />
  <meta property="og:url" content="{page_url}" />
  <meta property="og:image" content="{og_image}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:image" content="{og_image}" />
  <link rel="canonical" href="{page_url}" />
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap" rel="stylesheet" />
  <style>
    :root{{--bg:#0a0b0f;--surface:#12141a;--border:#232734;--text:#ecedef;--muted:#9ba1ae;--lo:#5a6072;--accent:#6e56cf;--accent-soft:#9e8cfc;}}
    *{{font-family:'Inter',system-ui,sans-serif}}
    body{{margin:0;background:var(--bg);color:var(--text)}}
    .btn-accent{{background:linear-gradient(135deg,var(--accent),var(--accent-soft))}}
    .btn-accent:hover{{filter:brightness(1.08)}}
  </style>
</head>
<body class="min-h-screen">
  <header class="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
    <a href="{_PUBLIC_BASE}" class="flex items-center gap-2">
      <div class="grid h-8 w-8 place-items-center rounded-lg btn-accent text-sm font-extrabold text-white">N</div>
      <span class="font-semibold tracking-tight">NFT Prompt Builder</span>
    </a>
    <a href="{cta}" class="btn-accent rounded-lg px-4 py-2 text-sm font-semibold text-white transition">Make your own →</a>
  </header>

  <section class="mx-auto max-w-5xl px-6 pt-6">
    <h1 class="text-3xl font-extrabold tracking-tight sm:text-4xl">{title}</h1>
    {by_line}
    {sub_line}
    <p class="mt-2 text-xs text-[var(--lo)]">{len(images)} items · made with <a href="{_PUBLIC_BASE}" class="text-[var(--accent-soft)] hover:underline">w3ir.io</a></p>
  </section>

  <section class="mx-auto max-w-5xl px-6 py-8">
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
{tiles}
    </div>
  </section>

  <section class="mx-auto max-w-5xl px-6 pb-16">
    <div class="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 text-center">
      <h2 class="text-xl font-bold tracking-tight">Make a collection like this</h2>
      <p class="mx-auto mt-2 max-w-md text-sm text-[var(--muted)]">Idea → AI art → mint-ready bundle in 15 minutes. Pay-as-you-go, non-custodial.</p>
      <a href="{cta}" class="btn-accent mt-5 inline-block rounded-xl px-7 py-3 font-semibold text-white transition">Launch app →</a>
    </div>
  </section>
</body>
</html>
"""
