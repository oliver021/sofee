# Sofee

Sofee is a **learning and research assistant** frontend — explicitly not a coding
agent. It is built for people who are new to a team and need long, well-organised
answers they can read from the top, not a fast back-and-forth. There is no backend:
the assistant is a local, simulated token stream (see `packages/core/src/mock`), so
the whole UI is demonstrable on its own.

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

## Workspace layout

```
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
