<!--
  design-system.md §6 "Icon buttons" — the one control every toolbar, panel header, message
  toolbar and menu trigger is built from. 44x44 minimum target regardless of the 20px icon;
  rest/hover/active/focus states and the badge all come from tokens, never a literal colour.
  Both `label` (aria-label) and `tooltip` are required and translated — "Both.", per the spec.
-->
<script lang="ts">
  import type { Component } from 'svelte';
  import Badge from './Badge.svelte';

  interface Props {
    icon: Component<{ size?: number }>;
    label: string;
    tooltip?: string;
    badge?: number;
    active?: boolean;
    disabled?: boolean;
    tabindex?: number;
    tooltipSide?: 'top' | 'bottom' | 'left' | 'right';
    ariaHasPopup?: 'menu' | 'dialog' | 'listbox' | 'true';
    ariaExpanded?: boolean;
    ariaPressed?: boolean;
    /** A ref callback rather than `bind:` — a roving-tabindex host (IconToolbar) collects these into an
     * array it indexes by position, and binding a two-way prop to a not-yet-existing array slot
     * (`buttonEls[i]` before that index has ever been assigned) is a Svelte error, not just an
     * `undefined` value. A plain callback sidesteps that entirely. */
    onElementReady?: (element: HTMLButtonElement | null) => void;
    onclick?: (event: MouseEvent) => void;
    onkeydown?: (event: KeyboardEvent) => void;
  }

  let {
    icon: Icon,
    label,
    tooltip = label,
    badge,
    active = false,
    disabled = false,
    tabindex = 0,
    tooltipSide = 'bottom',
    ariaHasPopup,
    ariaExpanded,
    ariaPressed,
    onElementReady,
    onclick,
    onkeydown,
  }: Props = $props();

  let buttonEl: HTMLButtonElement | null = $state(null);

  $effect(() => {
    onElementReady?.(buttonEl);
  });
</script>

<span class="host">
  <button
    bind:this={buttonEl}
    type="button"
    class="icon-button"
    class:active
    aria-label={label}
    aria-haspopup={ariaHasPopup}
    aria-expanded={ariaHasPopup ? ariaExpanded : undefined}
    aria-pressed={ariaPressed}
    {disabled}
    {tabindex}
    {onclick}
    {onkeydown}
  >
    <Icon size={20} />
    {#if badge !== undefined}
      <Badge count={badge} />
    {/if}
  </button>
  <span class="tooltip" data-side={tooltipSide} role="tooltip">{tooltip}</span>
</span>

<style>
  .host {
    position: relative;
    display: inline-flex;
  }

  .icon-button {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--target-min);
    height: var(--target-min);
    padding: 0;
    border-radius: var(--radius-icon-btn);
    border: 1px solid transparent;
    background: transparent;
    color: var(--p-mut);
    cursor: pointer;
    transition:
      color var(--motion-menu-duration) var(--motion-menu-easing),
      background-color var(--motion-menu-duration) var(--motion-menu-easing),
      border-color var(--motion-menu-duration) var(--motion-menu-easing);
  }

  .icon-button:hover:not(:disabled) {
    color: var(--p-ink);
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
    border-color: var(--p-line);
  }

  .icon-button.active {
    color: var(--p-acc);
    background: color-mix(in oklab, var(--p-acc) 12%, transparent);
    border-color: color-mix(in oklab, var(--p-acc) 40%, transparent);
  }

  .icon-button:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .icon-button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .tooltip {
    pointer-events: none;
    position: absolute;
    z-index: 3;
    white-space: nowrap;
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-menu);
    background: var(--p-surf-2);
    color: var(--p-ink);
    font-size: 12px;
    border: 1px solid var(--p-line);
    box-shadow: var(--p-shadow-menu);
    opacity: 0;
    transform: scale(0.96);
    transition:
      opacity var(--motion-menu-duration) var(--motion-menu-easing),
      transform var(--motion-menu-duration) var(--motion-menu-easing);
  }

  /* Keyboard focus only (:focus-visible), not :focus-within: a mouse click or a focus restore
     after a menu/dialog closes leaves the button focused, which kept the tooltip stuck open. */
  .host:hover .tooltip,
  .host:has(.icon-button:focus-visible) .tooltip {
    opacity: 1;
    transform: scale(1);
  }

  /* A trigger that has opened its menu/popup hides its own tooltip while that stays open. */
  .host:has(.icon-button[aria-expanded='true']) .tooltip {
    opacity: 0;
    transform: scale(0.96);
  }

  .tooltip[data-side='right'] {
    left: calc(100% + var(--space-2));
    top: 50%;
    transform-origin: left center;
    translate: 0 -50%;
  }
  .tooltip[data-side='left'] {
    right: calc(100% + var(--space-2));
    top: 50%;
    transform-origin: right center;
    translate: 0 -50%;
  }
  .tooltip[data-side='top'] {
    bottom: calc(100% + var(--space-2));
    left: 50%;
    transform-origin: center bottom;
    translate: -50% 0;
  }
  .tooltip[data-side='bottom'] {
    top: calc(100% + var(--space-2));
    left: 50%;
    transform-origin: center top;
    translate: -50% 0;
  }

  /* prefers-reduced-motion is handled once, centrally, by collapsing --motion-*-duration to
     ~1ms (see packages/tokens/src/css-base.ts) rather than overriding transform/translate here,
     which would otherwise fight the positional `translate` used above for centering. */
</style>
