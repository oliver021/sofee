<!--
  The one implementation behind both of ux-foundations.md §2's icon clusters: the horizontal
  header floating at the top-left (§2.1) and the vertical context toolbar down the right edge
  (§2.2). Neither is a sidebar; both are icon-driven launchers.

  §6/§8: role="toolbar" with roving tabindex — one Tab stop for the whole cluster, arrow keys
  move within it along its own axis, Home/End jump to the ends.

  `children` (if given) renders as a separate floating element after the toolbar, outside its
  surface and unaffected by roving tabindex — this is where the right toolbar's context meter
  goes (§2.2: a context meter on its own surface directly below the buttons).
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import IconButton from './IconButton.svelte';
  import type { ToolbarItem } from '../types.js';

  interface Props {
    items: ToolbarItem[];
    label: string;
    orientation: 'horizontal' | 'vertical';
    /** Which edge tooltips open toward, so they never point off-screen. */
    tooltipSide?: 'top' | 'bottom' | 'left' | 'right';
    children?: Snippet;
  }

  let { items, label, orientation, tooltipSide, children }: Props = $props();

  let current = $state(0);
  let buttonEls: (HTMLButtonElement | null)[] = $state([]);

  let resolvedTooltipSide = $derived(
    tooltipSide ?? (orientation === 'horizontal' ? 'bottom' : 'left'),
  );

  let nextKey = $derived(orientation === 'horizontal' ? 'ArrowRight' : 'ArrowDown');
  let previousKey = $derived(orientation === 'horizontal' ? 'ArrowLeft' : 'ArrowUp');

  function focusIndex(index: number): void {
    current = index;
    buttonEls[index]?.focus();
  }

  function onkeydown(event: KeyboardEvent): void {
    if (items.length === 0) return;
    if (event.key === nextKey) {
      event.preventDefault();
      focusIndex((current + 1) % items.length);
    } else if (event.key === previousKey) {
      event.preventDefault();
      focusIndex((current - 1 + items.length) % items.length);
    } else if (event.key === 'Home') {
      event.preventDefault();
      focusIndex(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      focusIndex(items.length - 1);
    }
  }
</script>

<div class="dock" data-orientation={orientation}>
  <!-- tabindex="-1": the toolbar itself is never a tab stop — roving tabindex lives on the
       individual buttons below (exactly one has tabindex 0 at a time). -->
  <div
    class="toolbar"
    role="toolbar"
    aria-label={label}
    aria-orientation={orientation}
    tabindex="-1"
    {onkeydown}
  >
    {#each items as item, i (item.id)}
      <IconButton
        icon={item.icon}
        label={item.label}
        tooltip={item.tooltip ?? item.label}
        active={item.active}
        badge={item.badge}
        tabindex={i === current ? 0 : -1}
        tooltipSide={resolvedTooltipSide}
        ariaHasPopup={item.ariaHasPopup}
        ariaExpanded={item.ariaExpanded}
        onclick={() => {
          current = i;
          const el = buttonEls[i];
          if (el) item.onActivate(el);
        }}
        onElementReady={(el) => {
          buttonEls[i] = el;
        }}
      />
    {/each}
  </div>
  {#if children}
    <div class="dock-extra">
      {@render children()}
    </div>
  {/if}
</div>

<style>
  .dock {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .dock[data-orientation='vertical'] {
    flex-direction: column;
  }

  /* Elevation 3 (design-system.md §7): these float over the canvas rather than sitting in the
     layout, so they need their own surface for message text to pass under legibly. */
  .toolbar {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    padding: var(--space-1);
    border-radius: var(--radius-capsule);
    border: 1px solid var(--p-line);
    background: color-mix(in oklab, var(--p-surf) 82%, transparent);
    backdrop-filter: blur(12px);
  }

  .toolbar[aria-orientation='vertical'] {
    flex-direction: column;
  }

  .dock-extra {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-2);
    border-radius: var(--radius-capsule);
    border: 1px solid var(--p-line);
    background: color-mix(in oklab, var(--p-surf) 82%, transparent);
    backdrop-filter: blur(12px);
  }
</style>
