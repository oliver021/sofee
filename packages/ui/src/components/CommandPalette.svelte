<!--
  ux-foundations.md §6 — Ctrl/Cmd+K. A filterable list of the same actions the rails and menus
  expose, for anyone who would rather not leave the keyboard.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import Dialog from './Dialog.svelte';
  import type { MenuItemConfig } from '../types.js';
  import { scrollbars } from '../actions/scrollbars.js';

  interface Props {
    t: Translate;
    triggerEl?: HTMLElement | null;
    commands: MenuItemConfig[];
    onClose: () => void;
  }

  let { t, triggerEl = null, commands, onClose }: Props = $props();

  let query = $state('');
  let activeIndex = $state(0);
  let resultEls: (HTMLButtonElement | null)[] = $state([]);

  let filtered = $derived(
    query.trim().length === 0
      ? commands
      : commands.filter((c) => c.label.toLowerCase().includes(query.trim().toLowerCase())),
  );

  function run(command: MenuItemConfig): void {
    command.onActivate();
    onClose();
  }

  function onInputKeydown(event: KeyboardEvent): void {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, Math.max(filtered.length - 1, 0));
      resultEls[activeIndex]?.scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      resultEls[activeIndex]?.scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const command = filtered[activeIndex];
      if (command) run(command);
    }
  }
</script>

<Dialog titleText={t('commandPalette.title')} {triggerEl} {onClose}>
  <input
    type="text"
    class="query"
    placeholder={t('commandPalette.placeholder')}
    aria-label={t('commandPalette.placeholder')}
    bind:value={query}
    onkeydown={onInputKeydown}
    oninput={() => (activeIndex = 0)}
  />
  {#if filtered.length === 0}
    <p class="empty">{t('commandPalette.empty')}</p>
  {:else}
    <ul
      class="results"
      use:scrollbars={{ autoHide: 'leave' }}
      role="listbox"
      aria-label={t('commandPalette.title')}
    >
      {#each filtered as command, i (command.id)}
        <li>
          <button
            bind:this={resultEls[i]}
            type="button"
            class="result"
            class:active={i === activeIndex}
            role="option"
            aria-selected={i === activeIndex}
            onclick={() => run(command)}
            onmouseenter={() => (activeIndex = i)}
          >
            {#if command.icon}
              {@const Icon = command.icon}
              <Icon size={18} />
            {/if}
            {command.label}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</Dialog>

<style>
  .query {
    width: 100%;
    padding: var(--space-3);
    margin-bottom: var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: 1px solid var(--p-line);
    background: var(--p-surf-2);
    color: var(--p-ink);
    font: inherit;
  }

  .query:focus {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .empty {
    color: var(--p-mut);
    font-size: 14px;
    text-align: center;
    padding: var(--space-4) 0;
  }

  .results {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    max-height: 320px;
    overflow-y: auto;
  }

  .result {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--target-min);
    padding: 0 var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: none;
    background: transparent;
    color: var(--p-ink);
    font: inherit;
    font-size: 14px;
    text-align: left;
    cursor: pointer;
  }

  .result.active,
  .result:hover {
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
  }

  .result:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: -2px;
  }
</style>
