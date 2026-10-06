/**
 * First-party ESLint rules for the two invariants the spec calls out
 * explicitly, which no off-the-shelf rule covers:
 *
 *  - `no-literal-colors` — "A literal colour anywhere in a component is a
 *    bug." (design-system.md §1). Every colour must flow through a
 *    `--p-*` / `--sem-*` custom property defined once in packages/tokens.
 *
 *  - `no-raw-text` — "No user-facing literal strings in components...
 *    Enforced by lint." (ux-foundations.md §7.1). Copy must come from the
 *    i18n catalogues in packages/core.
 *
 * Both rules scan the raw source text rather than walking a parser AST.
 * `sourceCode.getText()` with no arguments always returns the *whole* file
 * regardless of how a given parser scopes its `Program` node, so this works
 * identically for plain `.ts` files and for `.svelte` files parsed by
 * svelte-eslint-parser — without depending on that parser's exact AST node
 * names, which have shifted across versions. They are deliberately simple,
 * auditable heuristics rather than full parsers; see the allowlists inline.
 */

const HEX_COLOR = /#(?:[0-9a-fA-F]{3}){1,2}(?:[0-9a-fA-F]{2})?\b/g;

/** Text that carries no translatable meaning on its own (punctuation, digits, icons-as-text). */
function isIgnorableText(text) {
  const trimmed = text.trim();
  if (trimmed.length === 0) return true;
  if (!/[A-Za-zÀ-ÖØ-öø-ÿ]{2,}/.test(trimmed)) return true;
  return false;
}

/** Blank out <script>/<style> blocks (keep offsets stable) so only markup text is scanned. */
function stripNonTemplateRegions(text) {
  return text.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, (block) =>
    block.replace(/[^\n]/g, ' '),
  );
}

function filenameOf(context) {
  return context.filename ?? context.getFilename();
}

export const sofeeLocalRules = {
  rules: {
    'no-literal-colors': {
      meta: {
        type: 'problem',
        docs: {
          description: 'Disallow hard-coded hex colours outside packages/tokens.',
        },
        schema: [],
      },
      create(context) {
        return {
          Program(node) {
            const filename = filenameOf(context);
            if (filename.includes(`${'packages'}${'/'}${'tokens'}`)) return;
            const source = context.sourceCode.getText();
            for (const match of source.matchAll(HEX_COLOR)) {
              const index = match.index ?? 0;
              context.report({
                node,
                loc: context.sourceCode.getLocFromIndex(index),
                message:
                  'Literal colour "{{value}}" is not allowed here. Use a --p-* / --sem-* design token instead (design-system.md §1).',
                data: { value: match[0] },
              });
            }
          },
        };
      },
    },

    'no-raw-text': {
      meta: {
        type: 'problem',
        docs: {
          description:
            'Disallow user-facing literal text in .svelte markup; pull it from the i18n catalogue.',
        },
        schema: [],
      },
      create(context) {
        return {
          Program(node) {
            const filename = filenameOf(context);
            if (!filename.endsWith('.svelte')) return;
            const scanned = stripNonTemplateRegions(context.sourceCode.getText());
            // Text strictly between `>` and the next `<`, with no `{`/`}` inside —
            // a mustache expression (`{t(...)}`) is the escape hatch.
            const TEXT_NODE = />([^<>{}]+)</g;
            for (const match of scanned.matchAll(TEXT_NODE)) {
              const text = match[1] ?? '';
              if (isIgnorableText(text)) continue;
              const index = (match.index ?? 0) + 1;
              context.report({
                node,
                loc: context.sourceCode.getLocFromIndex(index),
                message:
                  'Raw text "{{value}}" in markup. Pull it from the i18n catalogue with t(...) instead (ux-foundations.md §7.1).',
                data: { value: text.trim() },
              });
            }
          },
        };
      },
    },
  },
};
