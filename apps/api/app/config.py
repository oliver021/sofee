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

    # RAG sobre la base de conocimiento. Sin `embeddings_base_url` y `embeddings_model` el
    # agente sigue buscando solo con full-text. `embeddings_base_url` es la raíz de una API
    # compatible con OpenAI (se le añade `/embeddings`), p. ej. `http://127.0.0.1:8082/v1`.
    embeddings_base_url: str | None = None
    embeddings_model: str | None = None
    embeddings_api_key: str | None = None
    # Texto que se antepone a la consulta (no a los documentos). Los modelos de recuperación como
    # Qwen3-Embedding lo piden: `Instruct: <tarea>\nQuery: `.
    embeddings_query_prefix: str = ""
    embeddings_timeout_seconds: float = 30.0
    # Parecido coseno mínimo del mejor trozo para considerar que la base de conocimiento responde
    # a la pregunta. Depende del modelo de embeddings: 0.48 está calibrado para Qwen3-Embedding-0.6B.
    rag_min_similarity: float = 0.48
    # Un trozo se devuelve si está a menos de este margen del mejor.
    rag_similarity_margin: float = 0.12
    rag_chunk_chars: int = 900
    rag_chunk_overlap_chars: int = 150

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