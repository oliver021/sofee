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
  CitationKind,
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

// Agent run protocol (roadmap §3.7): the wire events, and the view state the reducer builds from them
export type {
  RunErrorCode,
  RunStatus,
  TodoStatus,
  RunTodo,
  RunEvent,
  RunEventType,
  RunStartedPayload,
  RunCompletedPayload,
  RunFailedPayload,
  RunCancelledPayload,
  InterruptPayload,
  UsagePayload,
  SourceAddedPayload,
} from './agent/run-events.js';
export {
  RUN_ERROR_CODES,
  RUN_EVENT_TYPES,
  isActiveRunStatus,
  isRunEventType,
  isTerminalRunEvent,
  decodeRunEvent,
  toRunEvent,
} from './agent/run-events.js';
export type {
  RunActivity,
  RunTool,
  RunSubagent,
  RunSource,
  RunFile,
  RunDirection,
  RunQuizItem,
  RunInterrupt,
  RunUsage,
  RunFailure,
} from './agent/run-activity.js';
export { createRunActivity, applyRunEvent } from './agent/run-activity.js';

// Pure helpers over run view state (roadmap U2, U5, U16, U18)
export type {
  PlanProgress,
  AgentGroup,
  ContextMarkKind,
  ContextMarks,
  ContextCut,
} from './agent/run-view.js';
export {
  MAIN_AGENT,
  planProgress,
  newlyCompletedStep,
  groupByAgent,
  runSeconds,
  hostnameOf,
  contextMarks,
  editedPlan,
} from './agent/run-view.js';
