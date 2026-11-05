<!--
  A centered modal dialog: Settings, Keyboard shortcuts, Command palette and the temporary-chat
  confirmation all share this shell. Same contract as OverlayPanel (role="dialog", focus
  trapped, Esc/click-outside closes, focus returns to the trigger) but centered with a dimming
  backdrop rather than edge-anchored — these are one-off actions/references, not the persistent
  browsing panels ux-foundations.md §2.4 is about, so there is no "never push the canvas"
  constraint to preserve here.

  `size="lg"` is the two-pane Settings layout: a fixed-height shell whose own body scrolls
  instead of the whole dialog, plus a visible close button. The default `md` keeps every other
  dialog on the original 440px card.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';
  import { IconClose } from '@sofee/icons';
  import IconButton from './IconButton.svelte';
  import { scrollbars } from '../actions/scrollbars.js';

  interface Props {
    titleText: string;
    triggerEl?: HTMLElement | null;
    onClose: () => void;
    children: Snippet;
    /** `lg` is the 960×720 Settings shell; `md` is the original 440px card. */
    size?: 'md' | 'lg';
    /** Show an explicit close button in the header. Settings passes true so the large
     * surface has an always-visible way out. */
    showClose?: boolean;
    closeLabel?: string;
  }

  let {
    titleText,
    triggerEl = null,
    onClose,
    children,
    size = 'md',
    showClose = false,
    closeLabel = '',
  }: Props = $props();

  let dialogEl: HTMLDivElement | null = $state(null);
  let headingId = `dialog-heading-${Math.random().toString(36).slice(2, 8)}`;

  function focusableElements(): HTMLElement[] {
    if (!dialogEl) return [];
    const elements = Array.from(
      dialogEl.querySelectorAll<HTMLElement>(
        'a[href], button:not(:disabled), [tabindex]:not([tabindex="-1"]), input:not(:disabled), select, textarea',
      ),
    );
    // Settings renders every category as a `hidden` tabpanel. Those controls stay in the DOM,
    // so without this filter the trap's "last" element could be in an invisible panel and
    // forward Tab would escape the modal.
    return elements.filter((element) => element.getClientRects().length > 0);
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
      const preferred = dialogEl?.querySelector<HTMLElement>('[data-autofocus]');
      const focusable = focusableElements();
      (preferred ?? focusable[0] ?? dialogEl)?.focus();
    });
  });
</script>

<!-- role="presentation": purely a click-outside catcher, the actual dialog semantics live on
     the nested role="dialog" element below. -->
<div class="backdrop" role="presentation" onpointerdown={onBackdropPointerDown}>
  <div
    bind:this={dialogEl}
    class="dialog"
    class:lg={size === 'lg'}
    use:scrollbars={size === 'lg' ? undefined : { autoHide: 'leave' }}
    role="dialog"
    aria-modal="true"
    aria-labelledby={headingId}
    tabindex="-1"
    onkeydown={onKeydown}
  >
    <div class="dialog-header">
      <h2 id={headingId}>{titleText}</h2>
      {#if showClose}
        <IconButton icon={IconClose} label={closeLabel} tooltip={closeLabel} onclick={close} />
      {/if}
    </div>
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

  .dialog.lg {
    width: min(960px, 100%);
    height: min(720px, 86vh);
    max-height: none;
    padding: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .dialog-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-3);
    margin: 0 0 var(--space-4);
  }

  .dialog.lg .dialog-header {
    align-items: center;
    flex: none;
    margin: 0;
    padding: var(--space-3) var(--space-3) var(--space-3) var(--space-5);
    border-bottom: 1px solid var(--p-line);
  }

  .dialog h2 {
    margin: 0;
    font-family: var(--p-display);
    font-size: 18px;
    color: var(--p-ink);
  }

  @media (max-width: 560px) {
    .backdrop {
      padding: var(--space-2);
    }

    .dialog.lg {
      width: 100%;
      height: min(720px, 94vh);
    }
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
