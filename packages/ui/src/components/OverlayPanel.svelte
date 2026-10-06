<!--
  ux-foundations.md §2.4 — "the load-bearing decision of the whole layout." The context
  overlay: `position: fixed` so it can never resize or reflow the canvas underneath it,
  vertically centred against the right edge, and sized by its content rather than stretched
  floor to ceiling. role="dialog", focus trapped inside while open and returned to the trigger
  on close; Esc and a click outside both close it. On a narrow window it becomes a full-width
  bottom sheet (handled in CSS, no separate component).

  The header's own list buttons use DropdownPanel instead — see §2.4's table for why the two
  shapes differ.
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
  let headingId = `panel-heading-${Math.random().toString(36).slice(2, 8)}`;

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
    if (!open) return;
    queueMicrotask(() => {
      const focusable = focusableElements();
      (focusable[0] ?? panelEl)?.focus();
    });
    document.addEventListener('pointerdown', onDocumentPointerDown);
    return () => document.removeEventListener('pointerdown', onDocumentPointerDown);
  });
</script>

{#if open}
  <div
    bind:this={panelEl}
    class="panel"
    role="dialog"
    aria-modal="true"
    aria-labelledby={headingId}
    tabindex="-1"
    onkeydown={onKeydown}
  >
    <div class="panel-header">
      <h2 id={headingId}>{titleText}</h2>
      <IconButton icon={IconClose} label={closeLabel} tooltip={closeLabel} onclick={close} />
    </div>
    <div class="panel-body" use:scrollbars={{ autoHide: 'leave' }}>
      {@render children()}
    </div>
  </div>
{/if}

<style>
  .panel {
    position: fixed;
    /* Centred vertically rather than stretched: `inset-block: 0` plus `margin-block: auto`
       on a fit-content height, which centres without a transform — leaving the entry
       animation's own `translate` free to do its job. */
    inset-block: 0;
    margin-block: auto;
    block-size: fit-content;
    max-block-size: calc(100dvh - var(--space-7));
    /* Insets by the gutter so the floating context cluster stays visible beside it (§2.2). */
    right: var(--toolbar-gutter);
    z-index: 15;
    width: min(360px, 100vw);
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-panel);
    background: var(--p-surf);
    border: 1px solid var(--p-line);
    box-shadow: var(--p-shadow-panel);
    animation: panel-slide-in var(--motion-panel-duration) var(--motion-panel-easing);
  }

  @keyframes panel-slide-in {
    from {
      opacity: 0;
      translate: 0 -4px;
    }
    to {
      opacity: 1;
      translate: 0 0;
    }
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    padding: var(--space-4);
    border-bottom: 1px solid var(--p-line);
  }

  .panel-header h2 {
    margin: 0;
    font-family: var(--p-display);
    font-size: 16px;
    font-weight: 600;
    color: var(--p-ink);
  }

  .panel-body {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-4);
  }

  @media (max-width: 900px) {
    .panel {
      /* Bottom sheet: drop the vertical centring rather than fight it. */
      inset-block: auto 0;
      margin-block: 0;
      left: 0;
      right: 0;
      width: 100%;
      max-block-size: 80vh;
      border-radius: var(--radius-panel) var(--radius-panel) 0 0;
    }

    @keyframes panel-slide-in {
      from {
        opacity: 0;
        translate: 0 16px;
      }
      to {
        opacity: 1;
        translate: 0 0;
      }
    }
  }
</style>
