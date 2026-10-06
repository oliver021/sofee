/**
 * Domain types for a conversation. Deliberately small: the assistant's replies are still
 * produced by the mock layer (see packages/core/src/mock) while conversations are persisted
 * through the API (M8), so these model exactly what the UI, the mock and the persistence
 * client need — not a general-purpose chat schema.
 */

export type MessageRole = 'user' | 'assistant';

/** ux-foundations.md §4.3 — the states a message can be in. */
export type MessageStatus = 'pending' | 'streaming' | 'complete' | 'stopped' | 'error';

/** design-system.md §5 — the Orbit mode orb cycles Learn -> Research -> Explore. */
export type ComposerMode = 'learn' | 'research' | 'explore';

export const COMPOSER_MODES: readonly ComposerMode[] = ['learn', 'research', 'explore'];

export function nextComposerMode(mode: ComposerMode): ComposerMode {
  const index = COMPOSER_MODES.indexOf(mode);
  return COMPOSER_MODES[(index + 1) % COMPOSER_MODES.length] as ComposerMode;
}

/** ux-foundations.md §4.5 — an inline superscript reference resolved in a source list. */
export interface Citation {
  readonly index: number;
  readonly title: string;
  readonly url: string;
}

export interface ChatMessage {
  readonly id: string;
  readonly role: MessageRole;
  status: MessageStatus;
  text: string;
  readonly createdAt: number;
  citations?: Citation[];
  /** Storage object ids for files attached to this message (M8: uploads via `/storage`). */
  attachmentIds?: string[];
  /** ux-foundations.md §4.4 — editing forks the thread; the previous branch stays reachable. */
  readonly editedFromId?: string;
}

export interface Thread {
  readonly id: string;
  title: string;
  readonly isTemporary: boolean;
  readonly createdAt: number;
  messages: ChatMessage[];
  mode: ComposerMode;
}

export interface Project {
  readonly id: string;
  name: string;
  threadIds: string[];
}

export interface ToolCallRecord {
  readonly id: string;
  readonly name: string;
  readonly status: 'running' | 'success' | 'error';
}

export interface McpServerRecord {
  readonly id: string;
  readonly name: string;
  readonly connected: boolean;
}

export interface AttachmentRecord {
  readonly id: string;
  readonly name: string;
  readonly kind: 'file' | 'image' | 'url';
  readonly sizeLabel?: string;
  /** Set once the file has been uploaded to `/storage`; referenced by messages via `attachmentIds`. */
  readonly storageId?: string;
  /** Same-origin download URL for an uploaded object. */
  readonly url?: string;
  readonly uploading?: boolean;
  readonly error?: boolean;
}

/** `crypto.randomUUID` is a standard global in both browsers and Node 19+ — no dependency
 * needed, and no Svelte/DOM coupling. */
export function createId(prefix: string): string {
  const uuid =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${uuid}`;
}
