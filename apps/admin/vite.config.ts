import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

// The admin panel lives on the same domain as the API (decision 3): the built app is served
// by apps/api at /admin, so `base` is fixed to /admin/ for both dev and production. In dev
// the /api prefix is proxied to the FastAPI server so session cookies stay host-only.
export default defineConfig({
  plugins: [svelte()],
  base: '/admin/',
  server: {
    port: 5174,
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
