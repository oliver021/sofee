import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// Tests here cover the app's state modules (rune classes compiled by the Svelte plugin), not the
// DOM: the run client is replaced with a fake, so nothing touches the network.
export default defineConfig({
  plugins: [svelte()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    passWithNoTests: false,
  },
});
