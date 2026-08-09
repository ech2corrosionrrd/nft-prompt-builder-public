"""Тести структури модульних роутерів api_server.

Перевіряє, що всі необхідні роутери підключені до FastAPI застосунку
і кінцеві точки зареєстровані з очікуваними HTTP-методами.

ЛАНДМАЙН. Шляхи беремо з `app.openapi()`, а НЕ з `app.routes` з `r.path`/`r.methods`.
`starlette` — транзитивна залежність (`requirements.txt` пінить лише fastapi), і CI
підтягнув 1.3.1, поки локально стояла 0.52.1. У starlette 1.x `include_router`
загортає маршрути у приватний `fastapi.routing._IncludedRouter`, який `.path`/
`.methods` уже НЕ має: `hasattr(r, "path")` дає False, комприхеншен відфільтровує
геть усе, і перевірка перетворюється на `assert "/health" in {}` — тест червонів у
CI, лишаючись зеленим локально. `app.openapi()` — публічний API FastAPI, віддає
однаковий словник шляхів і методів в обох версіях.
"""

from fastapi.testclient import TestClient
from api_server import app

# Мінімальний контракт публічної поверхні API: шлях → методи, які МАЮТЬ бути.
EXPECTED_ROUTES = {
    "/health": {"GET"},
    "/": {"GET"},
    "/login": {"GET"},
    "/auth/nonce": {"GET"},
    "/auth/verify": {"POST"},
    "/webhooks/helio": {"POST"},
    "/gremlin/holder": {"GET"},
    "/gremlin/generate": {"POST"},
    "/api/vault/status": {"GET"},
    "/api/v1/launchpad/inspect-bundle": {"POST"},
    "/api/v1/b2b/status": {"GET"},
}


def _openapi_routes() -> dict[str, set[str]]:
    """Шлях → множина HTTP-методів, з публічної схеми FastAPI."""
    return {
        path: {method.upper() for method in operations}
        for path, operations in app.openapi()["paths"].items()
    }


def test_health_endpoint_responds():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_routers_registered_endpoints():
    routes = _openapi_routes()
    missing = [path for path in EXPECTED_ROUTES if path not in routes]
    assert not missing, f"роутери не змонтовано: {missing}"


def test_registered_endpoints_expose_expected_methods():
    """Метод так само важливий, як шлях: webhook, що відповідає лише на GET,
    змонтований, але непрацездатний."""
    routes = _openapi_routes()
    wrong = {
        path: sorted(routes[path])
        for path, methods in EXPECTED_ROUTES.items()
        if path in routes and not methods <= routes[path]
    }
    assert not wrong, f"невідповідні HTTP-методи: {wrong}"


def test_public_router_health():
    from routers.public import health
    res = health()
    assert res == {"status": "ok", "service": "nft-prompt-builder-payments"}


def test_routers_never_use_from_api_server_import():
    """Цикл api_server ↔ routers тримається лише на відкладеному доступі.

    `import api_server` зв'язується з напівімпортованим модулем і читає атрибут
    у момент запиту — цикл не рветься. `from api_server import X` виконує
    зчитування ВЖЕ на імпорті, коли потрібного імені в модулі ще немає, і валить
    застосунок ImportError-ом на старті. Різниця невидима при читанні коду, тож
    ловимо її тут, а не в проді.
    """
    import ast
    from pathlib import Path

    routers_dir = Path(__file__).resolve().parent.parent / "routers"
    offenders = []
    for path in sorted(routers_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "api_server":
                names = ", ".join(a.name for a in node.names)
                offenders.append(f"{path.name}:{node.lineno} → from api_server import {names}")

    assert not offenders, (
        "У роутерах дозволено лише `import api_server`:\n  " + "\n  ".join(offenders)
    )
