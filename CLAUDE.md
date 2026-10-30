# Sofee — reglas para trabajar en el repo

Sofee es un asistente de **learning y research** para gente nueva del equipo, no un agente de
código. Monorepo npm (`apps/web`, `apps/admin`, `packages/*`) más `apps/api` (FastAPI, uv).

## Comandos

Desde la raíz:

- `npm run typecheck`, `npm run lint`, `npm run build`, `npm run build:admin`
- `npm test` solo corre `@sofee/core`. Los otros: `npm test -w @sofee/ui` y `npm test -w @sofee/web`.

Desde `apps/api`:

- `uv run pytest -q`: necesita `docker compose up -d` (dev en 5432, test en 5433).
- `uv run alembic heads` tiene que dar **una sola cabeza**.
- `uv run python -m app.cli setup-agent-storage` crea las tablas del checkpointer y del store.

Servidores de desarrollo: `.claude/launch.json` (`sofee-web` en 5173, `sofee-api` en 8000,
`sofee-admin` en 5174).

## Antes de dar algo por terminado

- Corre las comprobaciones de lo que tocaste y di el resultado real; si algo no se pudo probar (modelo
  real, navegador), dilo.
- **Nunca dos `pytest` a la vez**: `clean_db` hace TRUNCATE sobre la misma `sofee_test` y aparecen
  fallos falsos.
- Un bug arreglado lleva un test que falla sin el arreglo.

## Frontend

- `packages/core` no importa Svelte. La lógica pura (reductores, view models) va ahí o en `.ts`
  sueltos; `packages/ui` es solo presentación.
- Ningún color literal en componentes (`sofee/no-literal-colors`): solo tokens de `packages/tokens`.
- Ningún texto visible literal en `apps/web` ni `packages/ui` (`sofee/no-raw-text`): todo pasa por
  i18n, con la clave en `en.ts` **y** `es.ts` (`packages/core/src/i18n/messages`). El admin queda
  fuera de esa regla y se escribe en español.
- Nada de `{@html}` con texto del modelo. Los enlaces pasan por `safeHref`; las imágenes del modelo no
  se cargan.
- `svelte-check` corre con `--fail-on-warnings`. JS inicial de la web por debajo de 120 kB gzip.
- El asistente simulado sigue detrás de `VITE_ASSISTANT=mock`; no lo borres.

## Backend y agente

- El harness vive en `apps/api/app/agent/`. Las firmas de deepagents/LangGraph se comprueban en el
  código instalado (`.venv`) y se anotan en `docs/deep-agent-api-notes.md`; no las supongas de
  memoria. Las versiones están fijadas en `pyproject.toml`; subirlas exige releer esas notas.
- Los eventos SSE del contrato están en `app/agent/events.py` (`EVENT_TYPES`). Un evento nuevo se
  añade ahí, en `packages/core/src/agent` y en `applyRunEvent`, a la vez.
- Cada evento se persiste en `agent_run_events` antes de difundirse. El mensaje del asistente de un run
  lo escribe solo el servidor (409 `server_owned`).
- Una ruta que devuelve `StreamingResponse` cierra su sesión de BD antes de devolverla.
- Tests sin red: modelos falsos de `tests/agent_fakes.py`, `respx` para HTTP, store y checkpointer en
  memoria con `TESTING`.
- Migraciones: una por cambio, lineal desde la cabeza actual; `alembic/env.py` excluye las tablas de
  LangGraph del autogenerate.
- Recursos de otro usuario responden 404. Toda mutación pide `X-CSRF-Token`, y las del admin además
  `require_admin` y una fila de auditoría.
- Secretos (claves de proveedor, Tavily) cifrados con Fernet; nunca en código, logs ni respuestas.
- Hay una sola réplica: los runs corren en proceso y el fan-out del SSE es en memoria.

## Git

- No hagas commit ni push sin que te lo pidan. Mensajes de commit en inglés.
- `docs/deep-agent-roadmap.md` es una nota local ignorada por git; no la vuelvas a añadir.
