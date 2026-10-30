/**
 * The client side of the run protocol (docs/deep-agent-roadmap.md §3.7). Mutations go through
 * `api()`, so CSRF and the 401 handling behave like every other route. The event stream is a plain
 * EventSource: a GET with the session cookie and nothing to protect, resumed by the browser with
 * `Last-Event-ID` after a network drop, and by `after=` when the page itself reattaches.
 *
 * Ids here are the client ids the thread already uses: the thread id is the run route's
 * `{thread_id}`, and the assistant message id is the one the UI keyed the placeholder with.
 */
import {
  decodeRunEvent,
  isTerminalRunEvent,
  RUN_EVENT_TYPES,
  type ComposerMode,
  type RunErrorCode,
  type RunEvent,
  type RunStatus,
  type RunTodo,
} from '@sofee/core';
import { api, ApiError } from './api.js';

export interface RunUserMessageBody {
  readonly client_id: string;
  readonly text: string;
  readonly attachment_ids: readonly string[] | null;
}

export interface CreateRunBody {
  readonly kind: 'send' | 'regenerate' | 'continue';
  readonly assistant_client_id: string;
  readonly mode: ComposerMode;
  readonly model_slug: string | null;
  /** Required for `send`; the server ignores it for `regenerate` and `continue`. */
  readonly user_message: RunUserMessageBody | null;
}

export interface CreatedRun {
  readonly run_id: string;
  readonly assistant_message_id: string;
  readonly status: string;
}

export interface RunSummary {
  readonly run_id: string;
  readonly assistant_message_id: string;
  readonly status: RunStatus;
  readonly mode: ComposerMode;
  readonly started_at: string | null;
  readonly finished_at: string | null;
}

export interface StoredRunEvent {
  readonly seq: number;
  readonly type: string;
  readonly payload: unknown;
}

/** One run from `GET /threads/{id}/runs`: its summary plus every event except `message.delta`. */
export interface RunWithEvents extends RunSummary {
  readonly events: readonly StoredRunEvent[];
}

export interface RunSubscription {
  close(): void;
}

/** Called for every decoded event, with the event's sequence number. */
export type RunEventHandler = (seq: number, event: RunEvent) => void;

function encode(id: string): string {
  return encodeURIComponent(id);
}

export function createRun(threadId: string, body: CreateRunBody): Promise<CreatedRun> {
  return api<CreatedRun>(`/threads/${encode(threadId)}/runs`, { method: 'POST', body });
}

export function cancelRun(runId: string): Promise<void> {
  return api<void>(`/runs/${encode(runId)}/cancel`, { method: 'POST' });
}

/** Answers a plan-review interrupt. `edit` needs the full replacement plan. */
export function resumeRun(
  runId: string,
  decision: 'approve' | 'edit' | 'reject',
  todos: readonly RunTodo[] | null,
): Promise<void> {
  return api<void>(`/runs/${encode(runId)}/resume`, {
    method: 'POST',
    body: { decision, todos },
  });
}

export function listRuns(threadId: string): Promise<RunWithEvents[]> {
  return api<RunWithEvents[]>(`/threads/${encode(threadId)}/runs`);
}

/** The thread's newest run, or undefined when it has none (the server answers 204). */
export function getLatestRun(threadId: string): Promise<RunSummary | undefined> {
  return api<RunSummary | undefined>(`/threads/${encode(threadId)}/runs/latest`);
}

export function compactThread(threadId: string): Promise<{ summary_through_seq: number | null }> {
  return api(`/threads/${encode(threadId)}/context/compact`, { method: 'POST' });
}

export function clearThreadContext(threadId: string): Promise<{ context_start_seq: number }> {
  return api(`/threads/${encode(threadId)}/context/clear`, { method: 'POST' });
}

/**
 * Opens the event stream for a run, replaying stored events after `after` and then the live ones.
 * The server closes the stream after a terminal event, so the source is closed here too: left
 * open, EventSource would reconnect and replay the same run again. `onClosed` fires only when the
 * browser gives up on the stream (an HTTP error such as 404), not on ordinary network drops, which
 * EventSource retries by itself.
 */
export function subscribeToRun(
  runId: string,
  after: number,
  onEvent: RunEventHandler,
  onClosed: () => void,
): RunSubscription {
  const source = new EventSource(`/api/v1/runs/${encode(runId)}/events?after=${after}`);
  let open = true;

  const close = (): void => {
    if (!open) return;
    open = false;
    source.close();
  };

  for (const type of RUN_EVENT_TYPES) {
    source.addEventListener(type, (message) => {
      if (!open) return;
      const event = decodeRunEvent(type, (message as MessageEvent<string>).data);
      if (!event) return;
      const seq = Number((message as MessageEvent<string>).lastEventId);
      onEvent(Number.isFinite(seq) ? seq : 0, event);
      if (isTerminalRunEvent(event)) close();
    });
  }

  source.onerror = () => {
    if (open && source.readyState === EventSource.CLOSED) {
      close();
      onClosed();
    }
  };

  return { close };
}

export interface RunFailureInfo {
  readonly code: RunErrorCode;
  /** ISO time (UTC) a quota-exceeded send can be retried. */
  readonly resetAt?: string;
}

/**
 * Turns a failed create or context call into the code the thread shows. The backend answers
 * 429 `quota_exceeded` with `reset_at`, 503 `agent_disabled` when the switch is off, and anything
 * else is reported as an internal failure.
 */
export function failureInfoOf(error: unknown): RunFailureInfo {
  if (error instanceof ApiError) {
    if (error.status === 429 && error.message === 'quota_exceeded') {
      const resetAt = (error.body as { reset_at?: unknown } | null)?.reset_at;
      return {
        code: 'quota_exceeded',
        ...(typeof resetAt === 'string' ? { resetAt } : {}),
      };
    }
    if (error.status === 503 && error.message === 'agent_disabled') {
      return { code: 'agent_disabled' };
    }
    if (error.status === 503 && error.message === 'model_unavailable') {
      return { code: 'model_unavailable' };
    }
  }
  return { code: 'internal' };
}
