<script lang="ts">
  import type { Snippet } from 'svelte';
  import { IconClose } from '@sofee/icons';

  interface Props {
    open: boolean;
    title: string;
    onclose: () => void;
    children?: Snippet;
  }

  let { open, title, onclose, children }: Props = $props();
</script>

{#if open}
  <div class="scrim" role="presentation" onclick={onclose}></div>
  <div class="drawer" role="dialog" aria-modal="true" aria-label={title}>
    <header class="head">
      <h2 class="title">{title}</h2>
      <button class="icon-btn" type="button" onclick={onclose} aria-label="Cerrar">
        <IconClose />
      </button>
    </header>
    <div class="body">
      {@render children?.()}
    </div>
  </div>
{/if}

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 39;
    background: color-mix(in oklab, var(--p-bg) 45%, transparent);
  }

  .drawer {
    position: fixed;
    inset-block: 0;
    right: 0;
    z-index: 40;
    display: flex;
    flex-direction: column;
    width: min(540px, 100vw);
    background: var(--p-surf);
    border-left: 1px solid var(--p-line);
    box-shadow: var(--p-shadow-panel);
    animation: slide-in 180ms ease-out;
  }

  @keyframes slide-in {
    from {
      transform: translateX(32px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 20px;
    border-bottom: 1px solid var(--p-line);
  }

  .title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }

  .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--p-mut);
    cursor: pointer;
  }

  .icon-btn:hover {
    background: var(--p-hi);
    color: var(--p-ink);
  }

  .body {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
  }
</style>
