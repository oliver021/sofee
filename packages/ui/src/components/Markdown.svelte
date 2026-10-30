<!--
  A model reply, rendered from the block tree in ../markdown/parse-markdown.ts. The tree is walked
  with {#each} and recursive snippets, so model output never reaches {@html}: every piece becomes
  an element or a text node. `[n]` markers become CitationRef when the citation list has that index
  (ux-foundations.md §4.5); an unknown index stays as plain "[n]" text. Tables scroll inside their
  own box, so a wide one never moves the page.
-->
<script lang="ts">
  import type { Citation, Translate } from '@sofee/core';
  import CitationRef from './CitationRef.svelte';
  import CodeBlock from './CodeBlock.svelte';
  import VisuallyHidden from './VisuallyHidden.svelte';
  import {
    parseMarkdown,
    type MarkdownBlock,
    type MarkdownInline,
    type MarkdownListItem,
  } from '../markdown/parse-markdown.js';

  interface Props {
    text: string;
    citations?: readonly Citation[];
    t: Translate;
    /** Opens a team document or attachment from a `[n]` reference (roadmap U4). */
    onOpenSource?: (citation: Citation, trigger: HTMLElement) => void;
  }

  let { text, citations = [], t, onOpenSource }: Props = $props();

  let blocks = $derived(parseMarkdown(text));

  const HEADING_TAGS = { 1: 'h1', 2: 'h2', 3: 'h3', 4: 'h4' } as const;

  function citationFor(index: number): Citation | undefined {
    return citations.find((citation) => citation.index === index);
  }
</script>

{#snippet inlineNodes(nodes: readonly MarkdownInline[])}
  {#each nodes as node, i (i)}
    {#if node.type === 'text'}{node.value}
    {:else if node.type === 'citation'}
      {@const citation = citationFor(node.index)}
      {#if citation}<CitationRef {citation} {t} onOpen={onOpenSource} />{:else}[{node.index}]{/if}
    {:else if node.type === 'code'}<code class="inline-code">{node.value}</code>
    {:else if node.type === 'break'}<br />
    {:else if node.type === 'strong'}<strong>{@render inlineNodes(node.children)}</strong>
    {:else if node.type === 'em'}<em>{@render inlineNodes(node.children)}</em>
    {:else if node.type === 'del'}<del>{@render inlineNodes(node.children)}</del>
    {:else if node.type === 'link'}
      {#if node.href}
        <a href={node.href} target="_blank" rel="noopener noreferrer"
          >{@render inlineNodes(node.children)}<VisuallyHidden
            >{t('citation.openInNewTab')}</VisuallyHidden
          ></a
        >
      {:else}{@render inlineNodes(node.children)}{/if}
    {/if}
  {/each}
{/snippet}

{#snippet listItems(items: readonly MarkdownListItem[])}
  {#each items as item, i (i)}
    <li>
      {#if item.checked !== null}
        <input
          type="checkbox"
          class="task-box"
          disabled
          checked={item.checked}
          aria-hidden="true"
          tabindex="-1"
        />
      {/if}
      {@render blockNodes(item.children)}
    </li>
  {/each}
{/snippet}

{#snippet blockNodes(nodes: readonly MarkdownBlock[])}
  {#each nodes as block, i (i)}
    {#if block.type === 'paragraph'}
      <p>{@render inlineNodes(block.children)}</p>
    {:else if block.type === 'heading'}
      <svelte:element this={HEADING_TAGS[block.level]} class="heading">
        {@render inlineNodes(block.children)}
      </svelte:element>
    {:else if block.type === 'code'}
      <CodeBlock code={block.text} lang={block.lang} {t} />
    {:else if block.type === 'blockquote'}
      <blockquote>{@render blockNodes(block.children)}</blockquote>
    {:else if block.type === 'list'}
      {#if block.ordered}
        <ol start={block.start}>{@render listItems(block.items)}</ol>
      {:else}
        <ul>{@render listItems(block.items)}</ul>
      {/if}
    {:else if block.type === 'plain'}
      {@render inlineNodes(block.children)}
    {:else if block.type === 'hr'}
      <hr />
    {:else if block.type === 'table'}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              {#each block.header as cell, c (c)}
                <th style:text-align={cell.align ?? undefined}
                  >{@render inlineNodes(cell.children)}</th
                >
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each block.rows as row, r (r)}
              <tr>
                {#each row as cell, c (c)}
                  <td style:text-align={cell.align ?? undefined}
                    >{@render inlineNodes(cell.children)}</td
                  >
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/each}
{/snippet}

<div class="markdown">
  {@render blockNodes(blocks)}
</div>

<style>
  .markdown {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .markdown > :global(:last-child) {
    margin-bottom: 0;
  }

  p {
    margin: 0 0 var(--space-3);
  }

  p:last-child,
  li > :last-child {
    margin-bottom: 0;
  }

  .heading {
    margin: var(--space-4) 0 var(--space-2);
    font-family: var(--p-display);
    color: var(--p-ink);
    line-height: 1.3;
  }

  h1.heading {
    font-size: 20px;
  }

  h2.heading {
    font-size: 18px;
  }

  h3.heading {
    font-size: 16px;
  }

  h4.heading {
    font-size: 15px;
  }

  ul,
  ol {
    margin: 0 0 var(--space-3);
    padding-left: 1.3em;
  }

  li {
    margin-bottom: var(--space-1);
  }

  li > :global(ul),
  li > :global(ol) {
    margin-top: var(--space-1);
    margin-bottom: 0;
  }

  .task-box {
    margin: 0 var(--space-2) 0 0;
    accent-color: var(--p-acc);
    vertical-align: middle;
  }

  blockquote {
    margin: 0 0 var(--space-3);
    padding: var(--space-1) var(--space-4);
    border-inline-start: 3px solid var(--p-line-2);
    color: var(--p-mut);
  }

  hr {
    margin: var(--space-4) 0;
    border: none;
    border-top: 1px solid var(--p-line);
  }

  a {
    color: var(--p-acc);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  a:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: 3px;
  }

  .inline-code {
    padding: 1px 5px;
    border-radius: 4px;
    border: 1px solid var(--p-line);
    background: var(--p-surf-2);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.9em;
  }

  .table-wrap {
    max-width: 100%;
    margin: 0 0 var(--space-3);
    overflow-x: auto;
  }

  table {
    border-collapse: collapse;
    font-size: 14px;
  }

  th,
  td {
    padding: var(--space-1) var(--space-3);
    border: 1px solid var(--p-line);
    vertical-align: top;
  }

  th {
    background: var(--p-surf-2);
    font-weight: 600;
  }
</style>
