<!--
  ux-foundations.md §4.3 — "Empty thread: The canvas is the hero: greeting, three concrete
  starting moves, composer. No empty-box illustration."

  roadmap U7: the starting moves come from the team's admin, per mode. The app passes them in
  (falling back to its own copy when the server has none), so this component only lays them out.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';

  interface Props {
    t: Translate;
    /** The starting moves to show, already resolved by the app. */
    starters: readonly string[];
    onStarterSelect: (text: string) => void;
  }

  let { t, starters, onStarterSelect }: Props = $props();
</script>

<div class="empty-state">
  <h1 class="greeting">{t('thread.emptyGreeting')}</h1>
  <p class="hint">{t('thread.emptyHint')}</p>
  <div class="starters">
    {#each starters as starter, i (i)}
      <button type="button" class="starter" onclick={() => onStarterSelect(starter)}>
        {starter}
      </button>
    {/each}
  </div>
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    gap: var(--space-4);
    min-height: 40vh;
    padding: var(--space-6) var(--space-4);
  }

  .greeting {
    margin: 0;
    font-family: var(--p-display);
    font-size: clamp(28px, 4vw, 40px);
    font-weight: 600;
    text-wrap: balance;
    background: var(--p-title-grad);
    background-clip: text;
    -webkit-background-clip: text;
    color: transparent;
  }

  .hint {
    margin: 0;
    color: var(--p-mut);
    font-size: 15px;
  }

  .starters {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: var(--space-3);
    margin-top: var(--space-3);
    max-width: 640px;
  }

  .starter {
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-panel);
    border: 1px solid var(--p-line);
    background: var(--p-surf);
    color: var(--p-ink);
    font: inherit;
    font-size: 14px;
    text-align: left;
    cursor: pointer;
    max-width: 260px;
  }

  .starter:hover {
    border-color: var(--p-line-2);
    background: var(--p-surf-2);
  }

  .starter:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }
</style>
