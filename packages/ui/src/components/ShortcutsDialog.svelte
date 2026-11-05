<!--
  ux-foundations.md §6 — the full keyboard reference, opened from the header's More menu.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import Dialog from './Dialog.svelte';
  import { shortcutRows } from '../shortcuts.js';

  interface Props {
    t: Translate;
    triggerEl?: HTMLElement | null;
    onClose: () => void;
  }

  let { t, triggerEl = null, onClose }: Props = $props();

  let rows = $derived(shortcutRows(t));
</script>

<Dialog titleText={t('shortcuts.title')} {triggerEl} {onClose}>
  <dl class="shortcut-list">
    {#each rows as row, i (i)}
      <div class="row">
        <dt><kbd>{row.keys}</kbd></dt>
        <dd>{row.description}</dd>
      </div>
    {/each}
  </dl>
</Dialog>

<style>
  .shortcut-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
  }

  .row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4);
  }

  dt {
    flex-shrink: 0;
  }

  dd {
    margin: 0;
    text-align: right;
    color: var(--p-ink);
    font-size: 14px;
  }

  kbd {
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 12px;
    padding: 3px var(--space-2);
    border-radius: var(--radius-swatch);
    background: var(--p-surf-2);
    border: 1px solid var(--p-line);
    color: var(--p-mut);
    white-space: nowrap;
  }
</style>
