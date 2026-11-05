from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .agent.executor import recover_orphaned_runs
from .agent.persistence import agent_storage_lifespan
from .api.routes import (
    admin,
    agent_admin,
    audit,
    auth,
    catalog,
    catalog_admin,
    conversations,
    integrations_admin,
    kb_admin,
    me,
    providers,
    providers_admin,
    runs,
    runs_admin,
    storage,
)
from .config import settings

# CSP por defecto (M7): cubre el panel SPA servido en /admin desde el mismo origen.
# script-src 'unsafe-inline' es necesario por el snippet anti-flash de paleta en
# index.html (apps/admin); para endurecerlo, setear CONTENT_SECURITY_POLICY con
# nonces/hashes inline.
# La web (apps/web) carga la tipografía de la paleta activa desde Google Fonts (design-system.md §4):
# solo se admiten esa hoja de estilos y sus ficheros de fuente, nada más de terceros.
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, hsts_enabled: bool) -> None:
        super().__init__(app)
        self.hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        csp = settings.content_security_policy or DEFAULT_CSP
        if csp:
            response.headers["Content-Security-Policy"] = csp
        if self.hsts_enabled:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


def _default_admin_dist_dir() -> Path:
    return Path(__file__).resolve().parents[1].parent / "admin" / "dist"


def _default_web_dist_dir() -> Path:
    return Path(__file__).resolve().parents[1].parent / "web" / "dist"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with agent_storage_lifespan(app):
        # Un proceso nuevo no tiene tareas de runs: los que quedaron en curso se cierran.
        await recover_orphaned_runs()
        yield


def create_app(
    *,
    cors_allowed_origins: list[str] | None = None,
    hsts_enabled: bool | None = None,
) -> FastAPI:
    origins = (
        settings.cors_allowed_origins
        if cors_allowed_origins is None
        else cors_allowed_origins
    )
    hsts = settings.session_cookie_secure if hsts_enabled is None else hsts_enabled

    app = FastAPI(
        title="Sofee API",
        version="0.1.0",
        description="Backend Sofee — auth por sesión, providers LLM y panel admin.",
        # Pool de psycopg del checkpointer y del store del agente (ver app/agent/persistence.py).
        lifespan=_lifespan,
    )

    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=hsts)

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(me.router, prefix="/api/v1")
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(providers.router, prefix="/api/v1")
    app.include_router(providers_admin.router, prefix="/api/v1")
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(catalog_admin.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(storage.router, prefix="/api/v1")
    app.include_router(kb_admin.router, prefix="/api/v1")
    app.include_router(integrations_admin.router, prefix="/api/v1")
    app.include_router(agent_admin.router, prefix="/api/v1")
    app.include_router(runs_admin.router, prefix="/api/v1")

    admin_dir = (
        Path(settings.admin_dist_dir)
        if settings.admin_dist_dir
        else _default_admin_dist_dir()
    )
    if admin_dir.exists():
        app.mount("/admin", StaticFiles(directory=admin_dir, html=True), name="admin")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # M8: apps/web on the same origin (decision 3). Mounted last so every /api/v1 route and
    # /healthz win; unknown /api paths still 404 (StaticFiles only serves index.html for
    # directory requests, not for missing files). Same-origin means session cookies are
    # first-party and no CORS config is needed for the web app.
    web_dir = (
        Path(settings.web_dist_dir) if settings.web_dist_dir else _default_web_dist_dir()
    )
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


app = create_app()