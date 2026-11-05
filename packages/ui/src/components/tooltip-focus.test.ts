/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// The tooltip visibility rules are CSS inside .svelte files, which the SSR-only test setup cannot
// style-check. This guards the selector shape: a tooltip must open on keyboard focus only, never on
// :focus-within, because a mouse click or a focus restore leaves the trigger focused and the tooltip
// stuck open. Comments are stripped so the explanation in the stylesheet is not matched.
const styleOf = (name: string) => {
  const source = readFileSync(new URL(`./${name}`, import.meta.url), 'utf8');
  const style = source.slice(source.indexOf('<style>'));
  return style.replace(/\/\*[\s\S]*?\*\//g, '');
};

describe('tooltip visibility', () => {
  it('IconButton shows its tooltip on keyboard focus, not on any focus', () => {
    const css = styleOf('IconButton.svelte');
    expect(css).not.toMatch(/focus-within/);
    expect(css).toMatch(/:has\(\.icon-button:focus-visible\) \.tooltip/);
  });

  it('CitationRef shows its preview on keyboard focus, not on any focus', () => {
    const css = styleOf('CitationRef.svelte');
    expect(css).not.toMatch(/focus-within/);
    expect(css).toMatch(/:has\(\.citation-ref:focus-visible\) \.citation-preview/);
  });
});
