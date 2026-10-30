import type { Citation, CitationKind, ComposerMode } from '../domain/thread.js';

/**
 * Sofee's run protocol, v1 (docs/deep-agent-roadmap.md §3.7). The backend streams each event as
 * an SSE frame — `event: <type>` and `data: <payload json>` — so a decoded event is `{ type,
 * payload }`. Payload keys stay snake_case exactly as the server sends them: this module is the
 * wire contract, and `run-activity.ts` is what turns it into camelCase view state.
 */

/** Error codes a failed run can end with (roadmap §3.7, `run.failed`). Each one picks its own copy
 * and actions in the thread (ux-foundations.md §4.3, roadmap U6). */
export type RunErrorCode =
  | 'model_unavailable'
  | 'provider_error'
  | 'rate_limited'
  | 'quota_exceeded'
  | 'agent_disabled'
  | 'timeout'
  | 'internal';

export const RUN_ERROR_CODES: readonly RunErrorCode[] = [
  'model_unavailable',
  'provider_error',
  'rate_limited',
  'quota_exceeded',
  'agent_disabled',
  'timeout',
  'internal',
];

/** A run's lifecycle as the backend records it (`agent_runs.status`). */
export type RunStatus = 'queued' | 'running' | 'interrupted' | 'completed' | 'failed' | 'cancelled';

export type TodoStatus = 'pending' | 'in_progress' | 'completed';

export interface RunTodo {
  readonly content: string;
  readonly status: TodoStatus;
}

export interface RunStartedPayload {
  readonly run_id: string;
  readonly assistant_message_id: string;
  readonly mode: ComposerMode;
  readonly model_label: string;
}

export interface StatusPayload {
  readonly text: string;
}

export interface MessageDeltaPayload {
  readonly text: string;
}

export interface TodosUpdatedPayload {
  readonly items: readonly RunTodo[];
}

export interface ToolStartedPayload {
  readonly id: string;
  readonly name: string;
  readonly agent: string;
  readonly args_preview: string;
}

export interface ToolFinishedPayload {
  readonly id: string;
  readonly name: string;
  readonly agent: string;
  readonly status: 'success' | 'error';
  readonly result_preview: string;
  readonly duration_ms: number;
}

export interface SubagentStartedPayload {
  readonly id: string;
  readonly name: string;
  readonly task: string;
}

export interface SubagentFinishedPayload {
  readonly id: string;
  readonly name: string;
  readonly status: 'success' | 'error';
  readonly summary: string;
}

export interface SourceAddedPayload {
  readonly index: number;
  readonly title: string;
  readonly url: string | null;
  readonly kind: CitationKind;
  readonly ref: string | null;
}

export interface FileWrittenPayload {
  readonly path: string;
  readonly size: number | null;
}

export interface UiDirectionsPayload {
  readonly items: readonly { readonly title: string; readonly why: string }[];
}

export interface UiQuizPayload {
  readonly items: readonly { readonly question: string; readonly answer: string }[];
}

export interface InterruptPayload {
  readonly interrupt_id: string;
  readonly kind: 'plan_review';
  readonly todos: readonly RunTodo[];
}

export interface UsagePayload {
  readonly input_tokens: number;
  readonly output_tokens: number;
  readonly context_percent: number | null;
}

export interface RunCompletedPayload {
  readonly assistant_message_id: string;
  readonly text: string;
  readonly citations: readonly Citation[];
}

export interface RunFailedPayload {
  readonly error_code: RunErrorCode;
  readonly message: string;
  readonly retryable: boolean;
}

export interface RunCancelledPayload {
  readonly assistant_message_id: string;
  readonly text: string;
}

/** Every event the run stream can carry. Discriminated on `type`, which is also the SSE event name. */
export type RunEvent =
  | { readonly type: 'run.started'; readonly payload: RunStartedPayload }
  | { readonly type: 'status'; readonly payload: StatusPayload }
  | { readonly type: 'message.delta'; readonly payload: MessageDeltaPayload }
  | { readonly type: 'todos.updated'; readonly payload: TodosUpdatedPayload }
  | { readonly type: 'tool.started'; readonly payload: ToolStartedPayload }
  | { readonly type: 'tool.finished'; readonly payload: ToolFinishedPayload }
  | { readonly type: 'subagent.started'; readonly payload: SubagentStartedPayload }
  | { readonly type: 'subagent.finished'; readonly payload: SubagentFinishedPayload }
  | { readonly type: 'source.added'; readonly payload: SourceAddedPayload }
  | { readonly type: 'file.written'; readonly payload: FileWrittenPayload }
  | { readonly type: 'ui.directions'; readonly payload: UiDirectionsPayload }
  | { readonly type: 'ui.quiz'; readonly payload: UiQuizPayload }
  | { readonly type: 'interrupt'; readonly payload: InterruptPayload }
  | { readonly type: 'usage'; readonly payload: UsagePayload }
  | { readonly type: 'run.completed'; readonly payload: RunCompletedPayload }
  | { readonly type: 'run.failed'; readonly payload: RunFailedPayload }
  | { readonly type: 'run.cancelled'; readonly payload: RunCancelledPayload };

export type RunEventType = RunEvent['type'];

/** Every SSE event name, listed once so the transport can subscribe to all of them. The type
 * assertion below fails to compile if a `RunEvent` variant is missing from this list. */
export const RUN_EVENT_TYPES = [
  'run.started',
  'status',
  'message.delta',
  'todos.updated',
  'tool.started',
  'tool.finished',
  'subagent.started',
  'subagent.finished',
  'source.added',
  'file.written',
  'ui.directions',
  'ui.quiz',
  'interrupt',
  'usage',
  'run.completed',
  'run.failed',
  'run.cancelled',
] as const satisfies readonly RunEventType[];

type MissingRunEventType = Exclude<RunEventType, (typeof RUN_EVENT_TYPES)[number]>;
const _allRunEventTypesListed: [MissingRunEventType] extends [never] ? true : never = true;

const TERMINAL_EVENT_TYPES: ReadonlySet<RunEventType> = new Set<RunEventType>([
  'run.completed',
  'run.failed',
  'run.cancelled',
]);

export function isRunEventType(name: string): name is RunEventType {
  return (RUN_EVENT_TYPES as readonly string[]).includes(name);
}

/** `run.completed`, `run.failed` and `run.cancelled` end the stream; the server closes it after them. */
export function isTerminalRunEvent(event: RunEvent): boolean {
  return TERMINAL_EVENT_TYPES.has(event.type);
}

/** Runs that still occupy their thread: the server answers 409 `run_active` for them. */
export function isActiveRunStatus(status: RunStatus): boolean {
  return status === 'queued' || status === 'running' || status === 'interrupted';
}

/** Pairs an SSE event name with its payload. Returns null for names this build does not know, so a
 * newer backend cannot crash an older client. The payload is trusted to match the contract. */
export function toRunEvent(name: string, payload: unknown): RunEvent | null {
  if (!isRunEventType(name)) return null;
  if (typeof payload !== 'object' || payload === null) return null;
  return { type: name, payload } as RunEvent;
}

/** Decodes one SSE frame's event name and JSON data. Null when either is unusable. */
export function decodeRunEvent(name: string, data: string): RunEvent | null {
  let payload: unknown;
  try {
    payload = JSON.parse(data);
  } catch {
    return null;
  }
  return toRunEvent(name, payload);
}
