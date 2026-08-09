"""Роутер публічних сторінок, метаданих, лендінгу та юридичних довідників."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

import api_server
from services import legal_pages, public_gallery

router = APIRouter(tags=["public"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "nft-prompt-builder-payments"}


@router.get("/")
def landing_page() -> HTMLResponse:
    """Маркетинговий лендінг (G1.1) — публічний, поза SIWE-периметром."""
    if not api_server._LANDING_HTML.is_file():
        raise HTTPException(status_code=404, detail="landing.html not found")
    page = api_server._LANDING_HTML.read_text(encoding="utf-8")
    page = page.replace("<!-- DEMO_GALLERY -->", public_gallery.render_demo_section())
    return HTMLResponse(page, headers={"Cache-Control": api_server._CACHE_LANDING})


@router.get("/og-card.png")
def og_card() -> FileResponse:
    """OG-прев'ю для соцмереж (G1.2)."""
    if not api_server._OG_CARD.is_file():
        raise HTTPException(status_code=404, detail="og-card.png not found")
    return FileResponse(api_server._OG_CARD, media_type="image/png", headers={"Cache-Control": api_server._CACHE_ASSET})


@router.get("/sitemap.xml")
def sitemap() -> FileResponse:
    """Sitemap для індексації лендінга (G1.2)."""
    if not api_server._SITEMAP.is_file():
        raise HTTPException(status_code=404, detail="sitemap.xml not found")
    return FileResponse(api_server._SITEMAP, media_type="application/xml", headers={"Cache-Control": api_server._CACHE_SEO})


@router.get("/robots.txt")
def robots() -> FileResponse:
    """robots.txt із посиланням на sitemap (G1.2)."""
    if not api_server._ROBOTS.is_file():
        raise HTTPException(status_code=404, detail="robots.txt not found")
    return FileResponse(api_server._ROBOTS, media_type="text/plain", headers={"Cache-Control": api_server._CACHE_SEO})


@router.get("/favicon.ico")
def favicon() -> Response:
    """SVG-фавікон (знак w3ir: куб у гексагоні)."""
    return Response(api_server._FAVICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": api_server._CACHE_ASSET})


@router.get("/legal")
def legal_uk() -> HTMLResponse:
    """Правові документи (ToS+Privacy+Refund), UA — публічно, поза SIWE."""
    page = legal_pages.render_legal_html("uk")
    if page is None:
        raise HTTPException(status_code=404, detail="legal docs not found")
    return HTMLResponse(page)


@router.get("/legal/en")
def legal_en() -> HTMLResponse:
    """Legal (ToS+Privacy+Refund), EN — public, outside SIWE."""
    page = legal_pages.render_legal_html("en")
    if page is None:
        raise HTTPException(status_code=404, detail="legal docs not found")
    return HTMLResponse(page)


@router.get("/c/{slug}")
def public_collection(slug: str) -> HTMLResponse:
    """Публічна shareable-сторінка колекції (G3.2) — read-only, поза SIWE."""
    page = public_gallery.render_collection_html(slug)
    if page is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return HTMLResponse(page)


@router.get("/c/{slug}/img/{filename}")
def public_collection_image(slug: str, filename: str) -> FileResponse:
    """Зображення публічної колекції (лише whitelist із manifest — анти-traversal)."""
    path = public_gallery.collection_image_path(slug, filename)
    if path is None:
        raise HTTPException(status_code=404, detail="image not found")
    return FileResponse(path, media_type=public_gallery.media_type(filename))
