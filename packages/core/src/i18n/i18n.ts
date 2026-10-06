/**
 * A small, fully typed i18n layer built on native `Intl`.
 *
 * ux-foundations.md §7.1 asks for two locales with an architecture that
 * "must not assume two", plural/date/number formatting through `Intl`
 * (never hand-rolled), and explicitly says not to add a dependency for
 * this — "with two locales a typed local module is more reliable and the
 * swap point stays in one file." This is that one file.
 *
 * Type safety comes from `MessagePath`: it walks the *literal* shape of
 * whatever catalogue is passed to `createI18n`, so `t()` only accepts real
 * dotted paths into that catalogue. Message catalogues (messages/en.ts,
 * messages/es.ts) declare their own type as `typeof en`, so es.ts failing
 * to match en's shape — a missing key, an extra one, a plural collapsed
 * into a plain string — is a compile error, not a runtime fallback.
 */

export type Locale = 'en' | 'es';
export const SUPPORTED_LOCALES = ['en', 'es'] as const satisfies readonly Locale[];
export const FALLBACK_LOCALE: Locale = 'en';

/** CLDR plural categories relevant to en/es (both only ever resolve to "one" | "other",
 * but the shape stays open for a future locale that needs more). */
export type PluralMessage = { other: string } & Partial<
  Record<'zero' | 'one' | 'two' | 'few' | 'many', string>
>;
export type MessageValue = string | PluralMessage;
export type MessageSchema = { [key: string]: MessageValue | MessageSchema };

function isPluralMessage(value: MessageValue | MessageSchema): value is PluralMessage {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as PluralMessage).other === 'string'
  );
}

/** Dotted paths over a message catalogue, e.g. `"rail.new.tooltip"`. */
export type MessagePath<T, Prefix extends string = ''> = {
  [K in Extract<keyof T, string>]: T[K] extends PluralMessage
    ? `${Prefix}${K}`
    : T[K] extends string
      ? `${Prefix}${K}`
      : T[K] extends MessageSchema
        ? MessagePath<T[K], `${Prefix}${K}.`>
        : never;
}[Extract<keyof T, string>];

/** Named placeholders only — ux-foundations.md §7.1: "No concatenation. Full sentences
 * with named placeholders." `count` doubles as the cardinal for plural selection. */
export type Placeholders = Record<string, string | number> & { count?: number };

function readPath(schema: MessageSchema, path: string): MessageValue | undefined {
  const parts = path.split('.');
  let node: MessageSchema | MessageValue = schema;
  for (const part of parts) {
    if (typeof node !== 'object' || node === null || isPluralMessage(node)) return undefined;
    const next: MessageValue | MessageSchema | undefined = (node as MessageSchema)[part];
    if (next === undefined) return undefined;
    node = next;
  }
  return node as MessageValue;
}

function interpolate(template: string, params?: Placeholders): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in params ? String(params[key]) : match,
  );
}

/** A type-erased view of `I18n<M>['t']` — same runtime behaviour, but not tied to one
 * catalogue's literal shape. This is what `@sofee/ui` components accept as a prop: it lets them
 * render translated copy without importing the concrete message schema, which is exactly the
 * kind of app-specific "domain" detail packages/ui is not supposed to depend on. The app wires
 * its real, precisely-typed `t` into this looser shape at the one boundary that needs it. */
export type Translate = (path: string, params?: Placeholders) => string;

export interface I18n<M extends MessageSchema> {
  readonly locale: Locale;
  /** Looks up `path`, resolves a plural category via `Intl.PluralRules` when `params.count` is
   * given, then interpolates `{placeholders}`. Falls back to returning `path` itself if the key
   * is somehow missing at runtime (it cannot be, statically, for a well-typed catalogue). */
  t(path: MessagePath<M>, params?: Placeholders): string;
  formatNumber(value: number, options?: Intl.NumberFormatOptions): string;
  formatDate(value: Date | number, options?: Intl.DateTimeFormatOptions): string;
  formatRelativeTime(value: number, unit: Intl.RelativeTimeFormatUnit): string;
}

export function createI18n<M extends MessageSchema>(locale: Locale, messages: M): I18n<M> {
  const plural = new Intl.PluralRules(locale);
  const numberFmt = new Intl.NumberFormat(locale);
  const dateFmt = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' });
  const relativeFmt = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });

  return {
    locale,
    t(path, params) {
      const raw = readPath(messages, path as string);
      if (raw === undefined) return path as string;
      if (typeof raw === 'string') return interpolate(raw, params);
      const category = typeof params?.count === 'number' ? plural.select(params.count) : 'other';
      return interpolate(raw[category] ?? raw.other, params);
    },
    formatNumber: (value, options) =>
      options ? new Intl.NumberFormat(locale, options).format(value) : numberFmt.format(value),
    formatDate: (value, options) =>
      options ? new Intl.DateTimeFormat(locale, options).format(value) : dateFmt.format(value),
    formatRelativeTime: (value, unit) => relativeFmt.format(value, unit),
  };
}

/** ux-foundations.md §7.1: "Locale resolution order: stored preference -> navigator.languages
 * -> en." `candidates` is typically `navigator.languages`; kept as a parameter so this stays
 * framework- and DOM-free and is trivial to unit test. */
export function resolveLocale(
  stored: string | null | undefined,
  candidates: readonly string[],
  supported: readonly Locale[] = SUPPORTED_LOCALES,
  fallback: Locale = FALLBACK_LOCALE,
): Locale {
  const isSupported = (tag: string): tag is Locale =>
    (supported as readonly string[]).includes(tag);
  if (stored && isSupported(stored)) return stored;
  for (const candidate of candidates) {
    const base = candidate.toLowerCase().split('-')[0] ?? candidate;
    if (isSupported(base)) return base;
  }
  return fallback;
}

const STORAGE_KEY = 'sofee:locale';

/** localStorage throws in some contexts (private browsing, sandboxed iframes, storage
 * disabled by policy) — a locale preference is never worth crashing the app over. */
export function readStoredLocale(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeStoredLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Best-effort persistence only — see readStoredLocale.
  }
}
