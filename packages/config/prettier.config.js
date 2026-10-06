// Shared Prettier configuration for every package in the monorepo.
// Referenced from the root `.prettierrc.json` via `"extends"` is not
// supported for JS config files, so the root config re-exports this object
// (see /.prettierrc.cjs at the repo root).
export default {
  printWidth: 100,
  singleQuote: true,
  trailingComma: 'all',
  semi: true,
  arrowParens: 'always',
  plugins: ['prettier-plugin-svelte'],
  overrides: [
    {
      files: '*.svelte',
      options: {
        parser: 'svelte',
      },
    },
  ],
};
