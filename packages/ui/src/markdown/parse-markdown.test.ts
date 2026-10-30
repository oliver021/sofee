import { describe, expect, it } from 'vitest';
import { parseMarkdown, type MarkdownBlock, type MarkdownInline } from './parse-markdown.js';
import { safeHref } from './safe-href.js';

/** Flattens inline nodes to their visible text, so assertions can read as sentences. */
function textOf(nodes: readonly MarkdownInline[]): string {
  return nodes
    .map((node) => {
      if (node.type === 'text') return node.value;
      if (node.type === 'citation') return `[${node.index}]`;
      if (node.type === 'code') return node.value;
      if (node.type === 'break') return '\n';
      return textOf(node.children);
    })
    .join('');
}

describe('parseMarkdown — headings and paragraphs', () => {
  it('maps heading depths 1 to 4 and clamps deeper headings to 4', () => {
    const blocks = parseMarkdown('# Uno\n\n## Dos\n\n### Tres\n\n#### Cuatro\n\n##### Cinco');
    const headings = blocks.filter(
      (b): b is Extract<MarkdownBlock, { type: 'heading' }> => b.type === 'heading',
    );
    expect(headings.map((h) => h.level)).toEqual([1, 2, 3, 4, 4]);
    expect(textOf(headings[0]?.children ?? [])).toBe('Uno');
  });

  it('keeps bold, italic and strikethrough as nested inline nodes', () => {
    const [block] = parseMarkdown('Una **negrita**, *cursiva* y ~~tachado~~.');
    expect(block?.type).toBe('paragraph');
    if (block?.type !== 'paragraph') return;
    const types = block.children.map((n) => n.type);
    expect(types).toContain('strong');
    expect(types).toContain('em');
    expect(types).toContain('del');
    expect(textOf(block.children)).toBe('Una negrita, cursiva y tachado.');
  });

  it('returns no blocks for empty or whitespace-only input', () => {
    expect(parseMarkdown('')).toEqual([]);
    expect(parseMarkdown('   \n  ')).toEqual([]);
  });
});

describe('parseMarkdown — code', () => {
  it('reads the language from the info string and keeps the code verbatim', () => {
    const [block] = parseMarkdown('```ts title="x"\nconst a = 1;\n```');
    expect(block).toEqual({ type: 'code', lang: 'ts', text: 'const a = 1;' });
  });

  it('gives a block without a language a null label', () => {
    const [block] = parseMarkdown('```\nplain\n```');
    expect(block).toEqual({ type: 'code', lang: null, text: 'plain' });
  });

  it('renders an unclosed fence mid-stream as code, not as paragraph text', () => {
    const blocks = parseMarkdown('Antes\n\n```js\nconst b = 2;\nconst c');
    const code = blocks.find((b) => b.type === 'code');
    expect(code).toEqual({ type: 'code', lang: 'js', text: 'const b = 2;\nconst c' });
  });

  it('hides a lone opening backtick run at the end of a stream so it never flashes as text', () => {
    expect(parseMarkdown('Respuesta lista\n``')).toEqual([
      { type: 'paragraph', children: [{ type: 'text', value: 'Respuesta lista' }] },
    ]);
  });

  it('keeps inline code literal, including what looks like a citation', () => {
    const [block] = parseMarkdown('Usa `[2]` aquí');
    expect(
      block?.type === 'paragraph' &&
        block.children.some((n) => n.type === 'code' && n.value === '[2]'),
    ).toBe(true);
    expect(block?.type === 'paragraph' && block.children.some((n) => n.type === 'citation')).toBe(
      false,
    );
  });
});

describe('parseMarkdown — citations', () => {
  it('turns [n] markers into citation nodes, in place', () => {
    const [block] = parseMarkdown('El núcleo está validado [1] y matizado [2].');
    if (block?.type !== 'paragraph') throw new Error('expected a paragraph');
    const citations = block.children.filter((n) => n.type === 'citation');
    expect(citations).toEqual([
      { type: 'citation', index: 1 },
      { type: 'citation', index: 2 },
    ]);
    expect(textOf(block.children)).toBe('El núcleo está validado [1] y matizado [2].');
  });

  it('finds citations inside emphasis and list items', () => {
    const blocks = parseMarkdown('- **Clave** según la fuente [3]\n- otra [4]');
    const list = blocks[0];
    expect(list?.type).toBe('list');
    if (list?.type !== 'list') return;
    const first = list.items[0]?.children[0];
    expect(
      first?.type === 'plain' && first.children.some((n) => n.type === 'citation' && n.index === 3),
    ).toBe(true);
  });
});

describe('parseMarkdown — lists', () => {
  it('reads ordered lists with their start number', () => {
    const [block] = parseMarkdown('3. tercero\n4. cuarto');
    expect(block).toMatchObject({ type: 'list', ordered: true, start: 3 });
    if (block?.type !== 'list') return;
    expect(block.items).toHaveLength(2);
  });

  it('nests sub-lists inside their parent item', () => {
    const [block] = parseMarkdown('1. uno\n   - sub a\n   - sub b\n2. dos');
    if (block?.type !== 'list') throw new Error('expected a list');
    const nested = block.items[0]?.children.find((c) => c.type === 'list');
    expect(nested).toMatchObject({ type: 'list', ordered: false });
    if (nested?.type !== 'list') return;
    expect(
      nested.items.map((item) =>
        textOf(item.children[0]?.type === 'plain' ? item.children[0].children : []),
      ),
    ).toEqual(['sub a', 'sub b']);
  });

  it('marks GFM task items as checked or open, and plain items as null', () => {
    const [block] = parseMarkdown('- [x] hecho\n- [ ] pendiente\n- simple');
    if (block?.type !== 'list') throw new Error('expected a list');
    expect(block.items.map((item) => item.checked)).toEqual([true, false, null]);
  });
});

describe('parseMarkdown — quotes, rules and tables', () => {
  it('parses blockquotes into their own block children', () => {
    const [block] = parseMarkdown('> cita\n> segunda');
    expect(block?.type).toBe('blockquote');
    if (block?.type !== 'blockquote') return;
    expect(block.children[0]?.type).toBe('paragraph');
  });

  it('parses horizontal rules', () => {
    expect(parseMarkdown('---')).toEqual([{ type: 'hr' }]);
  });

  it('keeps table alignment on each cell', () => {
    const [block] = parseMarkdown('| izq | der |\n|:--|--:|\n| 1 | 2 |');
    expect(block?.type).toBe('table');
    if (block?.type !== 'table') return;
    expect(block.header.map((c) => c.align)).toEqual(['left', 'right']);
    expect(block.rows[0]?.map((c) => textOf(c.children))).toEqual(['1', '2']);
    expect(block.rows[0]?.[1]?.align).toBe('right');
  });
});

describe('parseMarkdown — links and untrusted markup', () => {
  it('keeps web links and drops dangerous destinations to plain text', () => {
    const [block] = parseMarkdown('[bueno](https://example.com/a) y [malo](javascript:alert(1))');
    if (block?.type !== 'paragraph') throw new Error('expected a paragraph');
    const links = block.children.filter((n) => n.type === 'link');
    expect(links[0]).toMatchObject({ type: 'link', href: 'https://example.com/a' });
    expect(links[1]).toMatchObject({ type: 'link', href: null });
    expect(textOf(block.children)).toBe('bueno y malo');
  });

  it('shows raw HTML as the text it was written as', () => {
    const [block] = parseMarkdown('<script>alert(1)</script>');
    expect(block?.type === 'paragraph' && textOf(block.children)).toContain('<script>');
  });

  it('replaces images with their alt text rather than loading them', () => {
    const [block] = parseMarkdown('![diagrama](https://example.com/d.png)');
    expect(block?.type === 'paragraph' && block.children.every((n) => n.type !== 'link')).toBe(
      true,
    );
    expect(block?.type === 'paragraph' && textOf(block.children)).toBe('diagrama');
  });
});

describe('safeHref', () => {
  it('allows absolute http, https and mailto links', () => {
    expect(safeHref('https://sofee.dev/x')).toBe('https://sofee.dev/x');
    expect(safeHref('http://example.com')).toBe('http://example.com/');
    expect(safeHref('mailto:ana@example.com')).toBe('mailto:ana@example.com');
  });

  it('rejects scripts, data URLs, relative paths and empty values', () => {
    expect(safeHref('javascript:alert(1)')).toBeNull();
    expect(safeHref('data:text/html,<b>x</b>')).toBeNull();
    expect(safeHref('/notes/informe.md')).toBeNull();
    expect(safeHref('')).toBeNull();
    expect(safeHref(null)).toBeNull();
  });
});
