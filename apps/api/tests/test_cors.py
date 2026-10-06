import httpx

from app.main import create_app

ALLOWED = "https://admin.example.com"


def _client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_no_cors_headers_by_default():
    """Sin CORS_ALLOWED_ORIGINS no se emite ninguna cabecera CORS (mismo origen)."""
    async with _client(create_app()) as c:
        resp = await c.get("/healthz", headers={"Origin": "https://evil.example.com"})
    assert resp.headers.get("access-control-allow-origin") is None


async def test_no_cors_preflight_by_default():
    async with _client(create_app()) as c:
        resp = await c.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.headers.get("access-control-allow-origin") is None


async def test_cors_allows_configured_origin():
    async with _client(create_app(cors_allowed_origins=[ALLOWED])) as c:
        resp = await c.get("/healthz", headers={"Origin": ALLOWED})
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ALLOWED
    assert resp.headers["access-control-allow-credentials"] == "true"


async def test_cors_denies_unknown_origin():
    async with _client(create_app(cors_allowed_origins=[ALLOWED])) as c:
        resp = await c.get("/healthz", headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is None


async def test_cors_preflight_for_allowed_origin():
    async with _client(create_app(cors_allowed_origins=[ALLOWED])) as c:
        resp = await c.options(
            "/api/v1/auth/login",
            headers={
                "Origin": ALLOWED,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == ALLOWED
    assert "POST" in resp.headers["access-control-allow-methods"]
    assert "x-csrf-token" in resp.headers["access-control-allow-headers"].lower()


async def test_cors_preflight_denied_for_unknown_origin():
    async with _client(create_app(cors_allowed_origins=[ALLOWED])) as c:
        resp = await c.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.headers.get("access-control-allow-origin") is None