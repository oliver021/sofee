import os
from pathlib import Path

os.environ["DATABASE_URL"] = "postgresql+asyncpg://sofee:sofee@localhost:5433/sofee_test"
os.environ["TESTING"] = "true"
os.environ["CSRF_SECRET"] = "test-csrf-secret"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STORAGE_LOCAL_DIR"] = "/tmp/sofee-test-storage"
os.environ["STORAGE_MAX_UPLOAD_BYTES"] = "1024"
os.environ["TRUSTED_PROXIES"] = '["127.0.0.1"]'

import shutil  # noqa: E402
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.csrf import derive_csrf_token  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.agent.persistence import reset_in_memory_storage  # noqa: E402
from app.db import async_session_factory  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def apply_migrations():
    config = Config(str(API_DIR / "alembic.ini"))
    command.upgrade(config, "head")
    yield


def _clear_storage_dir() -> None:
    root = Path(settings.storage_local_dir).resolve()
    if root.exists():
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        root.mkdir(parents=True, exist_ok=True)


@pytest_asyncio.fixture(autouse=True)
async def clean_db(apply_migrations):
    _clear_storage_dir()
    reset_in_memory_storage()
    yield
    _clear_storage_dir()
    async with async_session_factory() as db:
        await db.execute(
            text(
                "TRUNCATE users, sessions, providers, provider_credentials, "
                "provider_models, model_catalog_entries, model_catalog_bindings, "
                "audit_log, storage_objects, login_attempts, agent_profiles, "
                "agent_runs, agent_run_events, message_feedback, app_settings, "
                "kb_documents, integration_credentials "
                "RESTART IDENTITY CASCADE"
            )
        )
        await db.commit()


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def make_user():
    async def _make(
        email: str = "user@example.com",
        password: str = "password123",
        role: UserRole = UserRole.regular,
        display_name: str = "Test User",
        is_active: bool = True,
    ) -> User:
        async with async_session_factory() as db:
            user = User(
                email=email,
                password_hash=hash_password(password),
                display_name=display_name,
                role=role,
                is_active=is_active,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return user

    return _make


@pytest_asyncio.fixture
async def login(client, make_user):
    async def _login(email: str = "user@example.com") -> str:
        await make_user(email=email)
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["user"]

    return _login


def csrf_from_client(client: httpx.AsyncClient) -> str:
    sid = uuid.UUID(client.cookies.get("sofee_session"))
    return derive_csrf_token(sid)