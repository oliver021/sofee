# Plan: backend FastAPI + panel de administración

Este documento es un plan de arquitectura e implementación para un backend nuevo
que hoy no existe (el README es explícito: _"There is no backend"_). Cubre:
usuarios, sesiones, roles (`regular` / `admin`), almacenamiento, una biblioteca de
_providers_ de LLM (Vercel AI Gateway, DeepInfra, NVIDIA NIM, endpoints
compatibles con OpenAI), y un frontend de administración separado para gestionar
esa biblioteca, los usuarios y la auditoría.

Es **solo el plan** — no incluye código. Sirve de referencia para desglosar el
trabajo en tareas o PRs concretos.

## 1. Objetivos y alcance

**Objetivos**

- Dar a `apps/web` un backend real: autenticación de usuarios, persistencia de
  conversaciones/adjuntos, y una fuente de verdad para qué proveedor de modelo
  usar en cada request (hoy `packages/core/src/mock` simula todo esto).
- Permitir que un administrador gestione, sin tocar código ni variables de
  entorno a mano, la biblioteca de proveedores (altas, bajas, credenciales,
  qué modelos expone cada uno) desde un panel propio.
- Separar con claridad "usuario regular" (usa `apps/web`) de "admin" (usa el
  panel nuevo) a nivel de autenticación, autorización y superficie de API.
- Dejar todo movimiento sensible (cambios de credenciales, de usuarios, de
  roles) con registro de auditoría consultable.

**Fuera de alcance (por ahora)**

- Facturación/cuotas de uso por proveedor.
- Multi-tenant (varias organizaciones aisladas) — se diseña con roles simples,
  no con "organizations"; se anota como extensión futura donde aplica.
- SSO/OAuth externo (Google, GitHub, etc.) — login propio con email+contraseña
  primero; se deja el modelo de datos abierto para añadirlo después.

## 2. Arquitectura general

Dos superficies HTTP nuevas sobre un mismo backend FastAPI, más un frontend de
administración aparte:

```
apps/
  web/          (existente) — app de usuario regular, Svelte 5
  admin/        (nuevo) — panel de administración, Svelte 5 + Vite
  api/          (nuevo) — backend FastAPI (Python), sirve ambos frontends
```

- **`apps/api`** expone dos grupos de rutas bajo el mismo proceso pero con
  guards distintos: `/api/v1/*` (usuario regular, requiere sesión con rol
  `regular` o `admin`) y `/api/v1/admin/*` (solo rol `admin`). Un solo
  servicio es más simple de operar que dos; el aislamiento es a nivel de
  autorización, no de proceso.
- **`apps/admin`** es una SPA separada de `apps/web` (deploy y dominio propios,
  p. ej. `admin.sofee.app`), para que un usuario regular nunca reciba ni un
  byte del bundle de administración. Reutiliza `packages/tokens` (y
  posiblemente `packages/icons`) para no reinventar la identidad visual, pero
  **no** depende de `packages/ui`, que es específico del chat.
- `apps/api` no entra en los `workspaces` de npm (es Python); vive en el mismo
  monorepo con su propio `pyproject.toml`, gestionado con `uv` (rápido,
  lockfile determinista, buen soporte para apps FastAPI).

## 3. Stack tecnológico propuesto

| Capa                                        | Elección                                                                          | Motivo                                                                                                |
| ------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Framework                                   | FastAPI                                                                           | pedido explícitamente; async nativo, OpenAPI gratis                                                   |
| Validación                                  | Pydantic v2                                                                       | ya integrado en FastAPI, rápido                                                                       |
| ORM                                         | SQLAlchemy 2.0 (async)                                                            | maduro, tipado, buen soporte async con `asyncpg`                                                      |
| Migraciones                                 | Alembic                                                                           | estándar de facto con SQLAlchemy                                                                      |
| Base de datos                               | PostgreSQL                                                                        | JSONB para metadata de auditoría/proveedores, buen soporte de índices parciales para expirar sesiones |
| Cache/sesión rápida (opcional)              | Redis                                                                             | solo si se necesita rate-limiting o pub/sub; no bloqueante para el MVP                                |
| Hashing de contraseñas                      | `argon2-cffi` (Argon2id)                                                          | recomendado sobre bcrypt para nuevos sistemas                                                         |
| Cifrado de secretos (API keys de providers) | `cryptography` (Fernet) con clave maestra en variable de entorno / secret manager | las API keys de los providers son el dato más sensible del sistema                                    |
| Gestor de paquetes Python                   | `uv`                                                                              | lockfile, instalación rápida, buen ajuste con FastAPI moderno                                         |
| Contenedor                                  | Docker, imagen `python:3.12-slim`                                                 | despliegue reproducible                                                                               |
| Testing                                     | `pytest` + `httpx.AsyncClient` + `pytest-asyncio`                                 | estándar FastAPI                                                                                      |
| Frontend admin                              | Svelte 5 + Vite + TypeScript                                                      | consistencia con el resto del repo, sin reescribir stack                                              |

## 4. Modelo de datos

Entidades principales (nombres de tabla en `snake_case`):

### `users`

| Campo                      | Tipo                     | Notas                       |
| -------------------------- | ------------------------ | --------------------------- |
| `id`                       | UUID pk                  |                             |
| `email`                    | text, unique             | login                       |
| `password_hash`            | text                     | Argon2id                    |
| `display_name`             | text                     |                             |
| `role`                     | enum(`regular`, `admin`) | ver §6 para diseño de roles |
| `is_active`                | bool                     | desactivar sin borrar       |
| `created_at`, `updated_at` | timestamptz              |                             |
| `last_login_at`            | timestamptz nullable     |                             |

### `sessions`

Sesiones del lado servidor (no JWT stateless — ver §5 para el porqué).

| Campo                      | Tipo                 | Notas                              |
| -------------------------- | -------------------- | ---------------------------------- |
| `id`                       | UUID pk              | valor opaco enviado como cookie    |
| `user_id`                  | UUID fk → `users`    |                                    |
| `created_at`               | timestamptz          |                                    |
| `expires_at`               | timestamptz          | sliding expiration al usarse       |
| `revoked_at`               | timestamptz nullable | logout / revocación admin          |
| `user_agent`, `ip_address` | text                 | mostrado en "dispositivos activos" |

### `providers`

La "biblioteca de proveedores" que administra el panel.

| Campo                                    | Tipo                                                                   | Notas                                                                |
| ---------------------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `id`                                     | UUID pk                                                                |                                                                      |
| `name`                                   | text                                                                   | nombre visible, p. ej. "DeepInfra prod"                              |
| `kind`                                   | enum(`vercel_gateway`, `deepinfra`, `nvidia_nim`, `openai_compatible`) | determina el adaptador (§7)                                          |
| `base_url`                               | text nullable                                                          | requerido para `openai_compatible`; opcional/derivado para los demás |
| `is_enabled`                             | bool                                                                   | permite deshabilitar sin borrar                                      |
| `default_headers`                        | jsonb                                                                  | headers extra si el proveedor los necesita                           |
| `created_by`, `created_at`, `updated_at` |                                                                        |                                                                      |

### `provider_credentials`

Separada de `providers` a propósito: permite rotar/auditar credenciales sin
tocar la config del proveedor, y no expone el secreto en el mismo `SELECT *`
que usa el resto del panel.

| Campo                      | Tipo                  | Notas                                                |
| -------------------------- | --------------------- | ---------------------------------------------------- |
| `id`                       | UUID pk               |                                                      |
| `provider_id`              | UUID fk → `providers` |                                                      |
| `secret_ciphertext`        | bytea                 | API key cifrada con Fernet                           |
| `last_four`                | text                  | para mostrar `sk-...ab12` en el panel sin descifrar  |
| `is_active`                | bool                  | soporta credencial "de respaldo" sin borrar la vieja |
| `created_by`, `created_at` |                       |                                                      |

### `provider_models`

Qué modelos expone cada proveedor (para poblar selects en `apps/web` y para
que el admin habilite/deshabilite modelos concretos).

| Campo          | Tipo    | Notas                                                                               |
| -------------- | ------- | ----------------------------------------------------------------------------------- |
| `id`           | UUID pk |                                                                                     |
| `provider_id`  | UUID fk |                                                                                     |
| `model_id`     | text    | id tal como lo espera el proveedor, p. ej. `meta-llama/Meta-Llama-3.1-70B-Instruct` |
| `display_name` | text    |                                                                                     |
| `is_enabled`   | bool    |                                                                                     |

### `storage_objects`

Metadata de archivos subidos (adjuntos de conversación, exports, etc.); los
bytes viven en el backend de storage elegido (§8), no en Postgres.

| Campo                                    | Tipo                 | Notas                               |
| ---------------------------------------- | -------------------- | ----------------------------------- |
| `id`                                     | UUID pk              |                                     |
| `owner_id`                               | UUID fk → `users`    |                                     |
| `storage_key`                            | text                 | ruta/clave en el backend de storage |
| `filename`, `content_type`, `size_bytes` |                      |                                     |
| `created_at`                             | timestamptz          |                                     |
| `deleted_at`                             | timestamptz nullable | borrado lógico                      |

### `audit_log`

Append-only; ninguna ruta de la API la actualiza ni borra filas, solo inserta.

| Campo                          | Tipo                        | Notas                                                     |
| ------------------------------ | --------------------------- | --------------------------------------------------------- |
| `id`                           | bigint pk (serial)          | orden de inserción importa                                |
| `actor_id`                     | UUID fk → `users`, nullable | null para eventos del sistema                             |
| `action`                       | text                        | p. ej. `provider.credential.rotated`, `user.role.changed` |
| `resource_type`, `resource_id` | text                        | polimórfico simple                                        |
| `metadata`                     | jsonb                       | diff antes/después cuando aplica                          |
| `ip_address`                   | text                        |                                                           |
| `created_at`                   | timestamptz                 | índice principal de consulta                              |

## 5. Autenticación y sesiones

- **Sesiones server-side, no JWT.** El pedido menciona "sessiones" explícitamente,
  y para un panel de admin que maneja credenciales de proveedores, la
  revocación inmediata (logout forzado, "cerrar todas las sesiones") importa
  más que evitar un lookup a base de datos por request. Cookie `httpOnly`,
  `Secure`, `SameSite=Lax` con el `session.id` como valor opaco.
- Login: `POST /api/v1/auth/login` (email + password) → crea fila en
  `sessions`, setea cookie. Rate-limit por IP y por email para frenar
  fuerza bruta.
- Logout: `POST /api/v1/auth/logout` → `revoked_at = now()`.
- "Sesiones activas": `GET /api/v1/me/sessions` lista dispositivos; el usuario
  (o un admin sobre cualquier usuario) puede revocar una sesión puntual.
- Sliding expiration: cada request válido extiende `expires_at`; una tarea
  periódica (o un `DELETE ... WHERE expires_at < now()` perezoso) limpia
  sesiones vencidas.
- CSRF: como la auth es por cookie, las rutas mutantes (`POST`/`PATCH`/`DELETE`)
  exigen un header `X-CSRF-Token` que se valida contra un valor derivado de la
  sesión (patrón _double submit cookie_).
- Contraseñas: Argon2id, políticas mínimas (largo, no reutilizar el email),
  sin límites artificiales de "debe tener un símbolo" (evidencia de que
  degradan la seguridad real).

## 6. Roles y autorización

MVP: un enum de dos valores en `users.role`, suficiente para lo pedido
(`regular`, `admin`). Autorización vía dependencias de FastAPI:

```
require_user      -> cualquier sesión válida
require_admin     -> sesión válida y role == "admin"
```

Diseño deliberadamente simple en vez de una tabla de permisos genérica: no hay
pedido de roles intermedios (p. ej. "moderador") todavía, y una tabla de
permisos sin un segundo caso de uso real es complejidad especulativa. Si
aparece un tercer rol, el punto de extensión es claro: `role` pasa de enum a
fk hacia una tabla `roles`, y las dependencias de FastAPI pasan de comparar
un string a chequear un set de permisos — sin tocar el resto del sistema.

Toda ruta bajo `/api/v1/admin/*` usa `require_admin`; toda mutación relevante
(no solo en `/admin`) escribe una fila en `audit_log` en la misma transacción
que el cambio de negocio, para que auditoría y dato nunca diverjan.

## 7. Biblioteca de providers

Un **adaptador por `kind`**, detrás de una interfaz común, para que
`apps/web` (y el resto del backend) le pida "una respuesta de este modelo" sin
saber si por debajo hay Vercel AI Gateway, DeepInfra, NVIDIA NIM o un endpoint
OpenAI-compatible genérico:

```
class ProviderAdapter(Protocol):
    async def list_models(self) -> list[ModelInfo]: ...
    async def test_connection(self) -> ConnectionCheckResult: ...
    async def chat_completion(self, request: ChatRequest) -> ChatResponse: ...
    async def chat_completion_stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]: ...
```

- `vercel_gateway`, `deepinfra`, `nvidia_nim`: todos exponen una API
  compatible con el formato de chat completions de OpenAI (con matices en
  base URL, headers de auth y algún campo). En la práctica, tres de los
  cuatro `kind` comparten una sola implementación base
  (`OpenAICompatibleAdapter`) parametrizada por `base_url` y esquema de
  headers; `openai_compatible` es esa misma clase con `base_url` provisto
  por el admin en vez de fijo por código. Confirmar esto durante la
  implementación (revisar la doc de cada proveedor) antes de decidir si de
  verdad son cuatro `kind` o si dos colapsan en uno.
- El adaptador se resuelve por `provider.kind` en un registro simple
  (`{kind: AdapterClass}`), no por herencia dinámica ni plugins — no hay
  pedido de providers de terceros instalables en caliente.
- **Test de conexión desde el panel**: botón "Probar" en el admin dispara
  `POST /api/v1/admin/providers/{id}/test`, que llama a `test_connection()`
  (típicamente un `list_models` liviano o un ping) y devuelve éxito/error sin
  exponer el secreto en la respuesta.
- **Rotación de credenciales**: `POST /api/v1/admin/providers/{id}/credentials`
  crea una fila nueva en `provider_credentials`, marca la anterior
  `is_active = false` (no se borra: queda en auditoría vía `last_four`), y
  registra el evento en `audit_log`. El descifrado del secreto ocurre solo en
  el momento de hacer la llamada saliente al proveedor, nunca se devuelve al
  frontend.
- Selección de modelo en `apps/web`: expone `GET /api/v1/providers/models`
  (solo `provider_models` con `is_enabled=true` de providers `is_enabled=true`,
  sin credenciales ni URLs internas) para poblar el selector de modelo del
  usuario regular.

## 8. Almacenamiento

Interfaz `StorageBackend` con dos implementaciones desde el día uno (para no
acoplar el resto del sistema a una):

```
class StorageBackend(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    async def presigned_url(self, key: str, expires_in: int) -> str | None: ...
```

- **`LocalDiskBackend`**: default en desarrollo y en despliegues de un solo
  nodo; escribe bajo un directorio configurable, `presigned_url` devuelve
  `None` (se sirve por una ruta propia de la API con auth).
- **`S3CompatibleBackend`** (via `boto3`/`aiobotocore`, apunta a S3, R2,
  MinIO, etc.): para despliegues que necesitan escalar horizontalmente sin
  disco compartido. `presigned_url` habilita descarga directa sin pasar por
  el backend.
- `storage_objects.owner_id` liga cada archivo a un usuario; el borrado de
  cuenta (si se implementa) puede barrer sus objetos por esa fk.
- Cuotas por usuario: fuera de alcance del MVP, pero el modelo ya soporta
  `SUM(size_bytes) WHERE owner_id = ...` para sumarlas después sin migrar nada.

## 9. Auditoría

- Tabla `audit_log` (§4), _append-only_, sin endpoint de borrado ni de
  edición expuesto — ni siquiera para admins.
- Eventos mínimos a cubrir en el MVP:
  - `user.created`, `user.role_changed`, `user.deactivated`, `user.login_failed`
  - `session.revoked`
  - `provider.created`, `provider.updated`, `provider.deleted`, `provider.credential_rotated`, `provider.model_toggled`
- `GET /api/v1/admin/audit` con filtros por `actor_id`, `action`, rango de
  fechas y paginación por cursor (no `OFFSET`, para que no degrade con el
  tiempo).
- Retención: por defecto indefinida (es el registro legal/forense del panel);
  si el volumen lo justifica más adelante, partición por mes en Postgres es
  el siguiente paso natural — no diseñar eso ahora sin datos de volumen real.

## 10. Superficie de API (resumen)

```
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/me
GET    /api/v1/me/sessions
DELETE /api/v1/me/sessions/{id}

GET    /api/v1/providers/models          (solo lectura, providers habilitados)

POST   /api/v1/storage                    (subir archivo)
GET    /api/v1/storage/{id}
DELETE /api/v1/storage/{id}

# --- admin only, todas bajo require_admin ---
GET    /api/v1/admin/users
POST   /api/v1/admin/users
PATCH  /api/v1/admin/users/{id}           (rol, is_active, etc.)
DELETE /api/v1/admin/users/{id}

GET    /api/v1/admin/providers
POST   /api/v1/admin/providers
PATCH  /api/v1/admin/providers/{id}
DELETE /api/v1/admin/providers/{id}
POST   /api/v1/admin/providers/{id}/test
POST   /api/v1/admin/providers/{id}/credentials
PATCH  /api/v1/admin/providers/{id}/models/{model_id}   (toggle is_enabled)

GET    /api/v1/admin/audit
```

## 11. Frontend de administración (`apps/admin`)

- Vite + Svelte 5 + TypeScript, espejo de la config de `apps/web`
  (`packages/config` ya centraliza tsconfig/ESLint/Prettier — se reutiliza tal
  cual).
- Reutiliza `packages/tokens` para que el panel se sienta parte de la misma
  familia visual sin ser el mismo producto; no reutiliza `packages/ui`
  (acoplado al chat) — sus componentes (tablas, formularios, drawers) son
  propios de `apps/admin`, al menos hasta que exista un segundo consumidor
  real que justifique extraerlos a un paquete compartido.
- Vistas mínimas:
  1. **Login** (comparte el mismo `POST /auth/login`; el backend decide si la
     sesión resultante puede entrar al panel según `role`).
  2. **Providers**: tabla con `kind`, estado, último test de conexión; drawer
     de alta/edición; acción "rotar credencial"; sub-vista de modelos por
     proveedor con toggles.
  3. **Usuarios**: tabla con búsqueda, cambio de rol, activar/desactivar,
     forzar cierre de sesión.
  4. **Auditoría**: tabla filtrable/paginada de `audit_log`, de solo lectura.
- Todas las rutas del panel verifican `role == "admin"` también en el
  cliente (UX: redirigir antes de pedir datos), pero la autorización real
  vive en el backend — el frontend nunca es la barrera de seguridad.

## 12. Seguridad — checklist transversal

- Secretos de proveedores: cifrados en reposo (Fernet), nunca en logs, nunca
  devueltos completos por la API (solo `last_four`).
- Clave maestra de cifrado fuera del repo y fuera de la base de datos
  (variable de entorno inyectada por el orquestador de despliegue, o un
  secret manager si el hosting lo ofrece).
- CORS: `apps/web` y `apps/admin` como orígenes explícitos permitidos;
  `allow_credentials=True` solo para esos orígenes.
- Rate limiting en `/auth/login` (por IP y por email) para frenar fuerza
  bruta; ver si alcanza con una tabla de intentos o si conviene Redis.
- Cabeceras de seguridad estándar (`X-Content-Type-Options`,
  `Referrer-Policy`, etc.) vía middleware.
- Todas las rutas admin bajo `require_admin` cubiertas por tests que
  confirmen que un usuario `regular` recibe 403, no 404 (evita filtrar por
  timing/side-channel qué rutas existen).

## 13. Testing

- `pytest` + `httpx.AsyncClient` contra la app FastAPI real (sin mocks de
  framework), base de datos de test en contenedor Postgres efímero.
- Cobertura mínima por área: auth (login/logout/expiración/revocación), RBAC
  (403 para regular en rutas admin), adaptadores de provider (con HTTP
  mockeado vía `respx`, sin llamar a proveedores reales en CI), auditoría
  (cada mutación relevante deja exactamente una fila esperada).
- `apps/admin`: mismo patrón que `apps/core` hoy (Vitest) para lógica no
  trivial (formateo, validación de formularios); no se apunta a cobertura
  exhaustiva de UI en el MVP.

## 14. Despliegue

- `apps/api`: Dockerfile propio, migraciones de Alembic como paso de release
  (no en el arranque del proceso web, para no correrlas N veces con réplicas).
- Variables de entorno mínimas: `DATABASE_URL`, `SECRET_ENCRYPTION_KEY`,
  `SESSION_COOKIE_DOMAIN`, `CORS_ALLOWED_ORIGINS`, `STORAGE_BACKEND`
  (`local` | `s3`) y sus credenciales si es `s3`.
- `apps/admin` se construye y despliega como sitio estático (mismo patrón que
  `apps/web`, pero en su propio dominio/subdominio).

## 15. Fases sugeridas

1. **Fundaciones**: scaffolding de `apps/api` (FastAPI, config, conexión a
   Postgres, Alembic), modelo `users` + `sessions`, login/logout, `require_user`
   / `require_admin`. Sin providers todavía.
2. **Biblioteca de providers**: modelos `providers` / `provider_credentials` /
   `provider_models`, `OpenAICompatibleAdapter`, endpoints CRUD + test de
   conexión, cifrado de secretos.
3. **Auditoría**: tabla `audit_log`, helper de escritura reusado por las
   mutaciones ya existentes de fase 1 y 2 (retroactivo sobre lo hecho hasta
   acá), endpoint de consulta.
4. **Almacenamiento**: `StorageBackend` (empezar solo con `LocalDiskBackend`),
   modelo `storage_objects`, endpoints de subida/descarga/borrado.
5. **`apps/admin` MVP**: login, vista de providers y usuarios (las dos
   pantallas de mayor valor), consumiendo la API de fases 1–3.
6. **`apps/admin` completo**: vista de auditoría, gestión fina de modelos por
   proveedor, "sesiones activas" por usuario.
7. **Endurecimiento**: rate limiting, cabeceras de seguridad, revisión de
   CORS, tests de autorización negativa, doc de runbook de despliegue.

## 16. Preguntas abiertas

- ¿`apps/web` va a necesitar cuentas de usuario ya en el corto plazo, o el
  backend arranca sirviendo primero al panel de admin (providers + su propio
  login) y la integración con `apps/web` es una fase posterior? Cambia el
  orden de las fases 1–2 pero no el modelo de datos.
- ¿Hay ya una cuenta/proyecto de Postgres gestionado (Neon, RDS, Supabase,
  etc.) o hay que planear también la elección de hosting de base de datos?
- ¿`apps/admin` necesita convivir en el mismo dominio que `apps/web` (para
  compartir cookie sin configurar `SameSite`/dominios cruzados) o de verdad
  va a vivir en un subdominio aparte como se asume en §2?
