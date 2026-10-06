import type { Palette, SemanticColors } from './types.js';

/**
 * The six palettes. Every `colors` hex below is copied verbatim from
 * design-system.md §2 — do not "improve" one without updating that document
 * and recomputing its contrast column first, per the file's own warning.
 *
 * `gradientCss` (layer 2 of the dotted field, §3) and the mood-derived
 * choices in `derivedOverrides` are this project's interpretation of the
 * prose mood descriptions in §2 (e.g. Nocturne's "violet bloom top-left,
 * cyan ember bottom-right") — the document gives moods and rules, not exact
 * gradient coordinates, so those are a judgement call. Everything else is
 * traceable straight back to an exact value in the spec.
 */
export const palettes: Record<Palette['id'], Palette> = {
  nocturne: {
    id: 'nocturne',
    label: 'Nocturne',
    scheme: 'dark',
    colors: {
      bg: '#07080F',
      surf: '#0E1020',
      ink: '#D2D5E8',
      mut: '#7A7F9E',
      acc: '#7B6BF5',
      acc2: '#3FD9E4',
    },
    dot: { color: '#D2D5E8', alphaStart: 0.12, alphaEnd: 0.05, radiusPx: 2.2, pitchPx: 22 },
    gradientCss: [
      'radial-gradient(1100px circle at 6% -10%, color-mix(in oklab, var(--p-acc) 32%, transparent) 0%, transparent 60%)',
      'radial-gradient(900px circle at 108% 112%, color-mix(in oklab, var(--p-acc2) 26%, transparent) 0%, transparent 58%)',
      'linear-gradient(180deg, transparent 0%, var(--p-bg) 94%)',
    ].join(',\n    '),
    display: {
      cssFamily: '"Sora", ui-sans-serif, system-ui, sans-serif',
      googleFontFamily: 'Sora',
      weights: [400, 500, 600, 700],
    },
  },

  overprint: {
    id: 'overprint',
    label: 'Overprint',
    scheme: 'light',
    colors: {
      bg: '#E9E8E3',
      surf: '#F4F3EF',
      ink: '#191A15',
      mut: '#63645B',
      acc: '#2438C9',
      acc2: '#F2568F',
    },
    dot: { color: '#2438C9', alphaStart: 0.15, alphaEnd: 0.06, radiusPx: 2.0, pitchPx: 12 },
    dotMaskFlat: true,
    gradientCss: [
      'radial-gradient(760px circle at 10% 6%, color-mix(in oklab, var(--p-acc) 22%, transparent) 0%, transparent 56%)',
      'radial-gradient(760px circle at 94% 90%, color-mix(in oklab, var(--p-acc2) 20%, transparent) 0%, transparent 56%)',
      'linear-gradient(155deg, color-mix(in oklab, var(--p-ink) 5%, transparent) 0%, transparent 46%)',
    ].join(',\n    '),
    blend: 'multiply',
    display: {
      cssFamily: '"Familjen Grotesk", ui-sans-serif, system-ui, sans-serif',
      googleFontFamily: 'Familjen Grotesk',
      weights: [400, 500, 600, 700],
    },
    derivedOverrides: {
      // §2: "flat ... no glow, no glass." §7: hard cast shadow, never blurred.
      hi: 'transparent',
      glow: 'transparent',
      shadowPanel: '3px 3px 0 rgba(36, 56, 201, 0.22)',
      shadowMenu: '2px 2px 0 rgba(36, 56, 201, 0.22)',
      // §5: "a title gradient that stops at acc rather than running into acc2."
      titleGradient: 'linear-gradient(135deg, var(--p-acc) 0%, var(--p-acc) 100%)',
      // §6: "Overprint overrides the glyph to #F4F3EF because its ground is light."
      sendInk: '#F4F3EF',
    },
  },

  tidepool: {
    id: 'tidepool',
    label: 'Tidepool',
    scheme: 'dark',
    colors: {
      bg: '#08171B',
      surf: '#0F262C',
      ink: '#D7E4E2',
      mut: '#70908F',
      acc: '#DFAE54',
      acc2: '#4FA8A0',
    },
    dot: { color: '#DFAE54', alphaStart: 0.13, alphaEnd: 0.05, radiusPx: 2.3, pitchPx: 27 },
    gradientCss: [
      'radial-gradient(1000px circle at 50% 122%, color-mix(in oklab, var(--p-acc2) 26%, transparent) 0%, transparent 62%)',
      'radial-gradient(760px circle at 88% -6%, color-mix(in oklab, var(--p-acc) 20%, transparent) 0%, transparent 58%)',
      'linear-gradient(0deg, color-mix(in oklab, var(--p-acc2) 12%, transparent) 0%, transparent 42%)',
    ].join(',\n    '),
    display: {
      cssFamily: '"Fraunces", ui-serif, Georgia, serif',
      googleFontFamily: 'Fraunces',
      weights: [400, 500, 600],
    },
  },

  coffee: {
    id: 'coffee',
    label: 'Coffee',
    scheme: 'dark',
    colors: {
      bg: '#150F0A',
      surf: '#221811',
      ink: '#F0E4D4',
      mut: '#A08C72',
      acc: '#D9903F',
      acc2: '#D4705A',
    },
    dot: { color: '#D9903F', alphaStart: 0.13, alphaEnd: 0.05, radiusPx: 2.4, pitchPx: 24 },
    gradientCss: [
      'radial-gradient(900px circle at 14% -6%, color-mix(in oklab, var(--p-acc) 26%, transparent) 0%, transparent 58%)',
      'radial-gradient(820px circle at 100% 104%, color-mix(in oklab, var(--p-acc2) 22%, transparent) 0%, transparent 58%)',
      'linear-gradient(180deg, transparent 0%, var(--p-bg) 92%)',
    ].join(',\n    '),
    display: {
      cssFamily: '"Bricolage Grotesque", ui-sans-serif, system-ui, sans-serif',
      googleFontFamily: 'Bricolage Grotesque',
      weights: [400, 500, 600, 700],
    },
    derivedOverrides: {
      // §2: "Ground and surface separate by only 1.09:1. Cards need a stroke, not a fill."
      // The stroke itself is a component-level choice (packages/ui), not a token —
      // noted here only so the reason isn't lost.
    },
  },

  terminal: {
    id: 'terminal',
    label: 'Hacker Terminal',
    scheme: 'dark',
    colors: {
      bg: '#060A07',
      surf: '#0C120D',
      ink: '#BFEFC8',
      mut: '#5F8A67',
      acc: '#3DDC7F',
      acc2: '#F2A03D',
    },
    dot: { color: '#3DDC7F', alphaStart: 0.17, alphaEnd: 0.07, radiusPx: 1.9, pitchPx: 18 },
    gradientCss: [
      // §2: "Phosphor green tires the eye in large blocks ... never an area fill."
      // Kept far more restrained than the other five for exactly that reason.
      'radial-gradient(1400px circle at 50% -24%, color-mix(in oklab, var(--p-acc) 9%, transparent) 0%, transparent 70%)',
      'radial-gradient(1000px circle at 100% 120%, color-mix(in oklab, var(--p-acc2) 7%, transparent) 0%, transparent 66%)',
      'linear-gradient(180deg, transparent 0%, var(--p-bg) 96%)',
    ].join(',\n    '),
    scanline: 'true',
    display: {
      cssFamily: '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
      googleFontFamily: 'IBM Plex Mono',
      weights: [400, 500, 600],
    },
  },

  navy: {
    id: 'navy',
    label: 'Blue Navy',
    scheme: 'dark',
    colors: {
      bg: '#0A1428',
      surf: '#122040',
      ink: '#DCE4F2',
      mut: '#7E8FAE',
      acc: '#4D8EF0',
      acc2: '#D9C39B',
    },
    dot: { color: '#DCE4F2', alphaStart: 0.125, alphaEnd: 0.05, radiusPx: 2.2, pitchPx: 23 },
    gradientCss: [
      'radial-gradient(1000px circle at 90% -10%, color-mix(in oklab, var(--p-acc) 26%, transparent) 0%, transparent 60%)',
      // §2: champagne "must appear in real states and real data, not as trim" —
      // kept as a small share of the ambient wash so it does not become decoration.
      'radial-gradient(700px circle at 8% 108%, color-mix(in oklab, var(--p-acc2) 12%, transparent) 0%, transparent 55%)',
      'linear-gradient(180deg, transparent 0%, var(--p-bg) 94%)',
    ].join(',\n    '),
    display: {
      cssFamily: '"Archivo", ui-sans-serif, system-ui, sans-serif',
      googleFontFamily: 'Archivo',
      weights: [400, 500, 600, 700],
    },
  },
};

export const paletteIds = Object.keys(palettes) as Array<Palette['id']>;

export const DEFAULT_PALETTE: Palette['id'] = 'nocturne';

/**
 * Success / warning / critical — "a separate scale ... never the accent"
 * (design-system.md §1). No hex values are given in the spec for these, so
 * this is a judgement call: one set tuned for the five dark grounds, one
 * for Overprint's light ground, chosen to clear 4.5:1 against that palette's
 * `bg`. The context meter (ux-foundations.md §2.2) is the one place these
 * are load-bearing today.
 */
export const semanticColors: Record<'dark' | 'light', SemanticColors> = {
  dark: {
    success: '#4ADE80',
    successInk: '#0B0B0C',
    warning: '#F5A524',
    warningInk: '#0B0B0C',
    critical: '#FF5C5C',
    criticalInk: '#0B0B0C',
  },
  light: {
    success: '#1E7A46',
    successInk: '#F4F3EF',
    warning: '#8A5A00',
    warningInk: '#F4F3EF',
    critical: '#B3261E',
    criticalInk: '#F4F3EF',
  },
};
