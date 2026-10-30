<!--
  ux-foundations.md §4.5 — an inline superscript reference. Hovering or focusing it previews the
  source; clicking opens it: a new tab for a web URL, or the Attachments panel for a team document
  or an attachment (roadmap U4). Team documents and attachments have no URL, so they are buttons
  that call `onOpen`, which the app answers by opening that source's panel.
-->
<script lang="ts">
  import type { Citation, Translate } from '@sofee/core';
  import { IconExternalLink } from '@sofee/icons';
  import { safeHref } from '../markdown/safe-href.js';

  interface Props {
    citation: Citation;
    t: Translate;
    /** Opens a team document or attachment. `trigger` is the element to return focus to. */
    onOpen?: (citation: Citation, trigger: HTMLElement) => void;
  }

  let { citation, t, onOpen }: Props = $props();

  let href = $derived(safeHref(citation.url));
  let isLocal = $derived(citation.kind === 'kb' || citation.kind === 'attachment');
  let kindLabel = $derived(
    citation.kind === 'attachment'
      ? t('agent.sources.attachment')
      : t('agent.sources.teamDocument'),
  );
  let buttonEl: HTMLButtonElement | null = $state(null);
</script>

<span class="citation-host">
  {#if href}
    <a
      class="citation-ref"
      {href}
      target="_blank"
      rel="noreferrer noopener"
      aria-describedby="citation-preview-{citation.index}"
    >
      <sup>[{citation.index}]</sup>
    </a>
  {:else if isLocal && onOpen}
    <button
      bind:this={buttonEl}
      type="button"
      class="citation-ref citation-button"
      aria-describedby="citation-preview-{citation.index}"
      aria-label={t('citation.source', { index: citation.index })}
      onclick={() => {
        if (buttonEl) onOpen?.(citation, buttonEl);
      }}
    >
      <sup>[{citation.index}]</sup>
    </button>
  {:else}
    <span class="citation-ref">
      <sup>[{citation.index}]</sup>
    </span>
  {/if}
  <span class="citation-preview" id="citation-preview-{citation.index}" role="tooltip">
    <strong>{t('citation.source', { index: citation.index })}</strong>
    <span>{citation.title}</span>
    {#if isLocal}<span class="citation-kind">{kindLabel}</span>{/if}
    {#if citation.snippet}<span class="citation-snippet">{citation.snippet}</span>{/if}
    {#if href}
      <span class="citation-url">
        {href}
        <IconExternalLink size={12} />
      </span>
    {/if}
  </span>
</span>

<style>
  .citation-host {
    position: relative;
    display: inline-block;
  }

  .citation-ref {
    color: var(--p-acc);
    text-decoration: none;
    padding: 0 1px;
    border-radius: 3px;
  }

  /* Rendered as a button for team documents and attachments: reset the button chrome so the
     reference still reads as a superscript link, and keep the focus ring visible. Inline text
     keeps its own size, so the reference never pushes the line it sits on. */
  .citation-button {
    border: none;
    background: none;
    font: inherit;
    line-height: inherit;
    cursor: pointer;
    padding: 0 1px;
  }

  .citation-ref:hover,
  .citation-ref:focus-visible {
    text-decoration: underline;
  }

  .citation-ref:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .citation-preview {
    position: absolute;
    z-index: 5;
    bottom: calc(100% + var(--space-2));
    left: 50%;
    translate: -50% 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: max-content;
    max-width: 260px;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-menu);
    background: var(--p-surf-2);
    border: 1px solid var(--p-line);
    box-shadow: var(--p-shadow-menu);
    font-size: 12px;
    color: var(--p-ink);
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--motion-menu-duration) var(--motion-menu-easing);
  }

  .citation-host:hover .citation-preview,
  .citation-host:focus-within .citation-preview {
    opacity: 1;
  }

  .citation-kind {
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px;
    letter-spacing: 0.02em;
  }

  .citation-snippet {
    color: var(--p-mut);
    line-height: 1.4;
  }

  .citation-url {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--p-mut);
    word-break: break-all;
  }
</style>
