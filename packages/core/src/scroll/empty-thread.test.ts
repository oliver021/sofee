import { describe, expect, it } from 'vitest';
import { emptyThreadScrollTop } from './empty-thread.js';

describe('emptyThreadScrollTop', () => {
  it('sends an empty thread back to the top when the container was left scrolled', () => {
    expect(emptyThreadScrollTop(0, 1115.25)).toBe(0);
  });

  it('does nothing when an empty thread is already at the top', () => {
    expect(emptyThreadScrollTop(0, 0)).toBeNull();
  });

  it('never moves a thread that has messages', () => {
    expect(emptyThreadScrollTop(3, 1115)).toBeNull();
  });
});
