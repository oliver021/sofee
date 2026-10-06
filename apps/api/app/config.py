from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://sofee:sofee@localhost:5432/sofee"
    testing: bool = False

    session_cookie_name: str = "sofee_session"
    session_ttl_seconds: int = 30 * 24 * 60 * 60
    session_cookie_secure: bool = False
    session_cookie_domain: str | None = None
    csrf_secret: str = "dev-csrf-secret-change-me"

    cors_allowed_origins: list[str] = []
    # IPs de proxies (nginx, LB, etc.) autorizadas a introducir X-Forwarded-For.
    # Vacío = no se confía en la cabecera (el rate limit y la auditoría usan la IP directa).
    trusted_proxies: list[str] = []

    # M7: rate limiting de /auth/login (por email y por IP).
    login_rate_limit_max_attempts: int = 5
    login_rate_limit_window_seconds: int = 15 * 60

    secret_encryption_key: str | None = None

    storage_backend: str = "local"
    storage_local_dir: str = "./storage"
    storage_max_upload_bytes: int = 25 * 1024 * 1024

    # M7: despliegue. Si se setea, anula la ruta por defecto al dist de apps/admin.
    admin_dist_dir: str | None = None
    # M8: dist de apps/web servido en la raíz del mismo origen que la API (cookies first-party).
    web_dist_dir: str | None = None
    # CSP por defecto cubre el panel SPA servido en /admin; anulable vía env
    # (p. ej. para activar nonces sin 'unsafe-inline' en script-src).
    content_security_policy: str | None = None


settings = Settings()