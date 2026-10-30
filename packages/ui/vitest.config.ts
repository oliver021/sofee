import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  // The svelte plugin lets the component tests import .svelte files; the test environment stays
  // node, so components are rendered on the server (svelte/server) without a DOM.
  plugins: [svelte()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    passWithNoTests: false,
  },
});
