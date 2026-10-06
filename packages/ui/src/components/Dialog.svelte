<!--
  A centered modal dialog: Settings, Keyboard shortcuts, Command palette and the temporary-chat
  confirmation all share this shell. Same contract as OverlayPanel (role="dialog", focus
  trapped, Esc/click-outside closes, focus returns to the trigger) but centered with a dimming
  backdrop rather than edge-anchored — these are one-off actions/references, not the persistent
  browsing panels ux-foundations.md §2.4 is about, so there is no "never push the canvas"
  constraint to preserve here.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { scrollbars } from '../actions/scrollbars.js';

  interface Props {
    titleText: string;
    triggerEl?: HTMLElement | null;
    onClose: () => void;
    children: Snippet;
  }

  let { titleText, triggerEl = null, onClose, children }: Props = $props();

  let dialogEl: HTMLDivElement | null = $state(null);
  let headingId = `dialog-heading-${Math.random().toString(36).slice(2, 8)}`;

  function focusableElements(): HTMLElement[] {
    if (!dialogEl) return [];
    return Array.from(
      dialogEl.querySelectorAll<HTMLElement>(
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

  function onBackdropPointerDown(event: PointerEvent): void {
    if (event.target === event.currentTarget) close();
  }

  $effect(() => {
    queueMicrotask(() => {
      const focusable = focusableElements();
      (focusable[0] ?? dialogEl)?.focus();
    });
  });
</script>

<!-- role="presentation": purely a click-outside catcher, the actual dialog semantics live on
     the nested role="dialog" element below. -->
<div class="backdrop" role="presentation" onpointerdown={onBackdropPointerDown}>
  <div
    bind:this={dialogEl}
    class="dialog"
    use:scrollbars={{ autoHide: 'leave' }}
    role="dialog"
    aria-modal="true"
    aria-labelledby={headingId}
    tabindex="-1"
    onkeydown={onKeydown}
  >
    <h2 id={headingId}>{titleText}</h2>
    {@render children()}
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 30;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-5);
    background: color-mix(in oklab, var(--p-bg) 55%, transparent);
    animation: dialog-fade var(--motion-panel-duration) var(--motion-panel-easing);
  }

  .dialog {
    width: min(440px, 100%);
    max-height: min(600px, 85vh);
    overflow-y: auto;
    padding: var(--space-5);
    border-radius: var(--radius-panel);
    background: var(--p-surf);
    border: 1px solid var(--p-line);
    box-shadow: var(--p-shadow-panel);
  }

  .dialog h2 {
    margin: 0 0 var(--space-4);
    font-family: var(--p-display);
    font-size: 18px;
    color: var(--p-ink);
  }

  @keyframes dialog-fade {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }
</style>
