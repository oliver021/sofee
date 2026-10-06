/**
 * The scroll controller for the conversation view — ux-foundations.md §3 in
 * full, as one framework-free, DOM-free module. It is driven entirely by
 * metrics and intent notifications the host (a Svelte component wiring up
 * real `wheel`/`touchmove`/`keydown`/`ResizeObserver`/`visibilitychange`
 * listeners) hands in, and it hands back small instructions for the host to
 * apply. No method here ever takes a raw `scroll` event — that is §3.1's
 * central warning ("detect intent, not position"), enforced by simply not
 * exposing a method that could be wired to one.
 *
 * ## The pin state machine (§3.1)
 * `pinned` / `free`, starting pinned. Only three things repin from free:
 * scrolling back within `UNPIN_THRESHOLD_PX` of the bottom, sending a
 * message, or tapping Jump to latest. While pinned, new content keeps the
 * bottom edge in view; while free, nothing scrolls on its own.
 *
 * ## Reading position on send (§3.2)
 * Sending does not jump to the bottom of the thread — it puts the user's
 * new message at the *top* of the viewport and holds the view there while
 * the reply streams into the space below, so the reader starts at the
 * first word instead of chasing the tail of a growing paragraph. That hold
 * has to end once the reply grows taller than the space that was visible
 * below the message, or the rest of the reply would render off-screen with
 * nothing scrolling to reveal it — at that point this controller hands off
 * to the ordinary pinned bottom-chase for the remainder of the stream. The
 * `.thread-tail` spacer this needs (min-block-size big enough that the
 * message can reach the top even in a short thread) is a real DOM element
 * the host renders; `tailReserveActive`/`tailReservePx` in the snapshot are
 * what the host binds that element's size to, so it can reclaim the space
 * the moment this controller decides the hold is over ("the spacer
 * collapses once the reply is long enough to fill it").
 *
 * ## While streaming (§3.3)
 * The host observes the message list with a `ResizeObserver` (content
 * growth, not token events) and calls `notifyContentResize` once per frame.
 * This controller never asks for a smooth scroll during streaming — smooth
 * scrolls queue and fight each other — and pauses entirely while the tab is
 * hidden, catching up once when it becomes visible again.
 */

export type PinState = 'pinned' | 'free';

export interface ScrollMetrics {
  readonly scrollTop: number;
  readonly scrollHeight: number;
  readonly clientHeight: number;
}

export type ScrollInstruction =
  /** Do nothing. */
  | { readonly type: 'none' }
  /** Set `scrollTop = scrollHeight` directly. `smooth` is only ever true for an explicit
   * Jump-to-latest tap — never during streaming (§3.3, §3.4). */
  | { readonly type: 'scroll-to-bottom'; readonly smooth: boolean }
  /** Set `scrollTop` to this exact value — used to land the just-sent message at the top (§3.2)
   * and to restore per-thread scroll memory (§3.5). */
  | { readonly type: 'scroll-to-offset'; readonly scrollTop: number };

export interface ScrollControllerSnapshot {
  readonly pinned: boolean;
  /** Whether the `.thread-tail` spacer should currently be reserving space (§3.2). */
  readonly tailReserveActive: boolean;
  readonly tailReservePx: number;
  /** §3.4: only true while free and more than one viewport away from the bottom. */
  readonly showJumpToLatest: boolean;
  /** Messages that arrived while free — the badge count on Jump to latest (§3.4). */
  readonly unreadCount: number;
}

/** §3.1's own example, unchanged: distance still to scroll to reach the bottom. */
export function distanceFromBottom(metrics: ScrollMetrics): number {
  return metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight;
}

export const UNPIN_THRESHOLD_PX = 48;
const JUMP_TO_LATEST_VIEWPORTS = 1;

type Mode = 'idle' | 'holding' | 'streaming';

export interface ScrollControllerOptions {
  /** Defaults to `UNPIN_THRESHOLD_PX` (48, per §3.1). Overridable for tests/tuning. */
  unpinThresholdPx?: number;
}

export class ScrollController {
  readonly #unpinThresholdPx: number;
  #pinned = true;
  #mode: Mode = 'idle';
  #holdBoundary = 0;
  #tailReservePx = 0;
  #unreadCount = 0;
  #hidden = false;
  #lastMetrics: ScrollMetrics | null = null;
  readonly #listeners = new Set<(snapshot: ScrollControllerSnapshot) => void>();

  constructor(options: ScrollControllerOptions = {}) {
    this.#unpinThresholdPx = options.unpinThresholdPx ?? UNPIN_THRESHOLD_PX;
  }

  get snapshot(): ScrollControllerSnapshot {
    const last = this.#lastMetrics;
    const showJumpToLatest =
      !this.#pinned &&
      last !== null &&
      distanceFromBottom(last) > last.clientHeight * JUMP_TO_LATEST_VIEWPORTS;
    return {
      pinned: this.#pinned,
      tailReserveActive: this.#mode === 'holding',
      tailReservePx: this.#tailReservePx,
      showJumpToLatest,
      unreadCount: this.#unreadCount,
    };
  }

  /** Svelte-store-shaped on purpose (calls back immediately, returns an unsubscribe) so a
   * component can do `const unsubscribe = controller.subscribe(s => state = s)` — or even
   * `$controller` — without this package importing Svelte (10. "packages/core must not import
   * Svelte"). */
  subscribe(run: (snapshot: ScrollControllerSnapshot) => void): () => void {
    this.#listeners.add(run);
    run(this.snapshot);
    return () => this.#listeners.delete(run);
  }

  #emit(): void {
    const snapshot = this.snapshot;
    for (const listener of this.#listeners) listener(snapshot);
  }

  /**
   * Call this from `wheel`, `touchmove`, and scroll-relevant `keydown` handlers — never from a
   * `scroll` listener (§3.1). The browser has already moved the viewport by the time this fires,
   * so there is nothing to instruct; this only updates pin state.
   */
  notifyUserScrollIntent(metrics: ScrollMetrics): void {
    this.#lastMetrics = metrics;
    const wasHolding = this.#mode === 'holding';
    if (wasHolding) {
      // The user has taken control mid-hold; stop reserving space immediately rather than
      // fighting them on the next resize tick.
      this.#mode = 'streaming';
      this.#tailReservePx = 0;
    }
    const nowPinned = distanceFromBottom(metrics) <= this.#unpinThresholdPx;
    const changed = nowPinned !== this.#pinned;
    this.#pinned = nowPinned;
    if (nowPinned) this.#unreadCount = 0;
    if (changed || wasHolding) this.#emit();
  }

  /**
   * Call this from a `ResizeObserver` callback on the message list — once per frame, not once
   * per token (§3.3). Returns what the host should do about `scrollTop`.
   */
  notifyContentResize(metrics: ScrollMetrics): ScrollInstruction {
    this.#lastMetrics = metrics;
    if (this.#hidden) return { type: 'none' }; // §3.3 — paused while the tab is hidden.

    if (this.#mode === 'holding') {
      const contentBottom = metrics.scrollHeight - this.#tailReservePx;
      if (contentBottom <= this.#holdBoundary) return { type: 'none' };
      // The reply just grew past the space that was visible below the pinned message (§3.2:
      // "the spacer collapses once the reply is long enough to fill it") — hand off to the
      // ordinary pinned bottom-chase for the rest of the stream.
      this.#mode = 'streaming';
      this.#tailReservePx = 0;
      this.#emit();
      return { type: 'scroll-to-bottom', smooth: false };
    }

    if (this.#pinned) return { type: 'scroll-to-bottom', smooth: false };
    return { type: 'none' };
  }

  /**
   * Call once per new message appended to the thread — not per resize tick — so the
   * Jump-to-latest badge (§3.4) counts messages, not animation frames.
   */
  notifyMessageArrived(): void {
    if (this.#pinned) return;
    this.#unreadCount += 1;
    this.#emit();
  }

  /**
   * Call when the reply finishes (Response complete). If the hold from `prepareForSend` never
   * had to hand off (a short reply that fit entirely below the message), there is no more
   * growth coming, so reclaim the spacer now rather than leaving it reserved indefinitely.
   */
  notifyStreamSettled(): void {
    if (this.#mode === 'idle') return;
    this.#mode = 'idle';
    this.#tailReservePx = 0;
    this.#emit();
  }

  /**
   * §3.2. Called once, synchronously, when a message is sent. `messageTopOffset` is where that
   * message starts in the scrollable content (e.g. its `offsetTop`); `viewportHeight` is the
   * scroll container's `clientHeight`. Always re-pins (per the §3.1 state diagram: sending a
   * message is one of the three ways back to pinned).
   */
  prepareForSend(input: { messageTopOffset: number; viewportHeight: number }): ScrollInstruction {
    this.#mode = 'holding';
    this.#holdBoundary = input.messageTopOffset + input.viewportHeight;
    this.#tailReservePx = input.viewportHeight;
    this.#pinned = true;
    this.#unreadCount = 0;
    this.#emit();
    return { type: 'scroll-to-offset', scrollTop: input.messageTopOffset };
  }

  /** §3.4. Smooth-scrolls (the one time this controller ever asks for that) unless the host
   * suppresses it for `prefers-reduced-motion`, and re-pins. */
  jumpToLatest(): ScrollInstruction {
    this.#mode = 'idle';
    this.#tailReservePx = 0;
    this.#pinned = true;
    this.#unreadCount = 0;
    this.#emit();
    return { type: 'scroll-to-bottom', smooth: true };
  }

  /** §3.3: "Pause autoscroll while `document.visibilityState === 'hidden'`; catch up once on
   * `visibilitychange`." Call with `true`/`false` from that event. */
  setHidden(hidden: boolean): ScrollInstruction {
    const wasHidden = this.#hidden;
    this.#hidden = hidden;
    if (wasHidden && !hidden && this.#pinned && this.#mode !== 'holding') {
      return { type: 'scroll-to-bottom', smooth: false };
    }
    return { type: 'none' };
  }
}

/** §3.5 — "Store offset plus the id of the topmost visible message; restore by message id when
 * heights have changed." This store only holds the record; measuring the topmost visible
 * message and re-measuring it on restore is a DOM concern the host owns. In-memory only, keyed
 * by thread id — it is meant to survive switching between open threads in this session, not a
 * full page reload. */
export interface ScrollMemoryEntry {
  readonly scrollTop: number;
  readonly topMostMessageId: string | null;
}

export class ScrollMemoryStore {
  readonly #entries = new Map<string, ScrollMemoryEntry>();

  save(threadId: string, entry: ScrollMemoryEntry): void {
    this.#entries.set(threadId, entry);
  }

  restore(threadId: string): ScrollMemoryEntry | undefined {
    return this.#entries.get(threadId);
  }

  clear(threadId: string): void {
    this.#entries.delete(threadId);
  }
}
