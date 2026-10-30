<!--
  ux-foundations.md §4.5 and roadmap U4: the reply's sources, under the text. A web source opens in
  a new tab; a team document or an attachment opens the Attachments panel on that document. Each
  one shows its host (or where it lives) and, when the run kept one, the excerpt it came from.
-->
<script lang="ts">
  import type { Citation, Translate } from '@sofee/core';
  import { safeHref } from '../markdown/safe-href.js';
  import VisuallyHidden from './VisuallyHidden.svelte';
  import type { SourceView } from '../types.js';

  interface Props {
    sources: readonly SourceView[];
    t: Translate;
    onOpen?: (citation: Citation, trigger: HTMLElement) => void;
  }

  let { sources, t, onOpen }: Props = $props();
</script>

<section class="sources" aria-label={t('agent.sources.heading')}>
  <p class="heading">{t('agent.sources.heading')}</p>
  <ol class="list">
    {#each sources as source (source.index)}
      {@const href = safeHref(source.citation.url)}
      {@const local = source.citation.kind === 'kb' || source.citation.kind === 'attachment'}
      <li class="item">
        <span class="index" aria-hidden="true">{source.index}</span>
        <div class="body">
          {#if href}
            <a class="title" {href} target="_blank" rel="noreferrer noopener">
              {source.title}
              <VisuallyHidden>{t('citation.openInNewTab')}</VisuallyHidden>
            </a>
          {:else if local && onOpen}
            <button
              type="button"
              class="title as-button"
              onclick={(event) => onOpen?.(source.citation, event.currentTarget)}
            >
              {source.title}
              <VisuallyHidden>{t('citation.openInAttachments')}</VisuallyHidden>
            </button>
          {:else}
            <span class="title">{source.title}</span>
          {/if}
          <span class="meta">{source.meta}</span>
          {#if source.snippet}<p class="snippet">{source.snippet}</p>{/if}
        </div>
      </li>
    {/each}
  </ol>
</section>

<style>
  .sources {
    min-width: 0;
  }

  .heading {
    margin: 0 0 var(--space-2);
    color: var(--p-mut);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .item {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    min-width: 0;
    font-size: 14px;
  }

  .index {
    flex: none;
    min-width: 20px;
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 12px;
    padding-top: 2px;
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .title {
    color: var(--p-acc);
    text-align: start;
    overflow-wrap: anywhere;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .as-button {
    align-self: flex-start;
    min-height: var(--target-min);
    padding: 0;
    border: none;
    background: none;
    font: inherit;
    cursor: pointer;
  }

  span.title {
    color: var(--p-ink);
    text-decoration: none;
  }

  .title:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: 3px;
  }

  .meta {
    color: var(--p-mut);
    font-size: 12px;
  }

  .snippet {
    margin: var(--space-1) 0 0;
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.5;
  }
</style>
