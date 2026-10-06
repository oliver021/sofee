/**
 * design-system.md §2/§4 — applies `data-palette` to `<html>`, persists the choice, and lazily
 * loads only the active palette's Google Fonts display face ("do not ship six").
 */
import {
  palettes,
  paletteIds,
  DEFAULT_PALETTE,
  googleFontHref,
  type PaletteId,
} from '@sofee/tokens';

const STORAGE_KEY = 'sofee:palette';
const FONT_LINK_ID = 'sofee-display-font';

function isPaletteId(value: string): value is PaletteId {
  return (paletteIds as string[]).includes(value);
}

function readStoredPalette(): PaletteId | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value && isPaletteId(value) ? value : null;
  } catch {
    return null;
  }
}

function writeStoredPalette(id: PaletteId): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Best-effort persistence only — see packages/core's i18n readStoredLocale for the same
    // reasoning (localStorage throws in some contexts).
  }
}

// index.html's inline pre-hydration script already stamped `data-palette` on <html> before this
// module ever runs, so read that back rather than defaulting blind — it may reflect a stored
// preference this module has no other record of yet.
function resolveInitialPalette(): PaletteId {
  const fromDom = document.documentElement.dataset.palette;
  if (fromDom && isPaletteId(fromDom)) return fromDom;
  return readStoredPalette() ?? DEFAULT_PALETTE;
}

let paletteId = $state<PaletteId>(resolveInitialPalette());

export function getPaletteId(): PaletteId {
  return paletteId;
}

export function setPaletteId(id: PaletteId): void {
  paletteId = id;
  writeStoredPalette(id);
}

export function listPalettes() {
  return paletteIds.map((id) => palettes[id]);
}

function applyDisplayFont(id: PaletteId): void {
  const href = googleFontHref(palettes[id].display);
  let link = document.getElementById(FONT_LINK_ID) as HTMLLinkElement | null;
  if (!link) {
    link = document.createElement('link');
    link.id = FONT_LINK_ID;
    link.rel = 'stylesheet';
    document.head.appendChild(link);
  }
  if (link.href !== href) link.href = href;
}

$effect.root(() => {
  $effect(() => {
    document.documentElement.dataset.palette = paletteId;
    applyDisplayFont(paletteId);
  });
});
