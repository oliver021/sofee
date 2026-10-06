import type { DerivedOverrides, Palette } from './types.js';

/**
 * Tokens that design-system.md describes the *behaviour* of but does not
 * give a hex for (`--p-surf-2`, `--p-line`, `--p-line-2`, `--p-hi`,
 * `--p-glow`) plus two extras this build introduces to honour sentences in
 * §5/§6/§7 without ever hard-coding a colour in a component:
 * `--p-title-grad` and `--p-send-ink`. See palettes.ts's file comment and
 * the README for the full judgement-call write-up.
 *
 * Every formula below is a CSS `color-mix()` expression that references
 * *other* custom properties in the same rule — it is resolved by the
 * browser at paint time, not baked into a literal hex here. That keeps the
 * relationship between (say) `--p-line` and `--p-ink` visible in the
 * generated CSS itself instead of hiding it in a build-time computation.
 */
export function derivedTokens(palette: Palette): Record<string, string> {
  const overrides: DerivedOverrides = palette.derivedOverrides ?? {};

  return {
    '--p-surf-2': 'color-mix(in oklab, var(--p-surf) 88%, var(--p-ink) 12%)',
    '--p-line': 'color-mix(in oklab, var(--p-ink) 14%, transparent)',
    '--p-line-2': 'color-mix(in oklab, var(--p-ink) 26%, transparent)',
    '--p-hi': overrides.hi ?? 'color-mix(in oklab, white 10%, transparent)',
    '--p-glow': overrides.glow ?? 'color-mix(in oklab, var(--p-acc) 55%, transparent)',
    '--p-shadow-panel': overrides.shadowPanel ?? '0 12px 32px rgba(0, 0, 0, 0.38)',
    '--p-shadow-menu': overrides.shadowMenu ?? '0 6px 16px rgba(0, 0, 0, 0.32)',
    '--p-title-grad':
      overrides.titleGradient ?? 'linear-gradient(135deg, var(--p-acc) 0%, var(--p-acc2) 100%)',
    '--p-send-ink': overrides.sendInk ?? 'var(--p-bg)',
  };
}

/** `#RRGGBB` -> `[r, g, b]`. Used only for the literal `rgba()` dot formula (§3), which the
 * spec writes as literal channel values rather than a `color-mix()` expression. */
export function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  const r = Number.parseInt(clean.substring(0, 2), 16);
  const g = Number.parseInt(clean.substring(2, 4), 16);
  const b = Number.parseInt(clean.substring(4, 6), 16);
  return [r, g, b];
}
