/**
 * Turns the mock assistant's lightweight markdown (headings, bold, bullet lists, `[n]`
 * citation markers — see packages/core/src/mock/mock-assistant.ts) into a small tree Svelte can
 * walk with `{#each}`, instead of piping raw text through `{@html}`. The content is always
 * local mock output, never third-party HTML, but structured control flow is easier to keep in
 * sync with CitationRef than a raw-HTML-plus-sanitizer approach would be.
 *
 * This is rendering-support code, not domain logic — it knows nothing about messages, threads,
 * or the assistant, only about turning a string into display segments — which is why it lives
 * in packages/ui rather than packages/core.
 */

export type InlineSegment =
  | { type: 'text'; value: string }
  | { type: 'bold'; value: string }
  | { type: 'citation'; index: number };

export type Block =
  | { type: 'heading'; level: 2 | 3; segments: InlineSegment[] }
  | { type: 'paragraph'; segments: InlineSegment[] }
  | { type: 'bullets'; items: InlineSegment[][] };

function parseInline(text: string): InlineSegment[] {
  const segments: InlineSegment[] = [];
  const pattern = /\*\*(.+?)\*\*|\[(\d+)\]/g;
  let lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) segments.push({ type: 'text', value: text.slice(lastIndex, index) });
    if (match[1] !== undefined) {
      segments.push({ type: 'bold', value: match[1] });
    } else if (match[2] !== undefined) {
      segments.push({ type: 'citation', index: Number(match[2]) });
    }
    lastIndex = index + match[0].length;
  }
  if (lastIndex < text.length) segments.push({ type: 'text', value: text.slice(lastIndex) });
  return segments;
}

export function formatMessage(text: string): Block[] {
  const blocks: Block[] = [];
  let bulletBuffer: InlineSegment[][] | null = null;

  const flushBullets = (): void => {
    if (bulletBuffer && bulletBuffer.length > 0)
      blocks.push({ type: 'bullets', items: bulletBuffer });
    bulletBuffer = null;
  };

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (line.length === 0) {
      flushBullets();
      continue;
    }
    if (line.startsWith('### ')) {
      flushBullets();
      blocks.push({ type: 'heading', level: 3, segments: parseInline(line.slice(4)) });
    } else if (line.startsWith('## ')) {
      flushBullets();
      blocks.push({ type: 'heading', level: 2, segments: parseInline(line.slice(3)) });
    } else if (line.startsWith('- ')) {
      bulletBuffer ??= [];
      bulletBuffer.push(parseInline(line.slice(2)));
    } else {
      flushBullets();
      blocks.push({ type: 'paragraph', segments: parseInline(line) });
    }
  }
  flushBullets();
  return blocks;
}
