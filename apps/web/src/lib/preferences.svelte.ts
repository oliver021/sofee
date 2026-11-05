/**
 * Browser-local preferences that are not tied to a server feature: how the composer submits,
 * which motion level the interface uses, the default mode for new chats, and which answer
 * extras render. Kept in one localStorage record so resetting Settings is one write, and
 * applied to <html> in one effect (mirroring palette.svelte.ts).
 *
 * Language, palette and model keep their own existing storage keys; Settings calls their
 * setters directly so there is still a single source of truth per preference.
 */
import { COMPOSER_MODES, type ComposerMode } from '@sofee/core';

export type MotionPreference = 'system' | 'reduce';

export interface Preferences {
  readonly motion: MotionPreference;
  readonly defaultMode: ComposerMode;
  readonly notifyOnComplete: boolean;
  readonly invertSendKey: boolean;
  readonly showSources: boolean;
  readonly showDirections: boolean;
  readonly showQuiz: boolean;
}

export const DEFAULT_PREFERENCES: Preferences = {
  motion: 'system',
  defaultMode: 'learn',
  notifyOnComplete: false,
  invertSendKey: false,
  showSources: true,
  showDirections: true,
  showQuiz: true,
};

const STORAGE_KEY = 'sofee:preferences';

function isComposerMode(value: unknown): value is ComposerMode {
  return typeof value === 'string' && (COMPOSER_MODES as readonly string[]).includes(value);
}

function isMotion(value: unknown): value is MotionPreference {
  return value === 'system' || value === 'reduce';
}

function readPreferences(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PREFERENCES };
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return { ...DEFAULT_PREFERENCES };
    const record = parsed as Record<string, unknown>;
    const boolean = (value: unknown, fallback: boolean): boolean =>
      typeof value === 'boolean' ? value : fallback;
    return {
      motion: isMotion(record.motion) ? record.motion : DEFAULT_PREFERENCES.motion,
      defaultMode: isComposerMode(record.defaultMode)
        ? record.defaultMode
        : DEFAULT_PREFERENCES.defaultMode,
      notifyOnComplete: boolean(record.notifyOnComplete, DEFAULT_PREFERENCES.notifyOnComplete),
      invertSendKey: boolean(record.invertSendKey, DEFAULT_PREFERENCES.invertSendKey),
      showSources: boolean(record.showSources, DEFAULT_PREFERENCES.showSources),
      showDirections: boolean(record.showDirections, DEFAULT_PREFERENCES.showDirections),
      showQuiz: boolean(record.showQuiz, DEFAULT_PREFERENCES.showQuiz),
    };
  } catch {
    // Disabled storage: preferences last for this page only, like palette/locale.
    return { ...DEFAULT_PREFERENCES };
  }
}

function writePreferences(value: Preferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Best-effort persistence only.
  }
}

class PreferencesState {
  values = $state<Preferences>(readPreferences());

  set<K extends keyof Preferences>(key: K, value: Preferences[K]): void {
    this.values = { ...this.values, [key]: value };
    writePreferences(this.values);
  }

  reset(): void {
    this.values = { ...DEFAULT_PREFERENCES };
    writePreferences(this.values);
  }
}

export const preferences = new PreferencesState();

$effect.root(() => {
  $effect(() => {
    document.documentElement.dataset.motion = preferences.values.motion;
  });
});
