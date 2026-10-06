import httpx

from app.main import create_app


def _client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_security_headers_on_default_app():
    async with _client(create_app()) as c:
        resp = await c.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["x-xss-protection"] == "0"
    assert resp.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert resp.headers["cross-origin-opener-policy"] == "same-origin"
    assert resp.headers["cross-origin-resource-policy"] == "same-origin"
    assert "default-src 'self'" in resp.headers["content-security-policy"]
    # HSTS solo cuando la cookie es Secure (producción por HTTPS), nunca en dev/test.
    assert resp.headers.get("strict-transport-security") is None


async def test_hsts_when_cookies_secure():
    async with _client(create_app(hsts_enabled=True)) as c:
        resp = await c.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers["strict-transport-security"].startswith("max-age=31536000")


async def test_security_headers_apply_to_admin_static():
    """El panel SPA servido en /admin recibe las mismas cabeceras (mismo origen)."""
    async with _client(create_app()) as c:
        resp = await c.get("/admin/")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-security-policy"]


async def test_security_headers_on_error_responses():
    async with _client(create_app()) as c:
        resp = await c.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.headers["x-content-type-options"] == "nosniff"