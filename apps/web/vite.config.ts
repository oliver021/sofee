import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import rootPkg from '../../package.json' with { type: 'json' };

// Plain Vite + Svelte — no SvelteKit. Workspace packages (@sofee/*) ship their TypeScript/
// Svelte source directly (see each package.json's "exports"), so Vite compiles them as part of
// this app rather than consuming a pre-built dist — there is nothing to build per-package
// except @sofee/tokens' generated CSS (wired into predev/prebuild).
export default defineConfig({
  plugins: [svelte()],
  define: {
    // About > Version shows the workspace package version, not a hand-copied literal.
    __APP_VERSION__: JSON.stringify(rootPkg.version),
  },
  server: {
    port: 5173,
    // Same-origin in every environment (decision 3): production is served by apps/api at /,
    // so in dev the /api prefix is proxied to the FastAPI server to keep cookies host-only.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
  },
});
