/**
 * Shape of one palette. See design-system.md §1 for the token contract and
 * §2 for the six palettes themselves.
 *
 * A handful of fields here (`derivedOverrides`, `gradientCss`, `scanline`,
 * `titleGradient`, `sendInk`, `shadow*`) are NOT enumerated in the §1 token
 * contract table verbatim. design-system.md describes the *behaviour* it
 * wants (an inner top highlight, a focus glow, a title gradient that stops
 * early for Overprint, a send-icon colour override, a hard "cast" shadow
 * for Overprint) without handing over hex values for all of it. Rather than
 * hard-code a colour in a component to fill that gap — which §1 calls a bug
 * outright — those values are modelled as first-class tokens here, derived
 * systematically from the six documented colours per palette. See
 * `derive.ts` for the formulas and the README for the write-up.
 */

export type PaletteId = 'nocturne' | 'overprint' | 'tidepool' | 'coffee' | 'terminal' | 'navy';

export type ColorScheme = 'dark' | 'light';

/** The six hex values design-system.md §2 gives verbatim, per palette. */
export interface PaletteBaseColors {
  bg: string;
  surf: string;
  ink: string;
  mut: string;
  acc: string;
  acc2: string;
}

/** design-system.md §3 — one soft dot per palette. */
export interface DotSpec {
  /** Hex colour the dot is rendered in. */
  color: string;
  /** Opacity at the centre of the dot (0%). */
  alphaStart: number;
  /** Opacity at the 46% stop, just before it reaches zero at 100%. */
  alphaEnd: number;
  /** `circle <radius>px` in the radial-gradient. */
  radiusPx: number;
  /** Grid pitch — spacing between dot centres. */
  pitchPx: number;
}

/** design-system.md §4 — only the active palette's display face loads. */
export interface DisplayFont {
  /** CSS font-family value, including fallbacks. */
  cssFamily: string;
  /** Google Fonts family name, used to build the lazy-loaded stylesheet URL. */
  googleFontFamily: string;
  /** Weights to request from Google Fonts. */
  weights: number[];
}

/** Selective overrides for the systematically-derived tokens (see derive.ts). */
export interface DerivedOverrides {
  hi?: string;
  glow?: string;
  shadowPanel?: string;
  shadowMenu?: string;
  titleGradient?: string;
  sendInk?: string;
}

export interface Palette {
  id: PaletteId;
  /** Human-facing name, e.g. "Nocturne" — used only in the palette switcher UI. */
  label: string;
  scheme: ColorScheme;
  colors: PaletteBaseColors;
  dot: DotSpec;
  /** design-system.md §3: "Overprint is the exception ... its mask is flat." */
  dotMaskFlat?: boolean;
  /** `--p-grad` — layer 2, authored per palette per the mood in §2. */
  gradientCss: string;
  /** `--p-blend` — only Overprint sets this (to `multiply`). */
  blend?: string;
  /** `--p-scanline` — only Hacker Terminal sets this (§2, "Extra gradient layer"). */
  scanline?: string;
  display: DisplayFont;
  derivedOverrides?: DerivedOverrides;
}

export interface SemanticColors {
  success: string;
  successInk: string;
  warning: string;
  warningInk: string;
  critical: string;
  criticalInk: string;
}
