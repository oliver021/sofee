<!--
  A large anchored dropdown for the header's Chats and Projects buttons.

  Deliberately not an OverlayPanel: those are edge-anchored sheets running the full height of
  the window, which is far more surface than a list of recent chats needs and reads as a mode
  you have entered rather than a menu you have opened. This is bigger than a standard menu —
  wide enough for a chat title, tall enough for a useful page of them — and bounded, so the
  canvas stays visible around it.

  Same dismissal contract as every other overlay in the app (ux-foundations.md §2.4): Esc
  closes, a click outside closes, focus moves in on open and returns to the trigger on close.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import IconButton from './IconButton.svelte';
  import { IconClose } from '@sofee/icons';
  import { scrollbars } from '../actions/scrollbars.js';

  interface Props {
    open: boolean;
    titleText: string;
    closeLabel: string;
    triggerEl: HTMLElement | null;
    onClose: () => void;
    children: Snippet;
  }

  let { open, titleText, closeLabel, triggerEl, onClose, children }: Props = $props();

  let panelEl: HTMLDivElement | null = $state(null);
  let anchorRect: DOMRect | null = $state(null);
  const headingId = `dropdown-heading-${Math.random().toString(36).slice(2, 8)}`;

  const PANEL_WIDTH = 400;
  const EDGE_MARGIN = 16;
  const GAP_BELOW_TRIGGER = 8;

  /** Kept inside the viewport rather than allowed to run off the right edge on a narrow window. */
  let position = $derived.by(() => {
    if (!anchorRect) return { left: EDGE_MARGIN, top: EDGE_MARGIN };
    const maxLeft = Math.max(EDGE_MARGIN, window.innerWidth - PANEL_WIDTH - EDGE_MARGIN);
    return {
      left: Math.min(Math.max(EDGE_MARGIN, anchorRect.left), maxLeft),
      top: anchorRect.bottom + GAP_BELOW_TRIGGER,
    };
  });

  function focusableElements(): HTMLElement[] {
    if (!panelEl) return [];
    return Array.from(
      panelEl.querySelectorAll<HTMLElement>(
        'a[href], button:not(:disabled), [tabindex]:not([tabindex="-1"]), input:not(:disabled), select, textarea',
      ),
    );
  }

  function close(): void {
    onClose();
    triggerEl?.focus();
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = focusableElements();
    if (focusable.length === 0) return;
    const first = focusable[0] as HTMLElement;
    const last = focusable[focusable.length - 1] as HTMLElement;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function onDocumentPointerDown(event: PointerEvent): void {
    const target = event.target as Node;
    if (panelEl?.contains(target) || triggerEl?.contains(target)) return;
    close();
  }

  $effect(() => {
    if (!open || !triggerEl) return;
    function measure(): void {
      anchorRect = triggerEl?.getBoundingClientRect() ?? null;
    }
    measure();
    queueMicrotask(() => {
      const focusable = focusableElements();
      (focusable[0] ?? panelEl)?.focus();
    });
    document.addEventListener('pointerdown', onDocumentPointerDown);
    window.addEventListener('resize', measure);
    return () => {
      document.removeEventListener('pointerdown', onDocumentPointerDown);
      window.removeEventListener('resize', measure);
    };
  });
</script>

{#if open}
  <div
    bind:this={panelEl}
    class="dropdown-panel"
    role="dialog"
    aria-modal="true"
    aria-labelledby={headingId}
    tabindex="-1"
    style:left="{position.left}px"
    style:top="{position.top}px"
    style:width="{PANEL_WIDTH}px"
    onkeydown={onKeydown}
  >
    <div class="dropdown-header">
      <h2 id={headingId}>{titleText}</h2>
      <IconButton icon={IconClose} label={closeLabel} tooltip={closeLabel} onclick={close} />
    </div>
    <div class="dropdown-body" use:scrollbars={{ autoHide: 'leave' }}>
      {@render children()}
    </div>
  </div>
{/if}

<style>
  .dropdown-panel {
    position: fixed;
    z-index: 15;
    display: flex;
    flex-direction: column;
    /* Bounded on purpose: never floor to ceiling, and never taller than the content needs. */
    max-block-size: min(56vh, 520px);
    border-radius: var(--radius-panel);
    border: 1px solid var(--p-line);
    background: color-mix(in oklab, var(--p-surf) 92%, transparent);
    backdrop-filter: blur(16px);
    box-shadow: var(--p-shadow-panel);
    overflow: hidden;
    animation: dropdown-in var(--motion-menu-duration) var(--motion-panel-easing);
  }

  @keyframes dropdown-in {
    from {
      opacity: 0;
      translate: 0 -6px;
    }
    to {
      opacity: 1;
      translate: 0 0;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .dropdown-panel {
      animation: none;
    }
  }

  .dropdown-header {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-3) var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--p-line);
  }

  .dropdown-header h2 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
  }

  .dropdown-body {
    flex: 1;
    min-block-size: 0;
    overflow-y: auto;
    padding: var(--space-2);
  }

  /* A narrow window has no room for an anchored panel: fall back to a bottom sheet, still
     bounded rather than full height. */
  @media (max-width: 560px) {
    .dropdown-panel {
      left: var(--space-2) !important;
      right: var(--space-2);
      top: auto !important;
      bottom: var(--space-2);
      width: auto !important;
      max-block-size: 60vh;
    }
  }
</style>
