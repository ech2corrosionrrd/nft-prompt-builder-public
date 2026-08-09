"""Рендер правових документів (УМОВИ.md / LEGAL.md) у брендовану HTML-сторінку.

Потрібен, щоб ToS/Privacy/Refund були доступні веб-користувачам за URL (футер
лендінга), а не лише як .md у репо. Чисті функції без FastAPI/Streamlit —
api_server лише віддає результат. Власний мінімальний markdown→HTML (без нової
залежності): підмножина, що реально вживається в цих документах.
"""

from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_FILES = {"uk": _ROOT / "УМОВИ.md", "en": _ROOT / "LEGAL.md"}
_PUBLIC_BASE = "https://w3ir.io"
_APP_URL = "https://ai.w3ir.io"

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """Інлайн-розмітка: екранування → код → жирний → посилання (.md→маршрут /legal)."""
    out = html.escape(text)
    out = _CODE_RE.sub(r"<code>\1</code>", out)
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)

    def _link(m: re.Match) -> str:
        label, href = m.group(1), m.group(2)
        # Внутрішні посилання між документами ведуть на маршрути /legal(/en).
        if href == "LEGAL.md":
            href = "/legal/en"
        elif href in ("УМОВИ.md", "%D0%A3%D0%9C%D0%9E%D0%92%D0%98.md"):
            href = "/legal"
        # Пускаємо лише безпечні схеми (http(s)/mailto) та внутрішні шляхи;
        # усе інше (напр. javascript:) рендеримо як простий текст.
        safe = href.startswith(("http://", "https://", "mailto:", "/", "#"))
        if not safe:
            return label
        return f'<a href="{href}" class="text-[var(--accent-soft)] hover:underline">{label}</a>'

    return _LINK_RE.sub(_link, out)


def md_to_html(md: str) -> str:
    """Мінімальний markdown→HTML: h1-3, **жирний**, посилання, `код`, списки, > цитата, ---."""
    lines = md.replace("\r\n", "\n").split("\n")
    parts: list[str] = []
    para: list[str] = []
    ul: list[str] = []
    quote: list[str] = []

    def flush_para() -> None:
        if para:
            parts.append(f"<p>{' '.join(para)}</p>")
            para.clear()

    def flush_ul() -> None:
        if ul:
            parts.append("<ul>" + "".join(f"<li>{li}</li>" for li in ul) + "</ul>")
            ul.clear()

    def flush_quote() -> None:
        if quote:
            parts.append(f"<blockquote>{' '.join(quote)}</blockquote>")
            quote.clear()

    def flush_all() -> None:
        flush_para(); flush_ul(); flush_quote()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_all()
            continue
        if stripped == "---":
            flush_all(); parts.append("<hr/>"); continue
        h = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if h:
            flush_all()
            level = len(h.group(1))
            parts.append(f"<h{level}>{_inline(h.group(2))}</h{level}>")
            continue
        if stripped.startswith("> "):
            flush_para(); flush_ul()
            quote.append(_inline(stripped[2:]))
            continue
        if stripped.startswith("- "):
            flush_para(); flush_quote()
            ul.append(_inline(stripped[2:]))
            continue
        flush_ul(); flush_quote()
        para.append(_inline(stripped))

    flush_all()
    return "\n".join(parts)


def _shell(title: str, body_html: str, other_lang_href: str, other_lang_label: str) -> str:
    """Брендована оболонка (Radix-dark, Inter) — у стилі публічних сторінок."""
    return f"""<!DOCTYPE html>
<html lang="uk" class="dark">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)} — w3ir.io</title>
  <meta name="robots" content="all" />
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap" rel="stylesheet" />
  <style>
    :root{{--bg:#0a0b0f;--surface:#12141a;--border:#232734;--text:#ecedef;--muted:#9ba1ae;--lo:#5a6072;--accent:#6e56cf;--accent-soft:#9e8cfc;}}
    *{{font-family:'Inter',system-ui,sans-serif}}
    body{{margin:0;background:var(--bg);color:var(--text)}}
    .doc h1{{font-size:1.9rem;font-weight:800;margin:0 0 .5rem}}
    .doc h2{{font-size:1.35rem;font-weight:700;margin:2rem 0 .6rem;padding-top:1rem;border-top:1px solid var(--border)}}
    .doc h3{{font-size:1.05rem;font-weight:600;margin:1.2rem 0 .4rem;color:var(--accent-soft)}}
    .doc p,.doc li{{color:var(--muted);line-height:1.65;font-size:.95rem}}
    .doc ul{{margin:.3rem 0 .8rem 1.1rem}}
    .doc li{{margin:.25rem 0}}
    .doc code{{background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:.05rem .35rem;font-size:.85em;color:var(--accent-soft)}}
    .doc blockquote{{border-left:3px solid var(--accent);background:var(--surface);margin:1rem 0;padding:.7rem 1rem;border-radius:0 8px 8px 0;color:var(--text)}}
    .doc hr{{border:0;border-top:1px solid var(--border);margin:1.5rem 0}}
    .doc strong{{color:var(--text)}}
  </style>
</head>
<body class="min-h-screen">
  <header class="mx-auto flex max-w-3xl items-center justify-between px-6 py-5">
    <a href="{_PUBLIC_BASE}" class="flex items-center gap-2">
      <div class="grid h-8 w-8 place-items-center rounded-lg text-sm font-extrabold text-white" style="background:linear-gradient(135deg,var(--accent),var(--accent-soft))">N</div>
      <span class="font-semibold tracking-tight">NFT Prompt Builder</span>
    </a>
    <a href="{other_lang_href}" class="text-sm text-[var(--accent-soft)] hover:underline">{other_lang_label}</a>
  </header>
  <main class="doc mx-auto max-w-3xl px-6 pb-20 pt-4">
{body_html}
  </main>
  <footer class="mx-auto max-w-3xl px-6 py-8 text-xs text-[var(--lo)] border-t border-[var(--border)]">
    <a href="{_APP_URL}" class="text-[var(--accent-soft)] hover:underline">Запустити застосунок →</a>
    &nbsp;·&nbsp; <a href="{_PUBLIC_BASE}" class="hover:underline">w3ir.io</a>
  </footer>
</body>
</html>"""


@lru_cache(maxsize=2)
def _render(lang: str) -> str | None:
    """Будує HTML для вже нормалізованої мови ('uk'/'en'). Кешовано (2 записи).

    Документи статичні між деплоями (деплой = рестарт служби → інвалідація),
    тож тримаємо в кеші замість дискового I/O + ре-рендеру markdown на кожен
    запит публічного маршруту /legal.
    """
    path = _FILES[lang]
    if not path.is_file():
        return None
    body = md_to_html(path.read_text(encoding="utf-8"))
    title = "Правові документи" if lang == "uk" else "Legal"
    if lang == "uk":
        other_href, other_label = "/legal/en", "EN"
    else:
        other_href, other_label = "/legal", "UA"
    return _shell(title, body, other_href, other_label)


def render_legal_html(lang: str = "uk") -> str | None:
    """HTML правової сторінки для мови ('uk'/'en'). None, якщо файлу немає.

    Невідома мова → 'uk'. Нормалізуємо ДО кешу, щоб довільні значення не
    витісняли валідні записи (maxsize=2).
    """
    return _render("en" if lang == "en" else "uk")
