import { describe, expect, it, vi } from 'vitest';
import {
  ScrollController,
  ScrollMemoryStore,
  distanceFromBottom,
  UNPIN_THRESHOLD_PX,
  type ScrollMetrics,
} from './scroll-controller.js';

function metrics(partial: Partial<ScrollMetrics>): ScrollMetrics {
  return { scrollTop: 0, scrollHeight: 1000, clientHeight: 600, ...partial };
}

describe('distanceFromBottom', () => {
  it('is zero when scrolled all the way down', () => {
    expect(
      distanceFromBottom(metrics({ scrollTop: 400, scrollHeight: 1000, clientHeight: 600 })),
    ).toBe(0);
  });

  it('grows as the user scrolls up', () => {
    expect(
      distanceFromBottom(metrics({ scrollTop: 0, scrollHeight: 1000, clientHeight: 600 })),
    ).toBe(400);
  });
});

describe('ScrollController — pin state machine (§3.1)', () => {
  it('starts pinned', () => {
    expect(new ScrollController().snapshot.pinned).toBe(true);
  });

  it('unpins once the user scrolls more than the threshold away from the bottom', () => {
    const controller = new ScrollController();
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 0, scrollHeight: 1000, clientHeight: 600 }),
    );
    expect(controller.snapshot.pinned).toBe(false);
  });

  it('stays pinned at exactly the threshold', () => {
    const controller = new ScrollController();
    const top = 1000 - 600 - UNPIN_THRESHOLD_PX;
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: top, scrollHeight: 1000, clientHeight: 600 }),
    );
    expect(controller.snapshot.pinned).toBe(true);
  });

  it('re-pins once the user scrolls back within the threshold of the bottom', () => {
    const controller = new ScrollController();
    controller.notifyUserScrollIntent(metrics({ scrollTop: 0 }));
    expect(controller.snapshot.pinned).toBe(false);
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 390, scrollHeight: 1000, clientHeight: 600 }),
    );
    expect(controller.snapshot.pinned).toBe(true);
  });

  it('never changes pin state from content resize alone — only from intent or explicit actions', () => {
    const controller = new ScrollController();
    controller.notifyUserScrollIntent(metrics({ scrollTop: 0 }));
    expect(controller.snapshot.pinned).toBe(false);
    controller.notifyContentResize(
      metrics({ scrollTop: 0, scrollHeight: 2000, clientHeight: 600 }),
    );
    expect(controller.snapshot.pinned).toBe(false);
  });

  it('respects a custom unpin threshold', () => {
    const controller = new ScrollController({ unpinThresholdPx: 10 });
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 1000 - 600 - 20, scrollHeight: 1000, clientHeight: 600 }),
    );
    expect(controller.snapshot.pinned).toBe(false);
  });
});

describe('ScrollController — streaming (§3.3)', () => {
  it('while pinned and idle, instructs an instant scroll-to-bottom on content growth', () => {
    const controller = new ScrollController();
    const instruction = controller.notifyContentResize(
      metrics({ scrollTop: 400, scrollHeight: 1000, clientHeight: 600 }),
    );
    expect(instruction).toEqual({ type: 'scroll-to-bottom', smooth: false });
  });

  it('while free, content growth does not move the viewport', () => {
    const controller = new ScrollController();
    controller.notifyUserScrollIntent(metrics({ scrollTop: 0 }));
    const instruction = controller.notifyContentResize(
      metrics({ scrollTop: 0, scrollHeight: 1400, clientHeight: 600 }),
    );
    expect(instruction).toEqual({ type: 'none' });
  });

  it('pauses entirely while the tab is hidden, even if pinned', () => {
    const controller = new ScrollController();
    controller.setHidden(true);
    const instruction = controller.notifyContentResize(
      metrics({ scrollTop: 400, scrollHeight: 1200, clientHeight: 600 }),
    );
    expect(instruction).toEqual({ type: 'none' });
  });

  it('catches up once, instantly, when the tab becomes visible again while pinned', () => {
    const controller = new ScrollController();
    controller.setHidden(true);
    const instruction = controller.setHidden(false);
    expect(instruction).toEqual({ type: 'scroll-to-bottom', smooth: false });
  });

  it('does not catch up on visibility change if the user was free', () => {
    const controller = new ScrollController();
    controller.notifyUserScrollIntent(metrics({ scrollTop: 0 }));
    controller.setHidden(true);
    const instruction = controller.setHidden(false);
    expect(instruction).toEqual({ type: 'none' });
  });
});

describe('ScrollController — Jump to latest (§3.4)', () => {
  it('is hidden while pinned', () => {
    const controller = new ScrollController();
    expect(controller.snapshot.showJumpToLatest).toBe(false);
  });

  it('stays hidden while free but within one viewport of the bottom', () => {
    const controller = new ScrollController();
    // distance = 1000 - 350 - 600 = 50: past the 48px unpin threshold (free), but well within
    // one viewport (600) of the bottom, so Jump to latest should not show yet.
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 350, scrollHeight: 1000, clientHeight: 600 }),
    );
    expect(controller.snapshot.pinned).toBe(false);
    expect(controller.snapshot.showJumpToLatest).toBe(false);
  });

  it('appears once free and more than one viewport away from the bottom', () => {
    const controller = new ScrollController();
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 0, scrollHeight: 2000, clientHeight: 600 }),
    ); // distance 1400
    expect(controller.snapshot.showJumpToLatest).toBe(true);
  });

  it('counts messages that arrive while free, and only while free', () => {
    const controller = new ScrollController();
    controller.notifyMessageArrived();
    expect(controller.snapshot.unreadCount).toBe(0); // still pinned — nothing to count

    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 0, scrollHeight: 2000, clientHeight: 600 }),
    );
    controller.notifyMessageArrived();
    controller.notifyMessageArrived();
    expect(controller.snapshot.unreadCount).toBe(2);
  });

  it('re-pins, clears the unread count, and asks for a smooth scroll', () => {
    const controller = new ScrollController();
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 0, scrollHeight: 2000, clientHeight: 600 }),
    );
    controller.notifyMessageArrived();
    const instruction = controller.jumpToLatest();
    expect(instruction).toEqual({ type: 'scroll-to-bottom', smooth: true });
    expect(controller.snapshot.pinned).toBe(true);
    expect(controller.snapshot.unreadCount).toBe(0);
    expect(controller.snapshot.showJumpToLatest).toBe(false);
  });
});

describe('ScrollController — reading position on send (§3.2)', () => {
  it('instructs an absolute scroll to the message offset, and reserves the tail space', () => {
    const controller = new ScrollController();
    const instruction = controller.prepareForSend({ messageTopOffset: 1000, viewportHeight: 600 });
    expect(instruction).toEqual({ type: 'scroll-to-offset', scrollTop: 1000 });
    expect(controller.snapshot.tailReserveActive).toBe(true);
    expect(controller.snapshot.tailReservePx).toBe(600);
    expect(controller.snapshot.pinned).toBe(true);
  });

  it('holds still while the reply is still shorter than the space below the message', () => {
    const controller = new ScrollController();
    controller.prepareForSend({ messageTopOffset: 1000, viewportHeight: 600 }); // holdBoundary = 1600
    // content-so-far (1100) + reserved tail (600) = 1700 scrollHeight; contentBottom = 1100 <= 1600
    const instruction = controller.notifyContentResize(
      metrics({ scrollTop: 1000, scrollHeight: 1700, clientHeight: 600 }),
    );
    expect(instruction).toEqual({ type: 'none' });
    expect(controller.snapshot.tailReserveActive).toBe(true);
  });

  it('hands off to the ordinary pinned bottom-chase once the reply outgrows the hold, reclaiming the spacer', () => {
    const controller = new ScrollController();
    controller.prepareForSend({ messageTopOffset: 1000, viewportHeight: 600 }); // holdBoundary = 1600
    // content-so-far (1650) + reserved tail (600) = 2250; contentBottom = 1650 > 1600
    const instruction = controller.notifyContentResize(
      metrics({ scrollTop: 1000, scrollHeight: 2250, clientHeight: 600 }),
    );
    expect(instruction).toEqual({ type: 'scroll-to-bottom', smooth: false });
    expect(controller.snapshot.tailReserveActive).toBe(false);
    expect(controller.snapshot.tailReservePx).toBe(0);

    // From here on it behaves like ordinary pinned streaming.
    const next = controller.notifyContentResize(
      metrics({ scrollTop: 1650, scrollHeight: 2400, clientHeight: 600 }),
    );
    expect(next).toEqual({ type: 'scroll-to-bottom', smooth: false });
  });

  it('exits the hold immediately if the user scrolls mid-hold, deferring to their intent', () => {
    const controller = new ScrollController();
    controller.prepareForSend({ messageTopOffset: 1000, viewportHeight: 600 });
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 1000, scrollHeight: 1700, clientHeight: 600 }),
    ); // distance 100 -> free
    expect(controller.snapshot.tailReserveActive).toBe(false);
    expect(controller.snapshot.pinned).toBe(false);
  });

  it('reclaims the spacer on stream-settled if the hold never had to hand off', () => {
    const controller = new ScrollController();
    controller.prepareForSend({ messageTopOffset: 1000, viewportHeight: 600 });
    controller.notifyStreamSettled();
    expect(controller.snapshot.tailReserveActive).toBe(false);
    expect(controller.snapshot.tailReservePx).toBe(0);
  });
});

describe('ScrollController — subscribe (Svelte-store-shaped)', () => {
  it('calls back immediately with the current snapshot', () => {
    const controller = new ScrollController();
    const run = vi.fn();
    controller.subscribe(run);
    expect(run).toHaveBeenCalledTimes(1);
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ pinned: true }));
  });

  it('calls back again only when the snapshot actually changes', () => {
    const controller = new ScrollController();
    const run = vi.fn();
    controller.subscribe(run);
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 0, scrollHeight: 2000, clientHeight: 600 }),
    );
    expect(run).toHaveBeenCalledTimes(2);
  });

  it('stops notifying after unsubscribe', () => {
    const controller = new ScrollController();
    const run = vi.fn();
    const unsubscribe = controller.subscribe(run);
    unsubscribe();
    controller.notifyUserScrollIntent(
      metrics({ scrollTop: 0, scrollHeight: 2000, clientHeight: 600 }),
    );
    expect(run).toHaveBeenCalledTimes(1);
  });
});

describe('ScrollMemoryStore (§3.5)', () => {
  it('returns undefined for a thread it has never seen', () => {
    expect(new ScrollMemoryStore().restore('thread-1')).toBeUndefined();
  });

  it('round-trips an entry by thread id', () => {
    const store = new ScrollMemoryStore();
    store.save('thread-1', { scrollTop: 420, topMostMessageId: 'msg-9' });
    expect(store.restore('thread-1')).toEqual({ scrollTop: 420, topMostMessageId: 'msg-9' });
  });

  it('keeps separate threads independent', () => {
    const store = new ScrollMemoryStore();
    store.save('thread-1', { scrollTop: 10, topMostMessageId: null });
    store.save('thread-2', { scrollTop: 20, topMostMessageId: 'msg-2' });
    expect(store.restore('thread-1')?.scrollTop).toBe(10);
    expect(store.restore('thread-2')?.scrollTop).toBe(20);
  });

  it('clears an entry', () => {
    const store = new ScrollMemoryStore();
    store.save('thread-1', { scrollTop: 10, topMostMessageId: null });
    store.clear('thread-1');
    expect(store.restore('thread-1')).toBeUndefined();
  });
});
