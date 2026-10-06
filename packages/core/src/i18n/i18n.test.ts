import { describe, expect, it, afterEach, vi } from 'vitest';
import {
  createI18n,
  resolveLocale,
  readStoredLocale,
  writeStoredLocale,
  type MessagePath,
  type MessageSchema,
} from './i18n.js';
import en from './messages/en.js';
import es from './messages/es.js';

describe('createI18n — t()', () => {
  it('returns a plain string message untouched', () => {
    const i18n = createI18n('en', en);
    expect(i18n.t('toolbar.chats.label')).toBe('Chats');
  });

  it('interpolates named placeholders without concatenation', () => {
    const i18n = createI18n('en', en);
    expect(i18n.t('composer.mode.switchedTo', { mode: 'Research' })).toBe(
      'Switched to Research mode',
    );
  });

  it('leaves an unmatched placeholder token untouched instead of throwing', () => {
    const i18n = createI18n('en', en);
    expect(i18n.t('composer.mode.switchedTo')).toBe('Switched to {mode} mode');
  });

  it('selects the plural category via Intl.PluralRules, not count === 1', () => {
    const i18n = createI18n('en', en);
    expect(i18n.t('toolbar.attachments.count', { count: 1 })).toBe('1 attachment');
    expect(i18n.t('toolbar.attachments.count', { count: 0 })).toBe('0 attachments');
    expect(i18n.t('toolbar.attachments.count', { count: 5 })).toBe('5 attachments');
  });

  it('selects the matching Spanish plural category independently', () => {
    const i18n = createI18n('es', es);
    expect(i18n.t('toolbar.attachments.count', { count: 1 })).toBe('1 adjunto');
    expect(i18n.t('toolbar.attachments.count', { count: 3 })).toBe('3 adjuntos');
  });

  it('falls back to the path string for a key that does not exist at runtime', () => {
    const i18n = createI18n('en', en);
    // Cast bypasses the compile-time path check to exercise the runtime guard.
    expect(i18n.t('does.not.exist' as MessagePath<typeof en>)).toBe('does.not.exist');
  });

  it('every English path resolves on the Spanish catalogue (same shape)', () => {
    const enI18n = createI18n('en', en);
    const esI18n = createI18n('es', es);
    const paths = collectPaths(en as unknown as MessageSchema);
    expect(paths.length).toBeGreaterThan(20);
    for (const path of paths) {
      const enValue = enI18n.t(path as MessagePath<typeof en>, {
        count: 1,
        mode: 'x',
        percent: 1,
        index: 1,
      });
      const esValue = esI18n.t(path as MessagePath<typeof en>, {
        count: 1,
        mode: 'x',
        percent: 1,
        index: 1,
      });
      expect(esValue).not.toBe(path); // resolved, not a fallback
      expect(enValue).not.toBe(path);
    }
  });
});

describe('createI18n — Intl-backed formatting', () => {
  it('formats numbers per-locale through Intl.NumberFormat, not by hand', () => {
    const enI18n = createI18n('en', en);
    const esI18n = createI18n('es', es);
    expect(enI18n.formatNumber(1234.5)).not.toBe(esI18n.formatNumber(1234.5));
  });

  it('formats relative time through Intl.RelativeTimeFormat', () => {
    const enI18n = createI18n('en', en);
    expect(enI18n.formatRelativeTime(-1, 'day')).toMatch(/yesterday/i);
  });

  it('formats dates through Intl.DateTimeFormat', () => {
    const enI18n = createI18n('en', en);
    const formatted = enI18n.formatDate(new Date('2026-01-15T10:00:00Z'), { dateStyle: 'long' });
    expect(formatted).toContain('2026');
  });
});

describe('resolveLocale', () => {
  it('prefers the stored preference over everything else', () => {
    expect(resolveLocale('es', ['en-US'])).toBe('es');
  });

  it('ignores an unsupported stored value and falls through', () => {
    expect(resolveLocale('fr', ['es-MX', 'en-US'])).toBe('es');
  });

  it('matches navigator.languages by base language, ignoring region', () => {
    expect(resolveLocale(null, ['es-MX', 'en-US'])).toBe('es');
  });

  it('falls back to English when nothing matches', () => {
    expect(resolveLocale(null, ['fr-FR', 'de-DE'])).toBe('en');
  });

  it('falls back to English with no stored value and no candidates', () => {
    expect(resolveLocale(undefined, [])).toBe('en');
  });
});

describe('stored locale persistence', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('round-trips through a working storage', () => {
    const store = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
    });
    expect(readStoredLocale()).toBeNull();
    writeStoredLocale('es');
    expect(readStoredLocale()).toBe('es');
  });

  it('never throws when storage access throws (private browsing, sandboxed frames, ...)', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('SecurityError');
      },
      setItem: () => {
        throw new Error('SecurityError');
      },
    });
    expect(() => readStoredLocale()).not.toThrow();
    expect(readStoredLocale()).toBeNull();
    expect(() => writeStoredLocale('en')).not.toThrow();
  });

  it('never throws when localStorage does not exist at all', () => {
    vi.stubGlobal('localStorage', undefined);
    expect(() => readStoredLocale()).not.toThrow();
    expect(readStoredLocale()).toBeNull();
  });
});

/** Walks a message schema and returns every dotted leaf path — used above to prove the two
 * catalogues stay in lockstep beyond what the type system alone can assert at runtime. */
function collectPaths(schema: MessageSchema, prefix = ''): string[] {
  const paths: string[] = [];
  for (const [key, value] of Object.entries(schema)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'string') {
      paths.push(path);
    } else if (typeof value === 'object' && value !== null && typeof value.other === 'string') {
      paths.push(path);
    } else if (typeof value === 'object' && value !== null) {
      paths.push(...collectPaths(value as MessageSchema, path));
    }
  }
  return paths;
}
