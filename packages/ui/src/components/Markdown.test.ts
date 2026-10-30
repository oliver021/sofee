import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import type { Citation, Translate } from '@sofee/core';
import Markdown from './Markdown.svelte';

/** Stand-in for the app's translator: returns the key, so the markup shows which copy was used. */
const t: Translate = (path) => path;

/** The server render with Svelte's hydration comments and scoped class hashes removed, so the
 * assertions read the markup a person would see. */
function html(text: string, citations: Citation[] = []): string {
  const raw = render(Markdown, { props: { text, citations, t } }).body;
  return raw
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/ class="svelte-[a-z0-9]+"/g, '')
    .replace(/ svelte-[a-z0-9]+/g, '');
}

const citations: Citation[] = [
  { index: 1, title: 'Guía', url: 'https://example.com/guia' },
  { index: 2, title: 'Documento interno', url: null, kind: 'kb', ref: 'doc-7' },
];

describe('Markdown renderer', () => {
  it('renders paragraphs with bold and citations resolved from the citation list', () => {
    const out = html('Una **idea** clave [1].', citations);
    expect(out).toContain('<strong>idea</strong>');
    expect(out).toContain('href="https://example.com/guia"');
    expect(out).toContain('<sup>[1]</sup>');
  });

  it('keeps a citation with no URL as a reference with no link', () => {
    const out = html('Según el manual [2].', citations);
    expect(out).not.toContain('href="null"');
    expect(out).toContain('<span class="citation-ref">');
    expect(out).toContain('Documento interno');
  });

  it('shows an unknown citation index as plain bracketed text', () => {
    const out = html('Dato suelto [9].', citations);
    expect(out).toContain('Dato suelto [9].');
    expect(out).not.toContain('citation-preview');
  });

  it('renders fenced code with its language label and a copy button, never as HTML', () => {
    const out = html('```ts\nconst x = "<b>hola</b>";\n```');
    expect(out).toContain('<span class="code-lang">ts</span>');
    expect(out).toContain('copy-btn');
    expect(out).toContain('&lt;b>hola&lt;/b>');
    expect(out).not.toContain('<b>hola</b>');
  });

  it('labels a code block with no language as code', () => {
    const out = html('```\nplano\n```');
    expect(out).toContain('<span class="code-lang">message.codeBlock</span>');
  });

  it('renders an unclosed fence mid-stream as a code block', () => {
    const out = html('Respuesta\n\n```js\nconst a = 1;');
    expect(out).toContain('class="code-block"');
    expect(out).toContain('const a = 1;');
  });

  it('renders nested and ordered lists', () => {
    const out = html('1. uno\n   - sub\n2. dos');
    expect(out).toContain('<ol start="1">');
    expect(out).toContain('<ul>');
    expect(out).toMatch(/<li>[\s\S]*<ul>[\s\S]*sub[\s\S]*<\/ul>/);
  });

  it('wraps tables in their own scrolling box and keeps the column alignment', () => {
    const out = html('| a | b |\n|:-|-:|\n| 1 | 2 |');
    expect(out).toContain('<div class="table-wrap">');
    expect(out).toContain('text-align: right');
  });

  it('gives external links the safe target and rel, and drops unsafe ones to text', () => {
    const out = html('[ok](https://example.com) y [mal](javascript:alert(1))');
    expect(out).toContain('target="_blank"');
    expect(out).toContain('rel="noopener noreferrer"');
    expect(out).not.toContain('javascript:');
    expect(out).toContain('mal');
  });

  it('shows raw HTML from the model as escaped text', () => {
    const out = html('<img src=x onerror=alert(1)>');
    expect(out).not.toContain('<img');
    expect(out).toContain('&lt;img');
  });

  it('renders headings at their own level', () => {
    const out = html('## Título\n\n#### Pequeño');
    expect(out).toContain('<h2 class="heading">Título</h2>');
    expect(out).toContain('<h4 class="heading">Pequeño</h4>');
  });
});
