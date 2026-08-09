"""FastAPI: Helio webhook + healthcheck + SIWE auth + B2B API (Фаза A).

Запуск:
    uvicorn api_server:app --host 127.0.0.1 --port 8000

Cloudflare Tunnel: Public Hostname pay.w3ir.io / ai.w3ir.io / gen.w3ir.io
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import hashlib
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# .env МАЄ завантажитися ДО імпорту services.* — інакше module-level константи
# в них обчисляться з дефолтами.
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402

from services import auth_gateway, b2b_service, holder_rewards  # noqa: E402
from services.log_safety import configure_production_logging  # noqa: E402
from services.rate_limit import allow_request  # noqa: E402
from services.payment_service import (  # noqa: E402
    helio_keys,
    mark_fulfillment_done,
    mark_fulfillment_failed,
    pending_fulfillments,
    reconcile_payments_safe,
)

# ⚠️ Цикл api_server ↔ routers НАВМИСНИЙ і крихкий. Роутери читають звідси
# змінюваний стан (`_rate_limit`, `_NONCE_STORE`, ліміти, шляхи до шаблонів)
# через `import api_server` + доступ до атрибута в момент ЗАПИТУ — саме тому
# цикл не рветься на імпорті. Тести патчать той самий стан як `api_server.X`
# (`allow_request`, `_GREMLIN_API_KEY`, `_LAUNCHPAD_MAX_UPLOAD_MB`,
# `mark_fulfillment_*`), тож переносити його в окремий модуль не можна без
# переписування цих тестів — патч api_server.X тоді мовчки перестане діяти.
# У роутерах — ЛИШЕ `import api_server`, ніколи `from api_server import X`:
# перший варіант зв'язується з напівімпортованим модулем і чекає до виклику,
# другий падає ImportError уже на старті.
from routers import (  # noqa: E402
    auth_router,
    b2b_router,
    gremlin_router,
    public_router,
    webhooks_router,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
configure_production_logging()
logger = logging.getLogger("api_server")

# Періоди фонових циклів (сек)
RECONCILE_INTERVAL_SECONDS = int(os.environ.get("HELIO_RECONCILE_INTERVAL_SECONDS") or "300")
HOLDER_SYNC_INTERVAL_SECONDS = int(os.environ.get("HOLDER_SYNC_INTERVAL_SECONDS") or "120")
FULFILLMENT_RECONCILE_INTERVAL_SECONDS = int(os.environ.get("FULFILLMENT_RECONCILE_INTERVAL_SECONDS") or "300")
FULFILLMENT_STALE_SECONDS = int(os.environ.get("FULFILLMENT_STALE_SECONDS") or "300")
FULFILLMENT_MAX_ATTEMPTS = int(os.environ.get("FULFILLMENT_MAX_ATTEMPTS") or "5")
FULFILLMENT_AUTORETRY_RESERVED_MINT = os.environ.get("FULFILLMENT_AUTORETRY_RESERVED_MINT") == "1"

FULFILLMENT_MAX_CONCURRENCY = int(os.environ.get("FULFILLMENT_MAX_CONCURRENCY") or "4")
_fulfillment_semaphores: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}


def _fulfillment_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _fulfillment_semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(max(1, FULFILLMENT_MAX_CONCURRENCY))
        _fulfillment_semaphores[loop] = sem
    return sem


def _gremlin_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _gremlin_semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(max(1, GREMLIN_MAX_CONCURRENCY))
        _gremlin_semaphores[loop] = sem
    return sem


# Rate limit константи
_AUTH_NONCE_LIMIT = int(os.environ.get("AUTH_NONCE_RATE_LIMIT") or "30")
_AUTH_VERIFY_LIMIT = int(os.environ.get("AUTH_VERIFY_RATE_LIMIT") or "20")
_WEBHOOK_RATE_LIMIT = int(os.environ.get("HELIO_WEBHOOK_RATE_LIMIT") or "120")
_RATE_WINDOW = float(os.environ.get("API_RATE_WINDOW_SECONDS") or "60")

_GREMLIN_API_KEY = os.environ.get("GREMLIN_API_KEY") or ""
_GREMLIN_GENERATE_LIMIT = int(os.environ.get("GREMLIN_GENERATE_RATE_LIMIT") or "10")
_GREMLIN_HOLDER_LIMIT = int(os.environ.get("GREMLIN_HOLDER_RATE_LIMIT") or "60")
GREMLIN_MAX_CONCURRENCY = int(os.environ.get("GREMLIN_MAX_CONCURRENCY") or "3")
_gremlin_semaphores: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}

_LAUNCHPAD_MAX_UPLOAD_MB = int(os.environ.get("LAUNCHPAD_MAX_UPLOAD_MB") or "25")
_LAUNCHPAD_LIMIT = int(os.environ.get("LAUNCHPAD_RATE_LIMIT") or "30")
_VAULT_STATUS_LIMIT = int(os.environ.get("VAULT_STATUS_RATE_LIMIT") or "60")


def _client_ip(request: Request) -> str:
    cf_ip = (request.headers.get("cf-connecting-ip") or "").strip()
    if cf_ip:
        return cf_ip
    if os.environ.get("RATE_LIMIT_TRUST_XFF") == "1":
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _rate_limit(request: Request, bucket: str, limit: int) -> None:
    ip = _client_ip(request)
    if not allow_request(f"{bucket}:{ip}", limit=limit, window=_RATE_WINDOW):
        raise HTTPException(status_code=429, detail="Too many requests")


async def _reconcile_loop() -> None:
    while True:
        new_tx, credited = await asyncio.to_thread(reconcile_payments_safe)
        if new_tx:
            logger.info("Фонове звіряння: +%d транзакцій, +%d кредитів", new_tx, credited)
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)


async def _holder_sync_loop() -> None:
    await asyncio.sleep(10)
    while True:
        try:
            res = await asyncio.to_thread(holder_rewards.sync_genesis_mints)
            if res.get("success"):
                if res.get("new_mints_count", 0) > 0:
                    logger.info(
                        "Фонова синхронізація холдерів: знайдено %d нових мінтів. Разом: %d",
                        res["new_mints_count"],
                        res["total_mints_count"],
                    )
            else:
                logger.warning("Помилка під час автоматичної синхронізації холдерів: %s", res.get("error"))
        except Exception as e:
            logger.error("Критична помилка у фоновому циклі синхронізації холдерів: %s", e)
        await asyncio.sleep(HOLDER_SYNC_INTERVAL_SECONDS)


async def _run_fulfillment(tx_id: str, wallet: str, kind: str, detail: str) -> None:
    sugar_root = os.environ.get("SUGAR_PROJECT_PATH", str(Path(__file__).parent.parent / "Sugar"))
    if kind != "transfer":
        logger.error("Helio NFT: непідтримуваний тип фулфілменту: %r (тільки transfer у Дропі #2)", kind)
        return

    cmd = ["node", str(Path(sugar_root) / "scripts" / "transfer-nft.mjs"), wallet, detail]
    try:
        async with _fulfillment_semaphore():
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            mark_fulfillment_done(tx_id)
            logger.info("Helio NFT %s: успіх для %s\n%s", kind, wallet, stdout.decode("utf-8", errors="replace"))
        else:
            mark_fulfillment_failed(tx_id)
            logger.error("Helio NFT %s: помилка (rc=%s) для %s\n%s", kind, proc.returncode, wallet, stderr.decode("utf-8", errors="replace"))
    except Exception as e:
        mark_fulfillment_failed(tx_id)
        logger.error("Helio NFT %s: виняток під час запуску для %s: %s", kind, wallet, e)


def _fulfillment_should_autoretry(row: dict) -> bool:
    return (
        row.get("status") == "failed"
        or row.get("kind") == "transfer"
        or FULFILLMENT_AUTORETRY_RESERVED_MINT
    )


async def _fulfillment_reconcile_loop() -> None:
    await asyncio.sleep(20)
    while True:
        try:
            pend = await asyncio.to_thread(
                pending_fulfillments, FULFILLMENT_STALE_SECONDS, FULFILLMENT_MAX_ATTEMPTS
            )
            for row in pend:
                if not _fulfillment_should_autoretry(row):
                    logger.warning(
                        "Reconcile фулфілменту: стале 'reserved' Genesis-мінт %s (гаманець %s) "
                        "потребує РУЧНОГО розгляду — авто-повтор вимкнено (ризик подвійного мінту)",
                        row["tx_id"], row["wallet"],
                    )
                    continue
                logger.warning(
                    "Reconcile фулфілменту: повтор %s (%s, спроба %d)",
                    row["tx_id"], row["kind"], row["attempts"] + 1,
                )
                await _run_fulfillment(row["tx_id"], row["wallet"], row["kind"], row["detail"])
        except Exception as e:
            logger.error("Reconcile фулфілменту: помилка циклу: %s", e)
        await asyncio.sleep(FULFILLMENT_RECONCILE_INTERVAL_SECONDS)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task: asyncio.Task | None = None
    sync_task: asyncio.Task | None = None
    fulfill_task: asyncio.Task | None = None

    if RECONCILE_INTERVAL_SECONDS > 0 and helio_keys():
        task = asyncio.create_task(_reconcile_loop())
        logger.info("Фонове звіряння платежів увімкнено (кожні %d с)", RECONCILE_INTERVAL_SECONDS)
    else:
        logger.info("Фонове звіряння вимкнено (інтервал=0 або немає HELIO-ключів)")
        
    if HOLDER_SYNC_INTERVAL_SECONDS > 0:
        sync_task = asyncio.create_task(_holder_sync_loop())
        logger.info(
            "Автоматична фонова синхронізація холдерів увімкнена (кожні %d с)",
            HOLDER_SYNC_INTERVAL_SECONDS,
        )
    else:
        logger.info("Автоматична фонова синхронізація холдерів вимкнена (інтервал=0)")

    if FULFILLMENT_RECONCILE_INTERVAL_SECONDS > 0:
        fulfill_task = asyncio.create_task(_fulfillment_reconcile_loop())
        logger.info(
            "Reconcile NFT-фулфілменту увімкнено (кожні %d с, stale=%d с, max_attempts=%d)",
            FULFILLMENT_RECONCILE_INTERVAL_SECONDS, FULFILLMENT_STALE_SECONDS, FULFILLMENT_MAX_ATTEMPTS,
        )
    else:
        logger.info("Reconcile NFT-фулфілменту вимкнено (інтервал=0)")

    try:
        yield
    finally:
        for t in (task, sync_task, fulfill_task):
            if t:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t


app = FastAPI(
    title="NFT Prompt Builder — Payments API", version="1.0.0", lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
)

_NONCE_STORE = auth_gateway.create_nonce_store()
SESSION_COOKIE = "w3ir_session"
_LOGIN_HTML = Path(__file__).parent / "ui" / "login.html"
_LANDING_HTML = Path(__file__).parent / "ui" / "landing.html"
_OG_CARD = Path(__file__).parent / "ui" / "og-card.png"
_SITEMAP = Path(__file__).parent / "ui" / "sitemap.xml"
_ROBOTS = Path(__file__).parent / "ui" / "robots.txt"

_FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<defs><linearGradient id='t' x1='0' y1='0' x2='1' y2='1'>"
    "<stop offset='0' stop-color='#6e56cf'/><stop offset='1' stop-color='#4c3a9e'/>"
    "</linearGradient></defs>"
    "<rect width='32' height='32' rx='7' fill='url(#t)'/>"
    "<path d='M16 4 L26.4 10 L26.4 22 L16 28 L5.6 22 L5.6 10 Z' fill='none' "
    "stroke='#fff' stroke-opacity='0.92' stroke-width='1.8' stroke-linejoin='round'/>"
    "<g fill='#fff'>"
    "<path d='M16 9.5 L21.6 12.75 L16 16 L10.4 12.75 Z' fill-opacity='0.96'/>"
    "<path d='M10.4 12.75 L16 16 L16 22.5 L10.4 19.25 Z' fill-opacity='0.78'/>"
    "<path d='M21.6 12.75 L16 16 L16 22.5 L21.6 19.25 Z' fill-opacity='0.6'/>"
    "</g></svg>"
)

_PAY_HOSTS = frozenset(
    h.strip().lower()
    for h in os.environ.get("PAY_SUBDOMAIN_HOSTS", "pay.w3ir.io").split(",")
    if h.strip()
)
_PAY_ALLOWED_PATHS = frozenset({"/health", "/webhooks/helio"})


def _vault_catalog_path() -> Path:
    override = (os.environ.get("VAULT_CATALOG_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).parent / "data" / "vault_catalog.json"


@app.middleware("http")
async def restrict_pay_subdomain(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if host in _PAY_HOSTS:
        path = request.url.path.rstrip("/") or "/"
        if path not in _PAY_ALLOWED_PATHS:
            return Response("Not Found", status_code=404)
    return await call_next(request)


def _verify_helio_signature(body: bytes, signature: str | None) -> bool:
    secret = os.environ.get("HELIO_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="HELIO_WEBHOOK_SECRET not configured — webhook вимкнено, зарахування лише через polling",
        )
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


_CACHE_LANDING = "public, max-age=300, stale-while-revalidate=60, stale-if-error=86400"
_CACHE_ASSET = "public, max-age=86400, stale-if-error=604800"
_CACHE_SEO = "public, max-age=3600, stale-if-error=604800"


def _require_gremlin_key(request: Request) -> None:
    if not _GREMLIN_API_KEY:
        raise HTTPException(status_code=503, detail="generator not configured")
    provided = (request.headers.get("x-gremlin-key") or "").strip()
    if not provided or not hmac.compare_digest(provided, _GREMLIN_API_KEY):
        raise HTTPException(status_code=401, detail="invalid or missing X-Gremlin-Key")


def _gremlin_generate_png(prompt: str, seed: int) -> bytes:
    import services.ai_service as ai_service

    service = ai_service.AIService()
    if service.engine_status().get(ai_service.ENGINE_FLUX):
        raise RuntimeError("flux not configured")
    try:
        return service.generate_image(
            prompt, ai_service.ENGINE_FLUX, width=1024, height=1024, seed=seed,
        )
    except ai_service.AIServiceError as e:
        raise RuntimeError(str(e)) from e


def _b2b_key(request: Request) -> str:
    return (request.headers.get("X-W3IR-B2B-Key") or "").strip()


def _require_b2b_client(request: Request) -> tuple[str, dict]:
    key = _b2b_key(request)
    client = b2b_service.verify_b2b_api_key(key)
    if not client:
        raise HTTPException(status_code=401, detail="Invalid or inactive B2B API key")
    return key, client


# Монтування модульних роутерів
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(webhooks_router)
app.include_router(gremlin_router)
app.include_router(b2b_router)

# Збереження сумісності імпортів для тестів
from routers.auth import VerifyBody  # noqa: F401, E402
from routers.gremlin import GremlinGenerateBody  # noqa: F401, E402
