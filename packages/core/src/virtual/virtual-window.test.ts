import { describe, expect, it } from 'vitest';
import {
  computeVirtualWindow,
  DEFAULT_OVERSCAN_PX,
  ESTIMATED_ITEM_HEIGHT_PX,
  VIRTUALISE_THRESHOLD,
  type VirtualWindow,
} from './virtual-window.js';

/** `count` items of `height` px each. */
function heights(count: number, height = 100): number[] {
  return Array.from({ length: count }, () => height);
}

/**
 * The invariant the whole module exists to protect (§3 + §10): whatever slice is
 * rendered, padding plus rendered heights must add up to the full list height, or
 * every scroll offset ScrollController computes drifts.
 */
function totalOf(window: VirtualWindow, all: readonly number[]): number {
  const rendered = all.slice(window.startIndex, window.endIndex).reduce((sum, h) => sum + h, 0);
  return window.padTopPx + rendered + window.padBottomPx;
}

describe('computeVirtualWindow', () => {
  describe('below the threshold', () => {
    it('renders an empty thread without virtualising', () => {
      const w = computeVirtualWindow({ heights: [], scrollTop: 0, viewportHeight: 800 });
      expect(w).toEqual({
        startIndex: 0,
        endIndex: 0,
        padTopPx: 0,
        padBottomPx: 0,
        virtualised: false,
      });
    });

    it('renders every item, with no padding, at exactly the threshold', () => {
      const all = heights(VIRTUALISE_THRESHOLD);
      const w = computeVirtualWindow({ heights: all, scrollTop: 5_000, viewportHeight: 800 });
      expect(w.virtualised).toBe(false);
      expect(w.startIndex).toBe(0);
      expect(w.endIndex).toBe(VIRTUALISE_THRESHOLD);
      expect(w.padTopPx).toBe(0);
      expect(w.padBottomPx).toBe(0);
    });

    it('starts virtualising one item past the threshold', () => {
      const all = heights(VIRTUALISE_THRESHOLD + 1);
      const w = computeVirtualWindow({ heights: all, scrollTop: 5_000, viewportHeight: 800 });
      expect(w.virtualised).toBe(true);
    });

    it('honours a caller-supplied threshold', () => {
      const all = heights(10);
      expect(
        computeVirtualWindow({ heights: all, scrollTop: 0, viewportHeight: 200, threshold: 4 })
          .virtualised,
      ).toBe(true);
      expect(
        computeVirtualWindow({ heights: all, scrollTop: 0, viewportHeight: 200, threshold: 20 })
          .virtualised,
      ).toBe(false);
    });
  });

  describe('window selection', () => {
    const all = heights(500); // 50 000px of content, 100px per item
    const viewportHeight = 800;

    it('renders from the first item when scrolled to the top', () => {
      const w = computeVirtualWindow({ heights: all, scrollTop: 0, viewportHeight });
      expect(w.startIndex).toBe(0);
      expect(w.padTopPx).toBe(0);
      // viewport + one overscan below, since there is nothing above item 0
      expect(w.endIndex).toBe((viewportHeight + DEFAULT_OVERSCAN_PX) / 100);
    });

    it('covers the viewport plus overscan on both sides in the middle', () => {
      const scrollTop = 25_000; // top of item 250
      const w = computeVirtualWindow({ heights: all, scrollTop, viewportHeight });
      expect(w.startIndex).toBe((scrollTop - DEFAULT_OVERSCAN_PX) / 100);
      expect(w.endIndex).toBe((scrollTop + viewportHeight + DEFAULT_OVERSCAN_PX) / 100);
    });

    it('reaches the last item when scrolled to the bottom', () => {
      const w = computeVirtualWindow({
        heights: all,
        scrollTop: 50_000 - viewportHeight,
        viewportHeight,
      });
      expect(w.endIndex).toBe(500);
      expect(w.padBottomPx).toBe(0);
    });

    it('still renders an item when scrollTop is past the end of the list', () => {
      const w = computeVirtualWindow({ heights: all, scrollTop: 999_999, viewportHeight });
      expect(w.startIndex).toBe(499);
      expect(w.endIndex).toBe(500);
      expect(w.endIndex).toBeGreaterThan(w.startIndex);
    });

    it('clamps a negative scrollTop to the start rather than producing a negative pad', () => {
      const w = computeVirtualWindow({ heights: all, scrollTop: -500, viewportHeight });
      expect(w.startIndex).toBe(0);
      expect(w.padTopPx).toBe(0);
    });

    it('widens the window when overscan grows', () => {
      const tight = computeVirtualWindow({
        heights: all,
        scrollTop: 25_000,
        viewportHeight,
        overscanPx: 0,
      });
      const loose = computeVirtualWindow({
        heights: all,
        scrollTop: 25_000,
        viewportHeight,
        overscanPx: 2_000,
      });
      expect(loose.startIndex).toBeLessThan(tight.startIndex);
      expect(loose.endIndex).toBeGreaterThan(tight.endIndex);
    });
  });

  describe('height bookkeeping', () => {
    it('keeps padding plus rendered height equal to the full list height', () => {
      const all = heights(500);
      for (const scrollTop of [0, 1_000, 25_000, 49_200, 50_000]) {
        const w = computeVirtualWindow({ heights: all, scrollTop, viewportHeight: 800 });
        expect(totalOf(w, all)).toBe(50_000);
      }
    });

    it('holds that invariant with ragged, realistic heights', () => {
      const all = Array.from({ length: 400 }, (_, i) => 60 + ((i * 37) % 400));
      const full = all.reduce((sum, h) => sum + h, 0);
      for (const scrollTop of [0, 3_333, 20_000, full - 800]) {
        const w = computeVirtualWindow({ heights: all, scrollTop, viewportHeight: 800 });
        expect(totalOf(w, all)).toBe(full);
      }
    });

    it('substitutes the estimate for unmeasured items', () => {
      // An entirely unmeasured list must lay out exactly as if every item were the estimate.
      const unmeasured = Array.from({ length: 200 }, () => Number.NaN);
      const estimated = heights(200, ESTIMATED_ITEM_HEIGHT_PX);
      const args = { scrollTop: 6_000, viewportHeight: 800 };
      expect(computeVirtualWindow({ heights: unmeasured, ...args })).toEqual(
        computeVirtualWindow({ heights: estimated, ...args }),
      );
    });

    it.each([
      ['negative', -1],
      ['NaN', Number.NaN],
      ['infinite', Number.POSITIVE_INFINITY],
    ])('treats a %s height as unmeasured', (_label, bad) => {
      // One bad entry must behave exactly like that entry being the estimate — asserted
      // against the equivalent list rather than a hand-computed offset.
      const withBad = heights(200);
      const withEstimate = heights(200);
      withBad[5] = bad;
      withEstimate[5] = ESTIMATED_ITEM_HEIGHT_PX;
      const args = { scrollTop: 10_000, viewportHeight: 800 };
      expect(computeVirtualWindow({ heights: withBad, ...args })).toEqual(
        computeVirtualWindow({ heights: withEstimate, ...args }),
      );
    });

    it('never returns an empty window for a non-empty list', () => {
      const all = heights(300);
      for (const scrollTop of [-1_000, 0, 15_000, 30_000, 100_000]) {
        const w = computeVirtualWindow({ heights: all, scrollTop, viewportHeight: 0 });
        expect(w.endIndex).toBeGreaterThan(w.startIndex);
      }
    });
  });
});
