/**
 * ux-foundations.md §10 — "Virtualise above 100 messages, preserving scroll anchoring."
 *
 * Pure geometry, no DOM. Given the height of every item in the thread and where the
 * viewport currently sits, work out which contiguous slice to render and how much
 * empty space to leave above and below it, so that the scrollable height — and
 * therefore every offset ScrollController reasons about in §3 — stays exactly what
 * it would have been with the whole thread in the DOM. That invariant is the reason
 * this returns padding in pixels rather than just an index range: get it wrong and
 * pinning, the send-time hold and jump-to-latest all quietly drift.
 *
 * Below `threshold` items nothing is virtualised at all. The common case — a thread
 * you can read in one sitting — then takes the plain, zero-risk path, and the
 * windowing code only has to be right about long threads.
 */

/** Item count below which the whole thread renders (§10: "virtualise above 100 messages"). */
export const VIRTUALISE_THRESHOLD = 100;

/**
 * Extra pixels rendered beyond each edge of the viewport. Generous on purpose: the
 * cost of an offscreen message is a few DOM nodes, the cost of running out of them
 * mid-flick is a blank band, which is far more noticeable.
 */
export const DEFAULT_OVERSCAN_PX = 800;

/** Height assumed for an item that has not been measured yet. */
export const ESTIMATED_ITEM_HEIGHT_PX = 140;

export interface VirtualWindowInput {
  /** Height of each item, in order. A non-finite or negative entry is treated as unmeasured. */
  readonly heights: readonly number[];
  readonly scrollTop: number;
  readonly viewportHeight: number;
  readonly overscanPx?: number;
  readonly threshold?: number;
  /** Height assumed for unmeasured items. */
  readonly estimatedItemHeightPx?: number;
}

export interface VirtualWindow {
  readonly startIndex: number;
  /** Exclusive, so `items.slice(startIndex, endIndex)` is the slice to render. */
  readonly endIndex: number;
  readonly padTopPx: number;
  readonly padBottomPx: number;
  /** False when the whole thread is rendered, which is also the `heights.length === 0` case. */
  readonly virtualised: boolean;
}

function renderEverything(count: number): VirtualWindow {
  return { startIndex: 0, endIndex: count, padTopPx: 0, padBottomPx: 0, virtualised: false };
}

export function computeVirtualWindow(input: VirtualWindowInput): VirtualWindow {
  const { heights, scrollTop, viewportHeight } = input;
  const overscanPx = Math.max(0, input.overscanPx ?? DEFAULT_OVERSCAN_PX);
  const threshold = input.threshold ?? VIRTUALISE_THRESHOLD;
  const estimate = input.estimatedItemHeightPx ?? ESTIMATED_ITEM_HEIGHT_PX;
  const count = heights.length;

  if (count === 0 || count <= threshold) return renderEverything(count);

  // offsets[i] is the distance from the top of the list to the top of item i;
  // offsets[count] is the full scrollable height of the list.
  const offsets = new Array<number>(count + 1);
  offsets[0] = 0;
  for (let i = 0; i < count; i += 1) {
    const raw = heights[i];
    const height = typeof raw === 'number' && Number.isFinite(raw) && raw >= 0 ? raw : estimate;
    offsets[i + 1] = (offsets[i] ?? 0) + height;
  }
  const offsetAt = (i: number): number => offsets[i] ?? 0;
  const totalPx = offsetAt(count);

  const topBoundary = scrollTop - overscanPx;
  const bottomBoundary = scrollTop + viewportHeight + overscanPx;

  // First item whose bottom edge is still below the top boundary — i.e. the first one
  // with any chance of being visible. Never past the last item, so a scrollTop beyond
  // the end of the list still renders something rather than an empty window.
  let startIndex = 0;
  while (startIndex < count - 1 && offsetAt(startIndex + 1) <= topBoundary) startIndex += 1;

  // First item that starts at or after the bottom boundary. At least one item is always
  // rendered, which keeps `endIndex > startIndex` true for every input.
  let endIndex = startIndex + 1;
  while (endIndex < count && offsetAt(endIndex) < bottomBoundary) endIndex += 1;

  return {
    startIndex,
    endIndex,
    padTopPx: offsetAt(startIndex),
    padBottomPx: totalPx - offsetAt(endIndex),
    virtualised: true,
  };
}
