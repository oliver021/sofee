/**
 * Palette-independent tokens: spacing/radius (design-system.md §8), rail and
 * canvas geometry (ux-foundations.md §2, §4/5), motion (ux-foundations.md
 * §9), and the semantic scale (design-system.md §1 — "a separate scale ...
 * never the accent"). These do not vary per palette, so they are
 * hand-written once here rather than generated per palette, then
 * concatenated onto the generated file by build.ts.
 */
export const baseCss = /* css */ `
:root {
  /* §8 Spacing and radius — 4px base */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
  --space-8: 64px;

  --radius-capsule: 999px;
  --radius-panel: 16px;
  --radius-menu: 12px;
  --radius-icon-btn: 10px;
  --radius-swatch: 4px;

  /* Layout geometry (ux-foundations.md §2, §4, §5) */
  /* Space the floating toolbars need on each side of the canvas (design-system.md §8)
     so conversation content never sits underneath them. */
  --toolbar-gutter: 72px;
  /* 16px offset + 54px toolbar + 8px gap: enough for a panel or the canvas to clear the
     floating header entirely rather than shaving its bottom edge. */
  --toolbar-inset-block: 78px;
  --canvas-max-width: 760px;
  --composer-height: 54px;
  --composer-block-size: calc(var(--composer-height) + var(--space-8));
  --target-min: 44px;
  --icon-size: 20px;
  --icon-stroke: 1.6;

  /* §9 Motion */
  --motion-panel-duration: 200ms;
  --motion-panel-easing: cubic-bezier(0.2, 0.8, 0.25, 1);
  --motion-menu-duration: 120ms;
  --motion-menu-easing: ease-out;
  --motion-focus-duration: 340ms;
  --motion-focus-easing: cubic-bezier(0.2, 0.8, 0.25, 1);
  --motion-jump-duration: 160ms;
  --motion-jump-easing: ease-out;

  /* §1 — semantic colours are a separate scale, never the accent. No hex is
     given in the spec; see palettes.ts for the write-up. Defaults below are
     the "dark" set; the light (Overprint) set is applied per-palette. */
  --sem-success: #4ade80;
  --sem-success-ink: #0b0b0c;
  --sem-warning: #f5a524;
  --sem-warning-ink: #0b0b0c;
  --sem-critical: #ff5c5c;
  --sem-critical-ink: #0b0b0c;
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --motion-panel-duration: 1ms;
    --motion-menu-duration: 1ms;
    --motion-focus-duration: 1ms;
    --motion-jump-duration: 1ms;
  }
}
`;
