# Runbook de despliegue — Sofee API + app web + panel admin

Guía de operación para el backend (`apps/api`), la app web (`apps/web`) y el panel
admin (`apps/admin`). Complementa el plan en [`backend-plan.md`](./backend-plan.md)
(§14) y la decisión 3 de [`index.md`](./index.md): **un solo contenedor que sirve la
API, la app web y el panel en el mismo dominio** — la API en `/api/v1`, la app web
en `/`, el panel estático en `/admin`.

## Modelo de despliegue

```
                 HTTPS
  Internet ──► reverse proxy ──► sofee-api (uvicorn, puerto 8000)
                  │                    ├── /api/v1/*      (JSON)
                  │                    ├── /              (SPA: apps/web/dist)
                  │                    ├── /admin/*       (SPA: apps/admin/dist)
                  │                    └── /healthz       (healthcheck)
                                      └─► PostgreSQL (gestionado o en red interna)
```

- Una sola imagen (`sofee-api`) con los `dist` de `apps/web` (`WEB_DIST_DIR`) y
  `apps/admin` (`ADMIN_DIST_DIR`) dentro.
- Sesiones server-side en Postgres → la cookie `sofee_session` viaja al mismo
  dominio también para la app web (cookies first-party, sin CORS).
- CORS queda **desactivado** (lista vacía): todo es mismo origen. Solo se activa si
  algún día `apps/web` o `apps/admin` viven en otro origen (ver §5).

## 1. Requisitos previos

- Node 20+ (para construir el panel) y Docker.
- PostgreSQL 15+ accesible desde la red del contenedor.
- `SECRET_ENCRYPTION_KEY` generada (ver §4).

## 2. Construcción

```bash
# 1) Construir los frontends:
npm run build             # -> genera apps/web/dist
npm run build:admin       # -> genera apps/admin/dist

# 2) Construir la imagen (context = raíz del monorepo):
docker build -t sofee-api:<version> -f apps/api/Dockerfile .
```

El `Dockerfile` usa `uv` en una etapa de build y copia el `.venv` a la etapa final;
las migraciones **no** se ejecutan en el arranque del proceso web (ver §3).

## 3. Release en dos pasos (migraciones aparte)

Las migraciones de Alembic corren una sola vez en el **paso de release**, no al
arrancar cada réplica (si no, N réplicas las disputarían).

```bash
# Paso A — migraciones (una sola ejecución):
docker run --rm \
  -e DATABASE_URL=... \
  -e SECRET_ENCRYPTION_KEY=... \
  sofee-api:<version> migrate

# Paso B — arrancar réplicas del proceso web (default CMD):
docker run -d \
  -e DATABASE_URL=... \
  -e SECRET_ENCRYPTION_KEY=... \
  -e SESSION_COOKIE_SECURE=true \
  -e TRUSTED_PROXIES='["10.0.0.5"]' \
  -p 8000:8000 \
  sofee-api:<version> serve
```

Orden recomendado en CI/CD: **build → migrate → deploy réplicas**. Si un release
falla a mitad, repetir solo `migrate` antes de reintentar; las migraciones son
idempotentes (Alembic versiona la cabecera).

## 4. Variables de entorno

Mínimas en producción:

| Variable                                | Obligatoria | Notas                                                                                                            |
| --------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                          | sí          | `postgresql+asyncpg://user:pass@host/db`                                                                         |
| `SECRET_ENCRYPTION_KEY`                 | sí          | Clave Fernet (32 bytes base64). Protege API keys de providers.                                                   |
| `CSRF_SECRET`                           | sí          | sustituir el valor de desarrollo `dev-csrf-secret-change-me`                                                     |
| `SESSION_COOKIE_SECURE`                 | sí          | `true` en producción; habilita atributo `Secure` y la cabecera HSTS                                              |
| `SESSION_COOKIE_DOMAIN`                 | opcional    | dominio de la cookie (`.sofee.app`) si se necesita                                                               |
| `TRUSTED_PROXIES`                       | sí*         | IP(s) del reverse proxy; sin esto `X-Forwarded-For` se ignora (el rate limit y la auditoría ven la IP del proxy) |
| `CORS_ALLOWED_ORIGINS`                  | no          | vacío = mismo origen                                                                                             |
| `STORAGE_BACKEND` / `STORAGE_LOCAL_DIR` | no          | `local` por defecto; `s3` pendiente de implementar                                                               |
| `WEB_DIST_DIR` / `ADMIN_DIST_DIR`       | no          | rutas a los `dist` de `apps/web` y `apps/admin`; en la imagen apuntan a `/apps/web_dist` y `/apps/admin_dist`    |

Generar la clave de cifrado (una vez, guardarla fuera del repo):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> ⚠️ Rotar `SECRET_ENCRYPTION_KEY` invalidará las API keys de providers cifradas
> con la anterior. Si se rota, hay que re-cifrar (`provider_credentials`) o
> re-insertar credenciales desde el panel.

## 5. Reverse proxy, TLS y cabeceras

- **TLS:** terminado en el proxy (nginx/Caddy/Traefik). Con `SESSION_COOKIE_SECURE=true`
  la API emite `Strict-Transport-Security` automáticamente.
- **Cabeceras** (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`,
  `Content-Security-Policy`) las emite el middleware de la API también a `/` y `/admin`.
  Si se quiere endurecer la CSP, setear `CONTENT_SECURITY_POLICY` con hashes/nonces
  del snippet inline del panel (la CSP por defecto usa `'unsafe-inline'` por ese snippet).
- **`TRUSTED_PROXIES` debe contener la IP del proxy** para que el rate limit y la
  auditoría usen la IP real del cliente en vez de la del proxy.
- Healthcheck del orquestador: `GET /healthz` → 200 `{"status":"ok"}`.
- CORS: mantener `CORS_ALLOWED_ORIGINS=[]` (mismo origen). Solo se activa el
  middleware si la lista no está vacía; los orígenes se declaran explícitamente,
  nunca `*`.

Ejemplo de config Docker Compose (producción, mismo dominio):

```yaml
services:
  api:
    image: sofee-api:<version>
    environment:
      DATABASE_URL: postgresql+asyncpg://sofee:${DB_PASS}@db:5432/sofee
      SECRET_ENCRYPTION_KEY: ${SECRET_ENCRYPTION_KEY}
      CSRF_SECRET: ${CSRF_SECRET}
      SESSION_COOKIE_SECURE: 'true'
      TRUSTED_PROXIES: '["127.0.0.1"]' # IP del proxy
    healthcheck:
      test:
        [
          'CMD',
          'python',
          '-c',
          "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')",
        ]
      interval: 10s
      timeout: 5s
      retries: 5
    depends_on:
      db:
        condition: service_healthy
```

Las migraciones se corren como job aparte con el mismo `image` pero comando
`migrate` (`docker compose run --rm api migrate`), nunca como parte del arranque.

## 6. Operación

- **Primer admin:** `docker run --rm <image> migrate` aplicó el esquema; luego
  `docker run --rm ... ` con un one-off: `python -m app.cli create-admin --email admin@sofee.app`.
  En el contenedor el CLI no expone shebang de script; usar la forma
  `docker run --rm -it <image> /apps/.venv/bin/python -m app.cli create-admin --email X --password Y`
  (o conectarse a una shell de una réplica).
- **Backups:** dump de Postgres; `storage_objects` apunta a `STORAGE_LOCAL_DIR` en
  disco local — para recuperación leer, montar un volumen persistente o usar S3.
- **Sesiones/auditoría:** las sesiones vencidas se podan de forma perezosa; la
  `audit_log` es append-only (sin retención por defecto). Volúmenes altos → pensar
  partición por mes.
- **Escalado horizontal:** el rate limit de login usa la tabla `login_attempts`
  (compartida), así que funciona multinodo sin Redis. Si llegara a saturarse,
  migrar ese contador interno a Redis es un cambio localizado en
  `app/services/ratelimit.py`.

## 7. Endurecimiento aplicado (M7)

- Rate limiting en `POST /auth/login` por email e IP (tabla `login_attempts`,
  ventana deslizante, respuesta `429` + `Retry-After`).
- Cabeceras de seguridad en middleware (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `X-XSS-Protection`, `Permissions-Policy`, `COOP`, `CORP`, CSP,
  HSTS cuando la cookie es Secure).
- CORS bajo demanda: solo se emiten cabeceras con orígenes explícitos; por defecto
  mismo origen sin middleware.
- `TRUSTED_PROXIES`: `X-Forwarded-For` solo se admite desde proxies configurados.
- Tests de autorización negativa: todo endpoint admin devuelve **403** a usuario
  regular (no 404) y **401** a anónimo; rutas inexistentes devuelven 404.

## 8. Integración de `apps/web` (M8)

- La app se monta en la **raíz `/`** (último mount, después de `/api/v1`, `/admin`
  y `/healthz`); las rutas `/api/*` inexistentes siguen dando 404 (el `StaticFiles`
  solo sirve `index.html` para directorios, no para ficheros que no existen).
- Registro self-service en `POST /api/v1/auth/register`: rol `regular`, comparte el
  rate limit de login, audita `user.created` y no concede acceso admin.
- Las conversaciones viven en `threads` + `messages`, direccionadas por el
  `client_id` generado en el navegador (upserts idempotentes); las mutaciones
  exigen CSRF y solo el dueño ve sus hilos (404 para el resto).
- Los adjuntos suben a `/api/v1/storage` y el id del objeto se guarda en
  `messages.attachment_ids`; la descarga es same-origin y requiere sesión.
- `storage_objects` sigue en `STORAGE_LOCAL_DIR`: montar un volumen persistente en
  producción o migrar a S3 (pendiente).
