<!--
  ux-foundations.md §2.3 — used for the temporary-chat "leaving loses this conversation for
  good" confirmation, and generically wherever else a destructive action needs one.
-->
<script lang="ts">
  import Dialog from './Dialog.svelte';

  interface Props {
    titleText: string;
    bodyText: string;
    confirmLabel: string;
    cancelLabel: string;
    triggerEl?: HTMLElement | null;
    onConfirm: () => void;
    onCancel: () => void;
  }

  let {
    titleText,
    bodyText,
    confirmLabel,
    cancelLabel,
    triggerEl = null,
    onConfirm,
    onCancel,
  }: Props = $props();
</script>

<Dialog {titleText} {triggerEl} onClose={onCancel}>
  <p class="body-text">{bodyText}</p>
  <div class="actions">
    <button type="button" class="btn-secondary" onclick={onCancel}>{cancelLabel}</button>
    <button type="button" class="btn-destructive" onclick={onConfirm}>{confirmLabel}</button>
  </div>
</Dialog>

<style>
  .body-text {
    margin: 0 0 var(--space-5);
    color: var(--p-ink);
    font-size: 14px;
    line-height: 1.6;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .btn-secondary,
  .btn-destructive {
    padding: var(--space-2) var(--space-4);
    min-height: var(--target-min);
    border-radius: var(--radius-icon-btn);
    font: inherit;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
  }

  .btn-secondary {
    border: 1px solid var(--p-line);
    background: transparent;
    color: var(--p-ink);
  }

  .btn-secondary:hover {
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
  }

  .btn-destructive {
    border: 1px solid transparent;
    background: var(--sem-critical);
    color: var(--sem-critical-ink);
  }

  .btn-destructive:hover {
    background: color-mix(in oklab, var(--sem-critical) 85%, black);
  }

  .btn-secondary:focus-visible,
  .btn-destructive:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }
</style>
