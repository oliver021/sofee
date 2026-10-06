<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    open: boolean;
    title: string;
    confirmLabel?: string;
    cancelLabel?: string;
    danger?: boolean;
    busy?: boolean;
    onconfirm: () => void;
    oncancel: () => void;
    children?: Snippet;
  }

  let {
    open,
    title,
    confirmLabel = 'Confirmar',
    cancelLabel = 'Cancelar',
    danger = false,
    busy = false,
    onconfirm,
    oncancel,
    children,
  }: Props = $props();
</script>

{#if open}
  <div class="scrim" role="presentation" onclick={oncancel}></div>
  <div class="dialog" role="alertdialog" aria-modal="true" aria-label={title}>
    <h2 class="title">{title}</h2>
    <div class="body">
      {@render children?.()}
    </div>
    <div class="actions">
      <button class="btn" type="button" onclick={oncancel} disabled={busy}>
        {cancelLabel}
      </button>
      <button
        class="btn {danger ? 'danger' : 'primary'}"
        type="button"
        onclick={onconfirm}
        disabled={busy}
      >
        {confirmLabel}
      </button>
    </div>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 49;
    background: color-mix(in oklab, var(--p-bg) 45%, transparent);
  }

  .dialog {
    position: fixed;
    z-index: 50;
    inset-inline: 50%;
    top: 50%;
    transform: translate(-50%, -50%);
    width: min(440px, calc(100vw - 32px));
    padding: 20px;
    border: 1px solid var(--p-line);
    border-radius: 14px;
    background: var(--p-surf);
    box-shadow: var(--p-shadow-panel);
  }

  .title {
    margin: 0 0 8px;
    font-size: 16px;
    font-weight: 600;
  }

  .body {
    color: var(--p-mut);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 20px;
  }
</style>
