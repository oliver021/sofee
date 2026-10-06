<!--
  ux-foundations.md §3, in full — the DOM wiring around packages/core's ScrollController — plus
  §10's "virtualise above 100 messages, preserving scroll anchoring" around
  packages/core's computeVirtualWindow. All of the interesting decisions in both live in those
  framework-free modules; this component's only job is translating real browser events into
  calls on them and applying what they return.

  `controller` is created and owned by the caller (one per open thread, so §3.5's per-thread
  memory is just "keep the controller/thread pair alive") and passed in as a prop — this
  component only ever calls its public methods, it does not decide when a message was "sent"
  or what a message looks like, which is what keeps packages/ui free of domain state.

  The caller passes `items` and an `item` snippet rather than one opaque `children` snippet
  because virtualisation has to know where the item boundaries are; what an item *renders as*
  is still entirely the caller's business.
-->
<script lang="ts" generics="T extends { id: string }">
  import { tick, type Snippet } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import type { ScrollController, ScrollInstruction, ScrollMetrics } from '@sofee/core';
  import type { Translate } from '@sofee/core';
  import { computeVirtualWindow } from '@sofee/core';
  import JumpToLatestButton from './JumpToLatestButton.svelte';
  import { scrollbars } from '../actions/scrollbars.js';

  interface Props {
    controller: ScrollController;
    t: Translate;
    items: readonly T[];
    item: Snippet<[T, number]>;
    /** Rendered instead of the item list when `items` is empty. */
    empty?: Snippet;
  }

  let { controller, t, items, item, empty }: Props = $props();

  let viewportEl: HTMLDivElement | null = $state(null);
  let contentEl: HTMLDivElement | null = $state(null);

  // Svelte's `$store` auto-subscription works on anything shaped like a store (subscribe ->
  // unsubscribe) regardless of how it was constructed — ScrollController exposes exactly that
  // contract without this package (or packages/core) importing Svelte anywhere.
  let snapshot = $derived($controller);

  const SCROLL_RELEVANT_KEYS = new Set([
    'ArrowUp',
    'ArrowDown',
    'PageUp',
    'PageDown',
    'Home',
    'End',
    ' ',
  ]);

  // ─── Virtualisation (§10) ───────────────────────────────────────────────────────────────

  /** Measured heights, keyed by item id so they survive an item moving within the window. */
  const measuredHeights = new SvelteMap<string, number>();

  /** Viewport geometry, tracked only to pick the window — see `onViewportScroll`. */
  let scrollTop = $state(0);
  let viewportHeight = $state(0);

  /** Set for one render pass when `prepareForSend` needs an item the window has scrolled past. */
  let renderThroughEnd = $state(false);

  let heightList = $derived(items.map((entry) => measuredHeights.get(entry.id) ?? Number.NaN));

  let window_ = $derived.by(() => {
    const computed = computeVirtualWindow({ heights: heightList, scrollTop, viewportHeight });
    if (!renderThroughEnd || !computed.virtualised) return computed;
    // Rendering through the tail means there is nothing left below to reserve space for.
    return { ...computed, endIndex: items.length, padBottomPx: 0 };
  });

  let rendered = $derived(items.slice(window_.startIndex, window_.endIndex));

  /**
   * §3.1 is emphatic that pin state must come from *intent*, never from a scroll event. This
   * handler exists only to keep the window geometry current and deliberately never touches
   * `controller` — reading scrollTop to decide what to render is a different question from
   * inferring that a human meant to scroll.
   */
  function onViewportScroll(): void {
    if (!viewportEl) return;
    scrollTop = viewportEl.scrollTop;
  }

  function metricsOf(el: HTMLElement): ScrollMetrics {
    return {
      scrollTop: el.scrollTop,
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
    };
  }

  function applyInstruction(instruction: ScrollInstruction): void {
    if (!viewportEl || instruction.type === 'none') return;
    if (instruction.type === 'scroll-to-offset') {
      viewportEl.scrollTop = instruction.scrollTop;
      scrollTop = viewportEl.scrollTop;
      return;
    }
    // scroll-to-bottom
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (instruction.smooth && !reducedMotion) {
      viewportEl.scrollTo({ top: viewportEl.scrollHeight, behavior: 'smooth' });
    } else {
      // §3.3: never a smooth scroll during streaming — smooth scrolls queue and fight each other.
      viewportEl.scrollTop = viewportEl.scrollHeight;
    }
    scrollTop = viewportEl.scrollTop;
  }

  function onUserScrollIntent(): void {
    if (!viewportEl) return;
    controller.notifyUserScrollIntent(metricsOf(viewportEl));
  }

  function onScrollKeydown(event: KeyboardEvent): void {
    if (SCROLL_RELEVANT_KEYS.has(event.key)) onUserScrollIntent();
  }

  function onJumpToLatest(): void {
    applyInstruction(controller.jumpToLatest());
  }

  function elementFor(messageId: string): HTMLElement | null {
    return contentEl?.querySelector<HTMLElement>(`[data-message-id="${messageId}"]`) ?? null;
  }

  /** Imperative API for the caller — see the component doc comment above. */
  export async function prepareForSend(messageId: string): Promise<void> {
    if (!viewportEl || !contentEl) return;
    let target = elementFor(messageId);
    if (!target) {
      // Sending from far up a long thread: the new message is below the current window, so
      // render through the tail for one pass to get a real offset to hold onto.
      renderThroughEnd = true;
      await tick();
      target = elementFor(messageId);
    }
    if (target) {
      applyInstruction(
        controller.prepareForSend({
          messageTopOffset: target.offsetTop,
          viewportHeight: viewportEl.clientHeight,
        }),
      );
    }
    if (renderThroughEnd) {
      // Safe to drop: the scroll above put the viewport at the tail, so the window now
      // covers this message on its own.
      renderThroughEnd = false;
      await tick();
    }
  }

  export function notifyMessageArrived(): void {
    controller.notifyMessageArrived();
  }

  /** §3.5 — captures enough to restore reading position later even if message heights have
   * changed by then (a locale switch, a resize, more content loading in). */
  export function captureScrollMemory(): { scrollTop: number; topMostMessageId: string | null } {
    if (!viewportEl || !contentEl) return { scrollTop: 0, topMostMessageId: null };
    const currentScrollTop = viewportEl.scrollTop;
    const messageEls = Array.from(contentEl.querySelectorAll<HTMLElement>('[data-message-id]'));
    const topMost = messageEls.find((el) => el.offsetTop + el.offsetHeight > currentScrollTop);
    return { scrollTop: currentScrollTop, topMostMessageId: topMost?.dataset['messageId'] ?? null };
  }

  /** §3.5 — "restore by message id when heights have changed": re-measures the remembered
   * message's *current* offset rather than trusting the raw pixel value from last time, falling
   * back to that raw value only if the message is gone — which, in a virtualised thread, also
   * covers "scrolled out of the window", where the raw offset is the better guess anyway. */
  export function restoreScrollMemory(
    entry: { scrollTop: number; topMostMessageId: string | null } | undefined,
  ): void {
    if (!viewportEl || !contentEl || !entry) return;
    if (entry.topMostMessageId) {
      const el = elementFor(entry.topMostMessageId);
      if (el) {
        viewportEl.scrollTop = el.offsetTop;
        scrollTop = viewportEl.scrollTop;
        return;
      }
    }
    viewportEl.scrollTop = entry.scrollTop;
    scrollTop = viewportEl.scrollTop;
  }

  export function notifyStreamSettled(): void {
    controller.notifyStreamSettled();
  }

  $effect(() => {
    if (!contentEl || !viewportEl) return;
    // A ResizeObserver batches and delivers once before paint even if the content resized
    // several times in between — "one observer callback per frame", satisfied by the platform
    // itself rather than by throttling here (§3.3).
    const observer = new ResizeObserver(() => {
      if (!viewportEl) return;
      applyInstruction(controller.notifyContentResize(metricsOf(viewportEl)));
    });
    observer.observe(contentEl);
    return () => observer.disconnect();
  });

  $effect(() => {
    const el = viewportEl;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      viewportHeight = el.clientHeight;
    });
    observer.observe(el);
    viewportHeight = el.clientHeight;
    return () => observer.disconnect();
  });

  /** Measures every rendered item so the window can reason about the ones it has dropped. */
  $effect(() => {
    if (!contentEl) return;
    void rendered;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const el = entry.target as HTMLElement;
        const id = el.dataset['virtualId'];
        if (id === undefined) continue;
        const height = el.offsetHeight;
        // Guarded on inequality: without this, writing a height would re-derive the window,
        // re-run this effect and deliver the same measurement forever.
        if (height > 0 && measuredHeights.get(id) !== height) measuredHeights.set(id, height);
      }
    });
    for (const el of contentEl.querySelectorAll<HTMLElement>('[data-virtual-id]'))
      observer.observe(el);
    return () => observer.disconnect();
  });

  /**
   * Replacing an estimated height with a real one changes how much padding sits above the
   * window, which would slide the visible content out from under the reader. When the window
   * has not moved but its top padding has, the difference is exactly that correction, so
   * absorb it into scrollTop and nothing appears to move.
   *
   * Only while free: when pinned the controller owns scrollTop outright (§3.3) and a second
   * writer would be the scroll fight §3 exists to prevent.
   */
  let lastStartIndex = -1;
  let lastPadTopPx = 0;
  $effect(() => {
    const current = window_;
    const el = viewportEl;
    if (
      el &&
      current.virtualised &&
      !snapshot.pinned &&
      current.startIndex === lastStartIndex &&
      current.padTopPx !== lastPadTopPx
    ) {
      el.scrollTop += current.padTopPx - lastPadTopPx;
      scrollTop = el.scrollTop;
    }
    lastStartIndex = current.startIndex;
    lastPadTopPx = current.padTopPx;
  });

  $effect(() => {
    function onVisibilityChange(): void {
      applyInstruction(controller.setHidden(document.visibilityState === 'hidden'));
    }
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  });
</script>

<div class="message-list-root">
  <!-- tabindex="-1": not a Tab stop (ux-foundations.md §6 reaches this region via Alt+Up/Down
       onto a message, not a generic "tab into the transcript" step) — but still a valid target
       for that programmatic .focus(), after which native arrow-key scrolling of this ancestor
       works with no extra wiring, since onScrollKeydown below never calls preventDefault(). -->
  <!--
    Deliberate: ux-foundations.md §3.1 asks specifically for wheel/touchmove/keydown *intent*
    listeners on the scrollable region itself ("Detect intent, not position"). role="region" is
    the semantically correct landmark role for this container; there is no ARIA role for
    "scrollable content area" the linter would accept instead, and reaching for role="application"
    to silence this would cost real screen-reader navigation of the messages inside it for no
    actual benefit.
  -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="viewport"
    role="region"
    aria-label={t('thread.conversationLabel')}
    tabindex="-1"
    bind:this={viewportEl}
    use:scrollbars
    onwheel={onUserScrollIntent}
    ontouchmove={onUserScrollIntent}
    onkeydown={onScrollKeydown}
    onscroll={onViewportScroll}
  >
    <div class="content" bind:this={contentEl}>
      {#if items.length === 0}
        {#if empty}{@render empty()}{/if}
      {:else}
        <!-- §10: the two spacers stand in for the items outside the window, so the scrollable
             height stays exactly what it would be with the whole thread rendered. -->
        {#if window_.padTopPx > 0}
          <div class="virtual-pad" style:block-size="{window_.padTopPx}px"></div>
        {/if}
        {#each rendered as entry, offset (entry.id)}
          <div class="virtual-item" data-virtual-id={entry.id}>
            {@render item(entry, window_.startIndex + offset)}
          </div>
        {/each}
        {#if window_.padBottomPx > 0}
          <div class="virtual-pad" style:block-size="{window_.padBottomPx}px"></div>
        {/if}
      {/if}
      <!-- §3.2: the spacer that lets a message near the end of a short thread still reach the
           top of the viewport; its reserved size is entirely driven by the controller. -->
      <div class="thread-tail" style:min-block-size="{snapshot.tailReservePx}px"></div>
    </div>
  </div>

  {#if snapshot.showJumpToLatest}
    <div class="jump-anchor">
      <JumpToLatestButton count={snapshot.unreadCount} {t} onClick={onJumpToLatest} />
    </div>
  {/if}
</div>

<style>
  .message-list-root {
    position: relative;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    isolation: isolate;
  }

  .viewport {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    /* §3.3: browser scroll anchoring and manual pinning both try to own scrollTop — let ours
       win. */
    overflow-anchor: none;
  }

  .viewport:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: -2px;
  }

  .content {
    display: flex;
    flex-direction: column;
    width: min(100%, var(--canvas-max-width));
    margin-inline: auto;
    padding-inline: var(--space-4);
  }

  /* Carries no spacing of its own: messages space themselves with their own padding, so
     wrapping each one leaves the rendered result byte-for-byte what it was before §10. */
  .virtual-item {
    display: flex;
    flex-direction: column;
  }

  .virtual-pad {
    flex: none;
  }

  .jump-anchor {
    /* Absolutely positioned over the viewport's own bottom edge, not a normal flex row after
       it — otherwise the viewport's box (and so its scrollHeight/clientHeight maths) would
       resize by a few pixels each time this toggles, which is exactly the kind of layout shift
       §3 exists to avoid. */
    position: absolute;
    left: 0;
    right: 0;
    bottom: var(--space-4);
    z-index: 2;
    display: flex;
    justify-content: center;
    pointer-events: none;
  }

  .jump-anchor :global(.jump-to-latest) {
    pointer-events: auto;
  }
</style>
