<!--
  ux-foundations.md §4.5 — an inline superscript reference. Hovering or focusing it previews the
  source; clicking opens it (a new tab for a URL, or the Attachments panel for a local document
  — every mock citation is a URL, so only that path is wired up here).
-->
<script lang="ts">
  import type { Citation, Translate } from '@sofee/core';
  import { IconExternalLink } from '@sofee/icons';

  interface Props {
    citation: Citation;
    t: Translate;
  }

  let { citation, t }: Props = $props();
</script>

<span class="citation-host">
  <a
    class="citation-ref"
    href={citation.url}
    target="_blank"
    rel="noreferrer noopener"
    aria-describedby="citation-preview-{citation.index}"
  >
    <sup>[{citation.index}]</sup>
  </a>
  <span class="citation-preview" id="citation-preview-{citation.index}" role="tooltip">
    <strong>{t('citation.source', { index: citation.index })}</strong>
    <span>{citation.title}</span>
    <span class="citation-url">
      {citation.url}
      <IconExternalLink size={12} />
    </span>
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

  .citation-url {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--p-mut);
    word-break: break-all;
  }
</style>
