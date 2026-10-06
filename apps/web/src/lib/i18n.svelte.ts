/**
 * The one place @sofee/core's i18n module meets the DOM: resolves the initial locale (§7.1:
 * stored preference -> navigator.languages -> en), keeps `<html lang>` in sync, and persists
 * changes. `packages/ui` never imports this file or the concrete message catalogues — it only
 * sees the widened `Translate` shape (see core's i18n.ts doc comment on `Translate`), which is
 * what `tWide` below provides.
 */
import {
  createI18n,
  resolveLocale,
  readStoredLocale,
  writeStoredLocale,
  type Locale,
  type MessagePath,
  type Placeholders,
  type Translate,
} from '@sofee/core';
import en, { type Messages } from '@sofee/core/messages/en';
import es from '@sofee/core/messages/es';

const catalogs = { en, es } satisfies Record<Locale, Messages>;

function resolveInitialLocale(): Locale {
  const stored = readStoredLocale();
  const navLanguages = typeof navigator !== 'undefined' ? [...navigator.languages] : [];
  return resolveLocale(stored, navLanguages);
}

let locale = $state<Locale>(resolveInitialLocale());
const instance = $derived(createI18n(locale, catalogs[locale]));

export function getLocale(): Locale {
  return locale;
}

export function setLocale(next: Locale): void {
  locale = next;
  writeStoredLocale(next);
}

/** Precisely typed — safe to call with a literal path anywhere in apps/web. */
export function t(path: MessagePath<Messages>, params?: Placeholders): string {
  return instance.t(path, params);
}

export function formatRelativeTime(value: number, unit: Intl.RelativeTimeFormatUnit): string {
  return instance.formatRelativeTime(value, unit);
}

/** The boundary adapter packages/ui components accept as their `t` prop — see the `Translate`
 * doc comment in packages/core/src/i18n/i18n.ts for why this cast is the one place it happens. */
export const tWide: Translate = (path, params) => t(path as MessagePath<Messages>, params);

$effect.root(() => {
  $effect(() => {
    document.documentElement.lang = locale;
  });
});
