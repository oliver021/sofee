import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import sveltePlugin from 'eslint-plugin-svelte';
import globals from 'globals';
import prettierConfig from 'eslint-config-prettier';
import { sofeeLocalRules } from './packages/config/eslint/local-rules.js';

// design-system.md §1: "A literal colour anywhere in a component is a bug."
// packages/tokens is the one place colours are defined; core has no styling.
const noLiteralColorFiles = [
  'apps/web/src/**/*.{ts,svelte}',
  'apps/admin/src/**/*.{ts,svelte}',
  'packages/ui/src/**/*.{ts,svelte}',
  'packages/icons/src/**/*.{ts,svelte}',
];

// ux-foundations.md §7.1: "No user-facing literal strings in components."
// Icons carry no text; core/tokens carry no markup.
const noRawTextFiles = ['apps/web/src/**/*.svelte', 'packages/ui/src/**/*.svelte'];

export default tseslint.config(
  {
    ignores: [
      '**/node_modules/**',
      '**/dist/**',
      '**/generated/**',
      '**/.svelte-kit/**',
      '**/coverage/**',
      'package-lock.json',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...sveltePlugin.configs['flat/recommended'],
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.es2022 },
    },
  },
  {
    // `.svelte` components AND `.svelte.ts`/`.svelte.js` rune modules (Svelte 5's "universal
    // reactivity" files, e.g. apps/web/src/lib/*.svelte.ts) are both parsed by
    // svelte-eslint-parser, which needs to be told to delegate script content to the
    // TypeScript parser — without this, a plain `.svelte.ts` file with `import type { ... }`
    // fails to parse at all (svelte-eslint-parser falls back to a plain JS parser for it).
    files: ['**/*.svelte', '**/*.svelte.ts', '**/*.svelte.js'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
        extraFileExtensions: ['.svelte'],
      },
    },
  },
  {
    files: ['**/*.config.{js,ts,mjs,cjs}', '**/vitest.config.ts', 'packages/tokens/src/build.ts'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ['**/*.test.ts'],
    languageOptions: { globals: { ...globals.node } },
  },
  // Register the local plugin namespace, then turn its rules on only where
  // they are meaningful (see comments on the glob lists above).
  { plugins: { sofee: sofeeLocalRules } },
  { files: noLiteralColorFiles, rules: { 'sofee/no-literal-colors': 'error' } },
  { files: noRawTextFiles, rules: { 'sofee/no-raw-text': 'error' } },
  {
    rules: {
      // TS's own checker supersedes no-undef; it does not understand Svelte
      // 5 runes ($state/$derived/$effect/$props) and produces false
      // positives on them.
      'no-undef': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
      'svelte/valid-compile': ['error', { ignoreWarnings: false }],
    },
  },
  {
    files: ['packages/core/src/**/*.ts'],
    rules: {
      // packages/core must stay framework-free (10. "packages/core must not
      // import Svelte").
      'no-restricted-imports': ['error', { patterns: ['svelte', 'svelte/*'] }],
    },
  },
  prettierConfig,
);
