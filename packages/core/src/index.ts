// i18n
export type {
  Locale,
  MessageValue,
  PluralMessage,
  MessageSchema,
  MessagePath,
  Placeholders,
  Translate,
  I18n,
} from './i18n/i18n.js';
export {
  SUPPORTED_LOCALES,
  FALLBACK_LOCALE,
  createI18n,
  resolveLocale,
  readStoredLocale,
  writeStoredLocale,
} from './i18n/i18n.js';

// Scroll controller
export type {
  PinState,
  ScrollMetrics,
  ScrollInstruction,
  ScrollControllerSnapshot,
  ScrollControllerOptions,
  ScrollMemoryEntry,
} from './scroll/scroll-controller.js';
export {
  ScrollController,
  ScrollMemoryStore,
  distanceFromBottom,
  UNPIN_THRESHOLD_PX,
} from './scroll/scroll-controller.js';

// Virtual window
export type { VirtualWindowInput, VirtualWindow } from './virtual/virtual-window.js';
export {
  computeVirtualWindow,
  VIRTUALISE_THRESHOLD,
  DEFAULT_OVERSCAN_PX,
  ESTIMATED_ITEM_HEIGHT_PX,
} from './virtual/virtual-window.js';

// Domain
export type {
  MessageRole,
  MessageStatus,
  ComposerMode,
  Citation,
  ChatMessage,
  Thread,
  Project,
  ToolCallRecord,
  McpServerRecord,
  AttachmentRecord,
} from './domain/thread.js';
export { COMPOSER_MODES, nextComposerMode, createId } from './domain/thread.js';

// Mock assistant
export type { MockStreamOptions, MockReply } from './mock/mock-assistant.js';
export { MockAssistantStream, createMockReply } from './mock/mock-assistant.js';
