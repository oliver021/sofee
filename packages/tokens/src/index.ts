export type {
  PaletteId,
  Palette,
  PaletteBaseColors,
  DotSpec,
  DisplayFont,
  ColorScheme,
  SemanticColors,
} from './types.js';
export { palettes, paletteIds, DEFAULT_PALETTE, semanticColors } from './palettes.js';

import type { Palette } from './types.js';

/**
 * design-system.md §4: "Only the active palette's display face loads. Do
 * not ship six." Builds the Google Fonts stylesheet URL for exactly one
 * palette's display face, for a caller to inject as a `<link>` (and remove
 * the previous one) when the palette changes. Kept here, next to the font
 * data it reads, rather than in the app — but DOM mutation itself is left
 * to the caller so this package stays free of side effects.
 */
export function googleFontHref(display: Palette['display']): string {
  const family = display.googleFontFamily.replace(/ /g, '+');
  const weights = [...new Set(display.weights)].sort((a, b) => a - b).join(';');
  return `https://fonts.googleapis.com/css2?family=${family}:wght@${weights}&display=swap`;
}
