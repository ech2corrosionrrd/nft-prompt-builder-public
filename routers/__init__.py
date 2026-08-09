"""Пакет роутерів для FastAPI api_server."""

from routers.public import router as public_router
from routers.auth import router as auth_router
from routers.webhooks import router as webhooks_router
from routers.gremlin import router as gremlin_router
from routers.b2b import router as b2b_router

__all__ = [
    "public_router",
    "auth_router",
    "webhooks_router",
    "gremlin_router",
    "b2b_router",
]
