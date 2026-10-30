import { Lexer, type Token, type Tokens } from 'marked';
import { safeHref } from './safe-href.js';

/**
 * Turns a model reply into a block tree that Svelte walks with `{#each}`. The reply is parsed by
 * marked's Lexer (CommonMark + GFM) and only its structure is kept: nothing here produces HTML, so
 * the renderer never needs `{@html}`. Two Sofee rules sit on top of markdown: `[n]` markers become
 * citation nodes, and raw HTML is shown as the text it was written as.
 *
 * This is rendering support, not domain logic, which is why it lives in packages/ui.
 */

export type MarkdownInline =
  | { readonly type: 'text'; readonly value: string }
  | { readonly type: 'citation'; readonly index: number }
  | { readonly type: 'code'; readonly value: string }
  | { readonly type: 'break' }
  | { readonly type: 'strong' | 'em' | 'del'; readonly children: readonly MarkdownInline[] }
  | {
      readonly type: 'link';
      readonly href: string | null;
      readonly children: readonly MarkdownInline[];
    };

export type MarkdownAlign = 'left' | 'center' | 'right' | null;

export interface MarkdownCell {
  readonly align: MarkdownAlign;
  readonly children: readonly MarkdownInline[];
}

export interface MarkdownListItem {
  /** null for an ordinary item, true or false for a GFM task item. */
  readonly checked: boolean | null;
  readonly children: readonly MarkdownBlock[];
}

export type MarkdownBlock =
  | { readonly type: 'paragraph'; readonly children: readonly MarkdownInline[] }
  | {
      readonly type: 'heading';
      readonly level: 1 | 2 | 3 | 4;
      readonly children: readonly MarkdownInline[];
    }
  /** `text` is the whole body, unclosed fences included: a stream that stops mid-block still reads as code. */
  | { readonly type: 'code'; readonly lang: string | null; readonly text: string }
  | { readonly type: 'blockquote'; readonly children: readonly MarkdownBlock[] }
  | {
      readonly type: 'list';
      readonly ordered: boolean;
      readonly start: number;
      readonly items: readonly MarkdownListItem[];
    }
  /** Inline content that sits directly inside a tight list item, with no paragraph around it. */
  | { readonly type: 'plain'; readonly children: readonly MarkdownInline[] }
  | { readonly type: 'hr' }
  | {
      readonly type: 'table';
      readonly header: readonly MarkdownCell[];
      readonly rows: readonly (readonly MarkdownCell[])[];
    };

/** The `[n]` markers the mock and the backend use for citations (see mock-assistant.ts). */
const CITATION_MARKER = /\[(\d{1,3})\]/g;

/**
 * A stream can stop on a bare run of one or two backticks or tildes that becomes a fence on the
 * next chunk. Dropping that trailing line keeps the punctuation from flashing on screen for a frame.
 */
const PARTIAL_FENCE_AT_END = /(^|\n)[ \t]{0,3}(`{1,2}|~{1,2})$/;

function withoutPartialFence(source: string): string {
  return source.replace(PARTIAL_FENCE_AT_END, '$1');
}

function textNodes(value: string): MarkdownInline[] {
  const nodes: MarkdownInline[] = [];
  let last = 0;
  for (const match of value.matchAll(CITATION_MARKER)) {
    const at = match.index ?? 0;
    if (at > last) nodes.push({ type: 'text', value: value.slice(last, at) });
    nodes.push({ type: 'citation', index: Number(match[1] ?? 0) });
    last = at + match[0].length;
  }
  if (last < value.length) nodes.push({ type: 'text', value: value.slice(last) });
  return nodes;
}

function inlinesOf(tokens: readonly Token[] | undefined): MarkdownInline[] {
  return (tokens ?? []).flatMap(inlineOf);
}

function inlineOf(token: Token): MarkdownInline[] {
  switch (token.type) {
    case 'text': {
      const text = token as Tokens.Text;
      return text.tokens ? inlinesOf(text.tokens) : textNodes(text.text);
    }
    case 'escape':
      return textNodes((token as Tokens.Escape).text);
    case 'strong':
    case 'em':
    case 'del': {
      const emphasis = token as Tokens.Strong | Tokens.Em | Tokens.Del;
      return [{ type: emphasis.type, children: inlinesOf(emphasis.tokens) }];
    }
    case 'codespan':
      return [{ type: 'code', value: (token as Tokens.Codespan).text }];
    case 'br':
      return [{ type: 'break' }];
    case 'link': {
      const link = token as Tokens.Link;
      return [{ type: 'link', href: safeHref(link.href), children: inlinesOf(link.tokens) }];
    }
    case 'image':
      // Images are not fetched from model output; the alt text stands in for them.
      return textNodes((token as Tokens.Image).text);
    case 'html':
      // Raw HTML is never rendered. It is shown as the text it was written as.
      return textNodes((token as Tokens.HTML).text);
    default:
      return 'text' in token && typeof token.text === 'string' ? textNodes(token.text) : [];
  }
}

function cellOf(cell: Tokens.TableCell): MarkdownCell {
  return { align: cell.align, children: inlinesOf(cell.tokens) };
}

function clampHeadingLevel(depth: number): 1 | 2 | 3 | 4 {
  if (depth <= 1) return 1;
  if (depth >= 4) return 4;
  return depth as 2 | 3;
}

function listItemOf(item: Tokens.ListItem): MarkdownListItem {
  return {
    checked: item.task ? item.checked === true : null,
    children: blocksOf(item.tokens),
  };
}

function blockOf(token: Token): MarkdownBlock[] {
  switch (token.type) {
    case 'space':
    case 'def':
      return [];
    case 'paragraph':
      return [{ type: 'paragraph', children: inlinesOf((token as Tokens.Paragraph).tokens) }];
    case 'heading': {
      const heading = token as Tokens.Heading;
      return [
        {
          type: 'heading',
          level: clampHeadingLevel(heading.depth),
          children: inlinesOf(heading.tokens),
        },
      ];
    }
    case 'code': {
      const code = token as Tokens.Code;
      const lang = code.lang?.trim().split(/\s+/)[0] ?? '';
      return [{ type: 'code', lang: lang.length > 0 ? lang : null, text: code.text }];
    }
    case 'blockquote':
      return [{ type: 'blockquote', children: blocksOf((token as Tokens.Blockquote).tokens) }];
    case 'list': {
      const list = token as Tokens.List;
      return [
        {
          type: 'list',
          ordered: list.ordered,
          start: typeof list.start === 'number' ? list.start : 1,
          items: list.items.map(listItemOf),
        },
      ];
    }
    case 'text': {
      const text = token as Tokens.Text;
      return [{ type: 'plain', children: inlinesOf(text.tokens ?? [text]) }];
    }
    case 'hr':
      return [{ type: 'hr' }];
    case 'table': {
      const table = token as Tokens.Table;
      return [
        {
          type: 'table',
          header: table.header.map(cellOf),
          rows: table.rows.map((row) => row.map(cellOf)),
        },
      ];
    }
    case 'html':
      return [{ type: 'paragraph', children: textNodes((token as Tokens.HTML).text) }];
    default:
      if ('text' in token && typeof token.text === 'string') {
        return [{ type: 'paragraph', children: textNodes(token.text) }];
      }
      return [];
  }
}

function blocksOf(tokens: readonly Token[] | undefined): MarkdownBlock[] {
  return (tokens ?? []).flatMap(blockOf);
}

/** Parses a reply, complete or still streaming, into a block tree. Empty or whitespace-only input
 * yields no blocks. */
export function parseMarkdown(source: string): MarkdownBlock[] {
  const text = withoutPartialFence(source);
  if (text.trim().length === 0) return [];
  return blocksOf(new Lexer({ gfm: true }).lex(text));
}
