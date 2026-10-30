# Sofee

Sofee is a **learning and research assistant** frontend — explicitly not a coding
agent. It is built for people who are new to a team and need long, well-organised
answers they can read from the top, not a fast back-and-forth. There is no backend:
the answers come from a backend in `apps/api` (FastAPI) that runs a deep agent (`deepagents`
on LangGraph): Learn, Research and Explore are three agent profiles, edited from the admin panel.
The old simulated assistant (`packages/core/src/mock`) still runs behind `VITE_ASSISTANT=mock`, so
the UI stays demonstrable on its own. To run the whole demo, see
[Demo end to end](#demo-end-to-end) below.

The two documents that define this app's behaviour and appearance in full live in
[`docs/ux-foundations.md`](./docs/ux-foundations.md) (interaction, states, scroll,
accessibility, motion) and [`docs/design-system.md`](./docs/design-system.md)
(palettes, tokens, the dotted field, typography, the composer). Where they disagree,
UX foundations wins on behaviour and design system wins on appearance. Read those
before changing how something looks or behaves — this README only covers running
and extending the code.

## Install and run

Requires Node.js 20+ (built and tested on Node 22). This is an npm-workspaces
monorepo — plain `npm`, no other package manager required.

```bash
npm install        # also generates packages/tokens' CSS (postinstall)
npm run dev         # starts the Vite dev server for apps/web
```

Other useful scripts, run from the repo root:

```bash
npm run build        # builds packages/tokens' CSS, then apps/web for production
npm run typecheck    # tsc/svelte-check across every package, zero errors expected
npm run lint         # ESLint across the whole repo (includes two first-party rules,
                      # see "Design rules enforced by lint" below)
npm run format       # Prettier, writing
npm test             # Vitest — the scroll controller and the i18n module
```

`packages/tokens` has one real build step: it turns the palette **data**
(`packages/tokens/src/palettes.ts`) into generated CSS custom properties
(`packages/tokens/generated/tokens.css`, gitignored). That step is wired into the
root `postinstall` and into `apps/web`'s own `predev`/`prebuild`, so in normal use
you never have to think about it — `npm install` and `npm run dev`/`build` just
work. If you ever see stale token values, run `npm run build --workspace=@sofee/tokens`
directly.

## Demo end to end

What you need: Docker (for Postgres), Node.js 20+ and [uv](https://docs.astral.sh/uv/), which
installs the Python 3.12 that `apps/api` uses.

**1. Databases.** Development on port 5432, tests on 5433:

```bash
docker compose up -d postgres postgres-test
```

**2. Frontends.** From the repository root:

```bash
npm install
npm run build:admin    # the API serves the admin panel at /admin from apps/admin/dist
```

**3. API: dependencies, schema and the agent's tables.**

```bash
cd apps/api
uv sync
uv run alembic upgrade head
uv run python -m app.cli setup-agent-storage   # LangGraph checkpointer and store tables
```

**4. Demo data.** `seed-demo` is idempotent, so you can run it again at any time:

```bash
uv run python -m app.cli seed-demo
```

Without a provider it creates the demo users, the 14 fictional team documents in
`apps/api/demo/kb/`, version 1 of each agent profile and the starter questions. Passwords come from
`SOFEE_DEMO_ADMIN_PASSWORD` and `SOFEE_DEMO_USER_PASSWORD`; if they are unset, they are generated and
printed once. Without a provider the agent cannot answer live, so use replays (see below).

With a real provider, export the keys in your shell. They are never written to the repository:

```bash
SOFEE_DEMO_PROVIDER_KIND=deepinfra \
SOFEE_DEMO_API_KEY=... \
SOFEE_DEMO_MAIN_MODEL=... \
SOFEE_DEMO_WORKER_MODEL=... \
uv run python -m app.cli seed-demo
```

This adds the provider and the "Sofee Pro" catalog entry (main model first, worker as the fallback).
The seed never sets `supports_tools` by hand: it runs a real tool-calling probe on each model and
keeps the result. Set `SOFEE_DEMO_TAVILY_API_KEY` to enable web search.

**5. Run.** Provider and Tavily keys are stored encrypted, so `SECRET_ENCRYPTION_KEY` must be set
first (in `apps/api/.env`, which is gitignored, or in your shell). Generate one with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```bash
cd apps/api && uv run uvicorn app.main:app --reload   # API on http://localhost:8000
```

In another terminal, from the repository root:

```bash
npm run dev          # the app on http://localhost:5173, /api proxied to :8000
npm run dev:admin    # the admin panel on http://localhost:5174/admin/
```

Sign in to the admin panel as the admin user, then in **Agente → Ajustes** you can switch the agent
off for maintenance, edit the starter questions and set the replay map.

**Plan B: replays.** If the provider or the network fails during a live demo, point the question to
a run that already completed: in **Agente → Ajustes → Modo demo: runs grabados**, pair the question
with that run's id (copy it from the Runs view). When someone asks that question, the server replays the recorded run's events with their
original timing (gaps capped at 2 s) and makes no model call. The replay run is saved like any other,
but it uses no tokens and is logged in the audit trail. Only completed runs can be replayed. So
record the script once with the real provider before the demo.

Environment variables for the demo:

| Variable | Required | Notes |
| -------- | -------- | ----- |
| `SOFEE_DEMO_PROVIDER_KIND` | to add a provider | `vercel_gateway`, `deepinfra`, `nvidia_nim` or `openai_compatible` |
| `SOFEE_DEMO_API_KEY` | with a provider | never logged or stored in clear text |
| `SOFEE_DEMO_BASE_URL` | `openai_compatible` only | base URL of the endpoint |
| `SOFEE_DEMO_MAIN_MODEL` | with a provider | primary binding of "Sofee Pro" |
| `SOFEE_DEMO_WORKER_MODEL` | no | fallback binding; it must support tools too |
| `SOFEE_DEMO_CONTEXT_WINDOW` | no | context window of both models, 128000 by default |
| `SOFEE_DEMO_TAVILY_API_KEY` | no | enables `web_search` |
| `SOFEE_DEMO_ADMIN_PASSWORD` / `SOFEE_DEMO_USER_PASSWORD` | no | otherwise generated and printed once |

Tests for the backend, which never touch the network (they need `postgres-test` on 5433):

```bash
cd apps/api && uv run pytest
```

Production deployment, migrations and reverse proxy settings are in [`docs/deployment.md`](docs/deployment.md).

## Workspace layout

```
apps/api/            FastAPI backend (Python, managed with uv): sessions, providers, the model
                       catalog, the agent harness (`app/agent/`), the team knowledge base and the
                       admin API. Its agent and demo commands are below.
apps/admin/          Svelte admin panel, served by apps/api at /admin
apps/web/            Vite + Svelte 5 app — assembles everything, owns all app state
packages/tokens/      The six palettes as typed data -> generated CSS custom properties
packages/ui/          Svelte components (rails, panels, menus, the Orbit composer,
                       the message list) — presentational only, no domain state
packages/icons/       The icon set, as small Svelte components (20px, currentColor,
                       1.6 stroke, per design-system.md §6)
packages/core/        Framework-free domain logic: the scroll controller, the i18n
                       module + message catalogues, and the mock assistant.
                       Contains no Svelte imports anywhere.
packages/config/      Shared tsconfig / ESLint / Prettier base, consumed by the
                       other workspaces via relative paths
```

Dependency direction is one-way: `apps/web` depends on all four packages;
`packages/ui` depends on `packages/icons` and `packages/tokens` and only takes
_type-only_ imports from `packages/core` (its i18n `Translate` type, the
`ScrollController` type, and a couple of small domain type aliases like
`ComposerMode`) — it never imports `packages/core`'s runtime domain/mock logic,
which is what keeps it free of "domain state" per its own brief.

## Design rules enforced by lint

Two rules in `packages/config/eslint/local-rules.js`, wired up in the root
`eslint.config.js`, encode the two invariants the spec is strictest about:

- **`sofee/no-literal-colors`** — design-system.md §1: "A literal colour anywhere in
  a component is a bug." Flags a hex colour anywhere outside `packages/tokens`.
- **`sofee/no-raw-text`** — ux-foundations.md §7.1: "No user-facing literal strings
  in components." Flags text sitting directly in `.svelte` markup instead of coming
  from `t(...)`.

Both scan raw source text rather than a parser AST (see the file's header comment
for why); they are deliberately simple, auditable heuristics, not full parsers.

## Adding a locale

Sofee ships English and Spanish; the i18n module
(`packages/core/src/i18n/i18n.ts`) does not assume exactly two.

1. Add the new locale's tag to `Locale` and `SUPPORTED_LOCALES` in
   `packages/core/src/i18n/i18n.ts`.
2. Add `packages/core/src/i18n/messages/<locale>.ts`, typed as
   `const xx: Messages = { ... }` (where `Messages = typeof en`) — a missing or
   mis-shaped key is a compile error, not a silent runtime fallback.
3. Add it to the `catalogs` map in `apps/web/src/lib/i18n.svelte.ts`.
4. Add its display name to the `language` catalogue entry in **every** locale
   (each locale shows every language's name in that language, e.g. `en`/`es` both
   list `"English"` and `"Español"` unchanged).
5. Test the new locale end to end — ux-foundations.md §7.2: "Test every screen in
   `es` before calling it done" applies equally to whatever you add. Watch for
   fixed-width labels; Sofee's CSS avoids them for exactly this reason.

## Adding a palette

Every palette is one data record behind an identical token contract
(design-system.md §1) — a component never knows which palette is active.

1. Add the palette's id to `PaletteId` in `packages/tokens/src/types.ts`.
2. Add a full entry to the `palettes` record in `packages/tokens/src/palettes.ts`:
   the six base colours, the dot spec (§3's table), the ambient gradient, the
   display font, and (only if it needs to diverge from the standard formulas in
   `derive.ts`) a `derivedOverrides` entry — see that file's header comment for
   which tokens are derived and why.
3. If the palette needs semantic-colour tuning for contrast (e.g. it has a light
   ground, like Overprint), extend the `scheme` handling in
   `packages/tokens/src/palettes.ts`'s `semanticColors` map.
4. Run `npm run build --workspace=@sofee/tokens` (or just `npm run dev`, which
   does this for you) and check contrast against the new palette's `bg` — the
   design-system document's own warning applies: recompute the contrast column
   before shipping a hex.
5. The palette switcher (in the header's More menu, in `apps/web/src/App.svelte`)
   reads the `palettes` record directly, so a new entry appears there automatically.

## A few judgement calls

design-system.md gives exact hex values for six colours per palette (`bg`, `surf`,
`ink`, `mut`, `acc`, `acc2`) but describes several other tokens only in prose
(`--p-surf-2`, `--p-line`, `--p-line-2`, `--p-hi`, `--p-glow`, the semantic
success/warning/critical scale). Those are derived systematically via CSS
`color-mix()` from the six given colours — see the file header comments in
`packages/tokens/src/derive.ts` and `palettes.ts` for the exact formulas and
per-palette overrides (Overprint's flat/no-glow treatment, its hard cast shadow,
its title gradient stopping at `acc`). This is also written up in the delivery
report for this build; the short version is that every gap was filled with a
single systematic rule applied to all six palettes, not six one-off choices.
