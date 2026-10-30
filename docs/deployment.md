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
arrancar cada réplica (si no, N réplicas las disputarían). El paso `migrate` del contenedor hace dos
cosas: `alembic upgrade head` y `python -m app.cli setup-agent-storage`, que crea las tablas del
checkpointer y del store de LangGraph. Las dos son idempotentes y usan el mismo `DATABASE_URL`.

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
| `LANGSMITH_TRACING`                     | no          | `true` activa las trazas de LangChain en LangSmith. Ver §9: el enlace de la traza aún no se guarda en el run.   |
| `LANGSMITH_API_KEY`                     | si hay LangSmith | secreto: va en el gestor de secretos, nunca en el repositorio ni en la imagen.                              |
| `LANGSMITH_PROJECT`                     | no          | proyecto de LangSmith donde caen las trazas (por defecto, `default`).                                            |

`LANGGRAPH_STRICT_MSGPACK` lo fija la propia aplicación a `true` al importar el paquete del agente
(`app/agent/__init__.py`). No hace falta definirla; ponerla a `false` desactiva la restricción de tipos al
deserializar el checkpointer.

Variables de la demo (`SOFEE_DEMO_*`): solo las lee `python -m app.cli seed-demo`, en entornos de demo y de
prueba. En producción no se ejecuta el seed de la demo. Ninguna de estas claves va al repositorio.

| Variable                                       | Notas                                                                                       |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `SOFEE_DEMO_PROVIDER_KIND`                     | `vercel_gateway`, `deepinfra`, `nvidia_nim` o `openai_compatible`. Sin ella no se crea proveedor. |
| `SOFEE_DEMO_API_KEY`                           | key del provider de la demo. Se cifra con `SECRET_ENCRYPTION_KEY`.                          |
| `SOFEE_DEMO_BASE_URL`                          | obligatoria solo con `openai_compatible`.                                                   |
| `SOFEE_DEMO_MAIN_MODEL` / `SOFEE_DEMO_WORKER_MODEL` | modelo principal de "Sofee Pro" y su respaldo (el respaldo también debe admitir herramientas). |
| `SOFEE_DEMO_CONTEXT_WINDOW`                    | ventana de contexto de los dos modelos. Por defecto, 128000.                                |
| `SOFEE_DEMO_TAVILY_API_KEY`                    | activa `web_search`. Si ya hay una clave activa, el seed no la reemplaza.                   |
| `SOFEE_DEMO_ADMIN_PASSWORD` / `SOFEE_DEMO_USER_PASSWORD` | contraseñas de las cuentas de la demo. Si faltan, se generan y se imprimen una vez.   |

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
  `app/services/ratelimit.py`. **El agente no escala así todavía:** ver §9.

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

## 9. Agente, demo y streaming (M9–M14)

### Una sola réplica de la API

Los runs del agente son tareas asyncio dentro del proceso, y el SSE se difunde en memoria. Con dos
réplicas, un cliente conectado a una no vería los eventos de un run que ejecuta la otra, y al arrancar,
`recover_orphaned_runs` cerraría como fallidos los runs que la otra réplica tenía en curso. Hasta que se
añada `LISTEN/NOTIFY` de Postgres, **la API corre con `replicas: 1`**. Los runs pausados (`interrupted`)
no se tocan al arrancar: siguen reanudables desde el checkpointer.

### SSE detrás de un proxy

La API envía `X-Accel-Buffering: no` y un comentario de latido (`: ping`) cada 15 segundos. Aun así, el
proxy debe dejar pasar el stream sin bufferizar:

```nginx
location /api/v1/runs/ {
    proxy_pass http://sofee-api:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 1h;
}
```

Con Caddy, en el `reverse_proxy` de esa ruta: `flush_interval -1`.

### Kill switch y replay

- `agent.enabled = false` (admin → Agente → Ajustes) hace que los runs nuevos respondan 503. Un run ya en
  marcha termina.
- El modo demo (`replay.map`) reproduce un run grabado cuando la pregunta coincide. Funciona sin proveedor,
  así que es el plan B si cae la red. Solo se reproducen runs completados, y no consumen tokens ni cuota
  de tokens. La auditoría registra `agent.run_replayed`.

### Demo en un contenedor

Después del paso `migrate`, la imagen trae los documentos de la demo en `/apps/demo`:

```bash
docker run --rm \
  -e DATABASE_URL=... \
  -e SECRET_ENCRYPTION_KEY=... \
  -e SOFEE_DEMO_PROVIDER_KIND=... -e SOFEE_DEMO_API_KEY=... \
  -e SOFEE_DEMO_MAIN_MODEL=... \
  sofee-api:<version> /apps/.venv/bin/python -m app.cli seed-demo
```

El seed es idempotente: volver a ejecutarlo no duplica nada ni pisa lo que el admin haya cambiado (la
base de conocimiento retirada sigue retirada, y las preguntas de arranque existentes no se tocan).

### Trazas

Con `LANGSMITH_TRACING=true`, LangChain envía las trazas de cada llamada al modelo a LangSmith. Sofee todavía
no guarda el enlace a la traza en `agent_runs.trace_url`, así que el admin muestra "sin enlace de trazas"
aunque la traza exista.
