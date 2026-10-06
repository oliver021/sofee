# Sofee — Plan de ejecución y tracking

Documento de tracking basado en [`docs/backend-plan.md`](./backend-plan.md).
Cada milestone agrupa un entregable verificable; el checkbox solo se marca
cuando está **implementado, testeado y funcionando**.

## Decisiones tomadas

| #   | Pregunta (plan §16)                          | Decisión                                                                                                                                                  |
| --- | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | ¿`apps/web` necesita cuentas ya?             | **No por ahora**. El backend arranca sirviendo primero al panel de admin (login propio + providers). La integración con `apps/web` es una fase posterior. |
| 2   | ¿Hosting de Postgres?                        | **Docker Compose local** para desarrollo/aprovisionamiento; `DATABASE_URL` vía variable de entorno.                                                       |
| 3   | ¿`apps/admin` en mismo dominio o subdominio? | **Mismo dominio** (servido por `apps/api`), p. ej. el panel en `/admin`. Cookie sin dominios cruzados ni `SameSite` complejo; CORS del mismo origen.      |

## Orden de ejecución

El §15 del plan sugería fases. Con las decisiones de arriba, el orden es:

1. **M1 — Fundaciones** (back first, sin providers)
2. **M2 — Biblioteca de providers**
3. **M3 — Auditoría**
4. **M4 — Almacenamiento**
5. **M5 — Panel admin MVP** (providers + usuarios)
6. **M6 — Panel admin completo** (auditoría, modelos, sesiones)
7. **M7 — Endurecimiento y despliegue**
8. **M8 — Integración con `apps/web`** (fase nueva a partir de la decisión 1)

---

## M1 — Fundaciones del backend

**Objetivo:** `apps/api` corriendo con autenticación de sesión server-side.
**✅ Completado** — 22 tests pasando.

- [x] Docker Compose con PostgreSQL para desarrollo
- [x] Scaffolding `apps/api` (FastAPI, uv, estructura de paquetes)
- [x] Config por variable de entorno (`DATABASE_URL`, cookie, CORS)
- [x] Conexión SQLAlchemy 2.0 async + `asyncpg`
- [x] Modelos `users` + `sessions`
- [x] Alembic + migración inicial
- [x] Seguridad: Argon2id, cookies `httpOnly`/`Secure`/`SameSite`, CSRF
- [x] Endpoints: login, logout, `me`, `me/sessions`
- [x] Dependencias `require_user` / `require_admin`
- [x] Tests de auth (login/logout/expiración/revocación/RBAC 403)

## M2 — Biblioteca de providers

**Objetivo:** CRUD de proveedores LLM con cifrado de secretos.
**✅ Completado** — 60 tests pasando en total (M1+M2).

- [x] Modelos `providers`, `provider_credentials`, `provider_models`
- [x] Cifrado Fernet de API keys + clave maestra por env (`SECRET_ENCRYPTION_KEY`)
- [x] `ProviderAdapter` (Protocol) + `OpenAICompatibleAdapter`
- [x] Registro de adaptadores por `kind` (Vercel GW / DeepInfra / NVIDIA NIM comparten la impl base)
- [x] CRUD admin endpoints + test de conexión (`POST .../test`)
- [x] Rotación de credenciales (la anterior pasa a inactiva, nunca se borra)
- [x] Sync + toggle de modelos por proveedor
- [x] `GET /providers/models` para selector de `apps/web` (solo habilitados, sin secretos/URLs)

## M3 — Auditoría

**Objetivo:** toda mutación relevante queda registrada (append-only).
**✅ Completado** — 80 tests pasando en total (M1+M2+M3).

- [x] Tabla `audit_log`
- [x] Helper de escritura reusado por M1 y M2 (retroactivo)
- [x] `GET /admin/audit` con filtros + paginación por cursor
- [x] Tests: cada mutación deja exactamente la fila esperada

## M4 — Almacenamiento

**Objetivo:** subida/descarga/borrado de adjuntos.
**✅ Completado** — 92 tests pasando en total (M1+M2+M3+M4).

- [x] Interfaz `StorageBackend`
- [x] `LocalDiskBackend` (default dev)
- [x] Modelo `storage_objects`
- [x] Endpoints `POST/GET/DELETE /storage`
- [x] Tests de subida/descarga/borrado

## M5 — Panel admin MVP

**Objetivo:** login + gestión de providers y usuarios.
**✅ Completado** — 105 tests pasando en total (M1+M2+M3+M4+M5).

- [x] Scaffolding `apps/admin` (Svelte 5 + Vite, mismo dominio; `base=/admin/`, proxy `/api` en dev, mount estático en `apps/api`)
- [x] Login (comparte `POST /auth/login`) + CSRF del lado del cliente (`csrf_token` en login y `GET /auth/csrf`)
- [x] Vista Providers: tabla, alta/edición, test conectividad, rotar credencial
- [x] Vista Usuarios: tabla (+búsqueda `q`), cambio de rol, activar/desactivar (`PATCH /admin/users/{id}` con auditoría `user.role_changed` / `user.deactivated` / `user.activated` y guardas anti-bloqueo sobre el propio admin)
- [x] Sigue la decisión 3: mismo dominio; el build de `apps/admin` se sirve en `/admin` cuando `dist/` existe

## M6 — Panel admin completo

**Objetivo:** auditoría y gestión fina de sesiones/modelos.
**✅ Completado** — 116 tests pasando en total (M1…M6).

- [x] Vista Auditoría (filtrable por acción/recurso + paginación por cursor)
- [x] Toggles de modelos por proveedor (+ sync desde el panel)
- [x] "Sesiones activas" por usuario con revocación (`GET /admin/users/{id}/sessions`, `DELETE /admin/sessions/{id}`, `POST /admin/users/{id}/revoke-sessions` con auditoría `session.revoked` / `user.sessions_revoked` y guardas anti-bloqueo)
- [x] Sesión caducada en el panel → vuelve automáticamente al login (handler de 401 en el cliente)

## M7 — Endurecimiento y despliegue

**Objetivo:** seguridad y operación production-ready.
**✅ Completado** — 166 tests pasando en total (M1…M7).

- [x] Rate limiting en `/auth/login` (por IP y por email, tabla `login_attempts`, ventana deslizante, `429` + `Retry-After`)
- [x] Cabeceras de seguridad (middleware: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `COOP`, `CORP`, CSP; HSTS cuando la cookie es Secure)
- [x] Revisión CORS (solo se activa con orígenes explícitos; `TRUSTED_PROXIES` para no dejarse spoofear `X-Forwarded-For` en rate limit/auditoría)
- [x] Tests de autorización negativa (403 vs 404) parametrizados sobre todo `/api/v1/admin/*`
- [x] Dockerfile `apps/api` (imagen única con el `dist` de `apps/admin`) + migraciones como paso de release (`migrate` ≠ arranque web)
- [x] Runbook de despliegue ([`docs/deployment.md`](./deployment.md))
- [x] `httpx` movido a dependencia de runtime (lo usan los adaptadores de provider; faltaba en la imagen)

## M8 — Integración `apps/web`

**Objetivo:** `apps/web` con login real, persistencia y selector de modelo.
**✅ Completado** — 193 tests pasando en total (M1…M8).

- [x] Login/registro en `apps/web` contra la misma API (`POST /auth/register` nuevo, `user.created` en auditoría, mismo rate limit que login; pantalla de auth con copy i18n y mapeo de errores 401/409/400/429)
- [x] Persistencia de conversaciones (tablas `threads` + `messages`, endpoints `GET/POST/PATCH/DELETE /threads` y `POST/DELETE /threads/{id}/messages`; el frontend sincroniza por `client_id` con upserts idempotentes y cola por hilo)
- [x] Selector de modelo consumiendo `GET /providers/models` (en Configuración; elección en `localStorage`; `id = provider_id:model_id`)
- [x] Adjuntos vía `/storage` (subida multipart al elegir/soltar archivo, `attachment_ids` persistidos en el mensaje, URL de descarga same-origin)
- [x] `apps/web` servido en la raíz `/` por `apps/api` (decisión 3: cookies first-party; proxy `/api` en dev)

---

## Notas de ejecución

- El estado real se actualiza en este mismo archivo a medida que se avanza.
- `apps/api` es Python gestionado con `uv`, fuera de los workspaces npm.
- Postgres se levanta con `docker compose up -d postgres postgres-test` (ver `docker-compose.yml`).

### Backend — comandos de uso

```bash
cd apps/api
uv sync                       # instalar dependencias
uv run alembic upgrade head   # aplicar migraciones
docker compose up -d postgres # (desde la raíz) levantar Postgres
uv run uvicorn app.main:app --reload   # dev server en http://localhost:8000

# seed del primer admin:
uv run python -m app.cli create-admin --email admin@sofee.app --password '...'

# tests (usa el contenedor postgres-test en el puerto 5433):
uv run pytest
```

### Panel admin — comandos de uso (M5)

```bash
npm run build:admin     # build de apps/admin (tokens + admin) → apps/admin/dist
npm run dev:admin       # Vite en http://localhost:5174/admin/ con proxy /api → :8000
npm run typecheck -w @sofee/admin   # svelte-check estricto
```

Producción (decisión 3): con `apps/admin/dist/` presente, `apps/api` sirve el
panel en `/admin` automáticamente (mount en `app/main.py`).

### App web — comandos de uso (M8)

```bash
npm run build           # build de apps/web (tokens + web) → apps/web/dist
npm run dev             # Vite en http://localhost:5173 con proxy /api → :8000
npm run typecheck -w @sofee/web   # svelte-check estricto
```

Producción (decisión 3): con `apps/web/dist/` presente, `apps/api` sirve la app
en `/` (mismo origen que la API) automáticamente; la imagen Docker copia ambos
`dist` y los expone con `ADMIN_DIST_DIR` / `WEB_DIST_DIR`.
