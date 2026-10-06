import { OverlayScrollbars, type ScrollbarsAutoHideBehavior } from 'overlayscrollbars';

/**
 * Custom scrollbars, applied with OverlayScrollbars.
 *
 * The one thing this must not do is take ownership of scrolling. ux-foundations.md §3 puts
 * ScrollController in charge of `scrollTop` — pin state, the send-time hold, jump-to-latest —
 * and a scrollbar library that wraps the element in its own viewport would move the property
 * every one of those reads and writes depends on. So the target element is declared as the
 * viewport, and the padding and content wrappers are switched off: OverlayScrollbars paints
 * scrollbars over the element we already had, and the DOM it scrolls is unchanged.
 */
export interface ScrollbarsParams {
  /** When the scrollbar fades out. `'scroll'` keeps the reading surface clean at rest. */
  autoHide?: ScrollbarsAutoHideBehavior;
  /** Milliseconds before it fades after the last scroll. */
  autoHideDelay?: number;
}

export function scrollbars(node: HTMLElement, params: ScrollbarsParams = {}) {
  const instance = OverlayScrollbars(
    {
      target: node,
      elements: { viewport: node, padding: false, content: false },
      // Browsers that already overlay their native scrollbars (macOS, several Linux desktops)
      // would otherwise cancel initialisation, leaving those users with no visible scrollbar
      // at all rather than the themed one.
      cancel: { nativeScrollbarsOverlaid: false },
    },
    {
      scrollbars: {
        theme: 'os-theme-sofee',
        autoHide: params.autoHide ?? 'scroll',
        autoHideDelay: params.autoHideDelay ?? 700,
      },
    },
  );

  return {
    update(next: ScrollbarsParams): void {
      instance.options({
        scrollbars: {
          autoHide: next.autoHide ?? 'scroll',
          autoHideDelay: next.autoHideDelay ?? 700,
        },
      });
    },
    destroy(): void {
      instance.destroy();
    },
  };
}
