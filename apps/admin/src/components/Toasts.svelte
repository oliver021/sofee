<script lang="ts">
  import { IconCheck, IconClose, IconTrash } from '@sofee/icons';
  import { ui } from '../lib/ui.svelte.js';
</script>

<div class="toasts" aria-live="polite">
  {#each ui.toasts as toast (toast.id)}
    <div class="toast {toast.kind}" role="status">
      <span class="mark">
        {#if toast.kind === 'ok'}
          <IconCheck size={16} />
        {:else}
          <IconTrash size={15} />
        {/if}
      </span>
      <span class="msg">{toast.message}</span>
      <button
        class="dismiss"
        type="button"
        onclick={() => ui.dismiss(toast.id)}
        aria-label="Cerrar notificación"
      >
        <IconClose size={14} />
      </button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    inset: auto 16px 16px auto;
    z-index: 60;
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: min(420px, calc(100vw - 32px));
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border: 1px solid var(--p-line);
    border-radius: 10px;
    background: var(--p-surf-2);
    box-shadow: var(--p-shadow-panel);
  }

  .toast.error {
    border-color: var(--sem-critical);
  }

  .mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 999px;
    flex: none;
    background: var(--sem-success);
    color: var(--sem-success-ink);
  }

  .toast.error .mark {
    background: var(--sem-critical);
    color: var(--sem-critical-ink);
  }

  .msg {
    flex: 1;
  }

  .dismiss {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--p-mut);
    cursor: pointer;
  }

  .dismiss:hover {
    background: var(--p-hi);
    color: var(--p-ink);
  }
</style>
