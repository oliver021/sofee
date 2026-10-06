<!--
  ux-foundations.md §2.3/§8 — a dropdown menu anchored below its trigger button. Full keyboard
  semantics: role="menu"/menuitem (or menuitemradio for a checkable item, e.g. the palette or
  language pick), arrow keys, Home/End, single-character typeahead, Esc. Click-outside and Esc
  both close and return focus to the trigger, per ux-foundations.md §2.4's panel rules, which
  this follows too even though it is written for panels specifically.

  Positioned with `position: fixed` off the trigger's own `getBoundingClientRect()` rather than
  a popover/anchor library — the trigger is always one of a handful of fixed toolbar buttons, so
  this needs no general-purpose positioning engine.
-->
<script lang="ts">
  import { IconCheck } from '@sofee/icons';
  import type { MenuItemConfig } from '../types.js';

  interface Props {
    items: MenuItemConfig[];
    label: string;
    open: boolean;
    anchor: HTMLElement | null;
    align?: 'left' | 'right';
    onClose: () => void;
  }

  let { items, label, open, anchor, align = 'left', onClose }: Props = $props();

  let menuEl: HTMLDivElement | null = $state(null);
  let itemEls: (HTMLButtonElement | null)[] = $state([]);
  let typeahead = '';
  let typeaheadTimer: ReturnType<typeof setTimeout> | null = null;

  let position = $derived.by(() => {
    if (!anchor) return { top: 0, left: 0, right: undefined as number | undefined };
    const rect = anchor.getBoundingClientRect();
    const top = rect.bottom + 8;
    if (align === 'right') {
      return { top, left: undefined as number | undefined, right: window.innerWidth - rect.right };
    }
    return { top, left: rect.left, right: undefined as number | undefined };
  });

  function close(returnFocus: boolean): void {
    onClose();
    if (returnFocus) anchor?.focus();
  }

  function focusItem(index: number): void {
    const clamped = (index + items.length) % items.length;
    itemEls[clamped]?.focus();
  }

  function currentIndex(): number {
    const active = document.activeElement;
    return itemEls.findIndex((el) => el === active);
  }

  function activate(item: MenuItemConfig): void {
    item.onActivate();
    if (!item.keepOpen) close(true);
  }

  function onMenuKeydown(event: KeyboardEvent): void {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        focusItem(currentIndex() + 1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        focusItem(currentIndex() - 1);
        break;
      case 'Home':
        event.preventDefault();
        focusItem(0);
        break;
      case 'End':
        event.preventDefault();
        focusItem(items.length - 1);
        break;
      case 'Escape':
        event.preventDefault();
        close(true);
        break;
      case 'Tab':
        close(false);
        break;
      default:
        if (event.key.length === 1 && /[\p{L}\p{N}]/u.test(event.key)) {
          typeahead += event.key.toLowerCase();
          if (typeaheadTimer) clearTimeout(typeaheadTimer);
          typeaheadTimer = setTimeout(() => (typeahead = ''), 600);
          const match = items.findIndex((item) => item.label.toLowerCase().startsWith(typeahead));
          if (match >= 0) focusItem(match);
        }
    }
  }

  function onDocumentPointerDown(event: PointerEvent): void {
    const target = event.target as Node;
    if (menuEl?.contains(target) || anchor?.contains(target)) return;
    close(false);
  }

  $effect(() => {
    if (!open) return;
    const firstChecked = items.findIndex((item) => item.checked === true);
    queueMicrotask(() => focusItem(firstChecked >= 0 ? firstChecked : 0));
    document.addEventListener('pointerdown', onDocumentPointerDown);
    return () => document.removeEventListener('pointerdown', onDocumentPointerDown);
  });
</script>

{#if open}
  <div
    bind:this={menuEl}
    class="menu"
    role="menu"
    aria-label={label}
    tabindex="-1"
    style:top="{position.top}px"
    style:left={position.left !== undefined ? `${position.left}px` : undefined}
    style:right={position.right !== undefined ? `${position.right}px` : undefined}
    onkeydown={onMenuKeydown}
  >
    {#each items as item, i (item.id)}
      <button
        bind:this={itemEls[i]}
        type="button"
        class="menu-item"
        class:destructive={item.destructive}
        role={item.checked === undefined ? 'menuitem' : 'menuitemradio'}
        aria-checked={item.checked}
        tabindex="-1"
        onclick={() => activate(item)}
      >
        {#if item.icon}
          {@const Icon = item.icon}
          <Icon size={18} />
        {/if}
        <span class="menu-item-label">{item.label}</span>
        {#if item.checked}
          <IconCheck size={16} />
        {/if}
        {#if item.shortcut}
          <span class="menu-item-shortcut">{item.shortcut}</span>
        {/if}
      </button>
    {/each}
  </div>
{/if}

<style>
  .menu {
    position: fixed;
    z-index: 20;
    min-width: 220px;
    max-width: 320px;
    padding: var(--space-2);
    border-radius: var(--radius-menu);
    background: var(--p-surf-2);
    border: 1px solid var(--p-line);
    box-shadow: var(--p-shadow-menu);
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .menu-item {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: none;
    background: transparent;
    color: var(--p-ink);
    font-size: 14px;
    text-align: left;
    cursor: pointer;
    min-height: var(--target-min);
  }

  .menu-item:hover {
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
  }

  .menu-item:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: -2px;
  }

  .menu-item.destructive {
    color: var(--sem-critical);
  }

  .menu-item-label {
    flex: 1;
    min-width: 0;
  }

  .menu-item-shortcut {
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px;
    letter-spacing: 0.02em;
  }
</style>
