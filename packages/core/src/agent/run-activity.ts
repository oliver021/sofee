import type { CitationKind } from '../domain/thread.js';
import type { RunErrorCode, RunEvent, RunStatus, RunTodo } from './run-events.js';

/**
 * What a run has done so far, as the UI shows it: the plan, the tool calls, the subagents, the
 * sources and the files. The reply text is not here — it lives on the assistant message, because
 * that is what the thread renders and persists (roadmap §3.9).
 *
 * Every field is `readonly`, and `applyRunEvent` never mutates its input: it returns a new object
 * that shares any unchanged parts. That keeps the reducer pure and makes Svelte's reactivity see
 * each change as a fresh value.
 */

export interface RunTool {
  readonly id: string;
  readonly name: string;
  readonly agent: string;
  readonly argsPreview: string;
  readonly status: 'running' | 'success' | 'error';
  readonly resultPreview: string | null;
  readonly durationMs: number | null;
}

export interface RunSubagent {
  readonly id: string;
  readonly name: string;
  readonly task: string;
  readonly status: 'running' | 'success' | 'error';
  readonly summary: string | null;
}

export interface RunSource {
  readonly index: number;
  readonly title: string;
  readonly url: string | null;
  readonly kind: CitationKind;
  readonly ref: string | null;
}

export interface RunFile {
  readonly path: string;
  readonly size: number | null;
}

export interface RunDirection {
  readonly title: string;
  readonly why: string;
}

export interface RunQuizItem {
  readonly question: string;
  readonly answer: string;
}

/** A pause waiting for the user's answer. Only `plan_review` exists so far. */
export interface RunInterrupt {
  readonly interruptId: string;
  readonly kind: 'plan_review';
  readonly todos: readonly RunTodo[];
}

export interface RunUsage {
  readonly inputTokens: number;
  readonly outputTokens: number;
  /** Share of the context window used by the last main-agent step, or null when the model does
   * not declare a window. */
  readonly contextPercent: number | null;
}

/** The failure a run ended with, kept so the thread can say what went wrong. */
export interface RunFailure {
  readonly code: RunErrorCode;
  readonly message: string;
  readonly retryable: boolean;
}

export interface RunActivity {
  readonly runId: string;
  readonly status: RunStatus;
  /** The latest `status` event's text, e.g. "Leyendo deploy.md…". Empty once the run ends. */
  readonly statusText: string;
  readonly todos: readonly RunTodo[];
  readonly tools: readonly RunTool[];
  readonly subagents: readonly RunSubagent[];
  readonly sources: readonly RunSource[];
  readonly files: readonly RunFile[];
  readonly directions: readonly RunDirection[];
  readonly quiz: readonly RunQuizItem[];
  readonly interrupt: RunInterrupt | null;
  readonly usage: RunUsage | null;
  readonly error: RunFailure | null;
  /** Epoch milliseconds, or null until known. */
  readonly startedAt: number | null;
  readonly finishedAt: number | null;
}

/** A fresh activity for a run that has been created but has not reported anything yet. */
export function createRunActivity(
  runId: string,
  status: RunStatus = 'queued',
  startedAt: number | null = null,
): RunActivity {
  return {
    runId,
    status,
    statusText: '',
    todos: [],
    tools: [],
    subagents: [],
    sources: [],
    files: [],
    directions: [],
    quiz: [],
    interrupt: null,
    usage: null,
    error: null,
    startedAt,
    finishedAt: null,
  };
}

/** Replaces the first item matching `matches`, or appends `item` when none does. */
function upsert<T>(list: readonly T[], item: T, matches: (existing: T) => boolean): readonly T[] {
  const index = list.findIndex(matches);
  if (index === -1) return [...list, item];
  return list.map((existing, i) => (i === index ? item : existing));
}

/** Any progress after a pause means the user's answer was taken (or was never needed), so the run
 * is running again. Returns the same object when there is nothing to change. */
function resumed(activity: RunActivity): RunActivity {
  if (activity.status === 'running' && activity.interrupt === null) return activity;
  return { ...activity, status: 'running', interrupt: null };
}

/**
 * Folds one run event into the activity. `at` stamps the start and finish times and defaults to
 * now; pass it explicitly when replaying stored events so the result does not depend on the clock.
 * `message.delta` is deliberately a near no-op here: its text belongs to the message, not to this
 * record, so the reducer only notes that the run is progressing.
 */
export function applyRunEvent(
  activity: RunActivity,
  event: RunEvent,
  at: number = Date.now(),
): RunActivity {
  switch (event.type) {
    case 'run.started':
      return {
        ...activity,
        status: 'running',
        startedAt: activity.startedAt ?? at,
      };
    case 'status':
      return { ...resumed(activity), statusText: event.payload.text };
    case 'message.delta':
      return resumed(activity);
    case 'todos.updated':
      return { ...resumed(activity), todos: event.payload.items };
    case 'tool.started': {
      const { id, name, agent, args_preview } = event.payload;
      const tool: RunTool = {
        id,
        name,
        agent,
        argsPreview: args_preview,
        status: 'running',
        resultPreview: null,
        durationMs: null,
      };
      return { ...resumed(activity), tools: upsert(activity.tools, tool, (t) => t.id === id) };
    }
    case 'tool.finished': {
      const { id, name, agent, status, result_preview, duration_ms } = event.payload;
      const existing = activity.tools.find((t) => t.id === id);
      const tool: RunTool = {
        id,
        name,
        agent,
        argsPreview: existing?.argsPreview ?? '',
        status,
        resultPreview: result_preview,
        durationMs: duration_ms,
      };
      return { ...resumed(activity), tools: upsert(activity.tools, tool, (t) => t.id === id) };
    }
    case 'subagent.started': {
      const { id, name, task } = event.payload;
      const subagent: RunSubagent = { id, name, task, status: 'running', summary: null };
      return {
        ...resumed(activity),
        subagents: upsert(activity.subagents, subagent, (s) => s.id === id),
      };
    }
    case 'subagent.finished': {
      const { id, name, status, summary } = event.payload;
      const existing = activity.subagents.find((s) => s.id === id);
      const subagent: RunSubagent = {
        id,
        name,
        task: existing?.task ?? '',
        status,
        summary,
      };
      return {
        ...resumed(activity),
        subagents: upsert(activity.subagents, subagent, (s) => s.id === id),
      };
    }
    case 'source.added': {
      const { index, title, url, kind, ref } = event.payload;
      const source: RunSource = { index, title, url, kind, ref };
      return {
        ...resumed(activity),
        sources: upsert(activity.sources, source, (s) => s.index === index),
      };
    }
    case 'file.written': {
      const { path, size } = event.payload;
      return {
        ...resumed(activity),
        files: upsert(activity.files, { path, size }, (f) => f.path === path),
      };
    }
    case 'ui.directions':
      return {
        ...resumed(activity),
        directions: event.payload.items.map((item) => ({ title: item.title, why: item.why })),
      };
    case 'ui.quiz':
      return {
        ...resumed(activity),
        quiz: event.payload.items.map((item) => ({ question: item.question, answer: item.answer })),
      };
    case 'interrupt':
      return {
        ...activity,
        status: 'interrupted',
        statusText: '',
        todos: event.payload.todos,
        interrupt: {
          interruptId: event.payload.interrupt_id,
          kind: event.payload.kind,
          todos: event.payload.todos,
        },
      };
    case 'usage':
      return {
        ...resumed(activity),
        usage: {
          inputTokens: event.payload.input_tokens,
          outputTokens: event.payload.output_tokens,
          contextPercent: event.payload.context_percent,
        },
      };
    case 'run.completed':
      return finish(activity, 'completed', at, { error: null });
    case 'run.failed':
      return finish(activity, 'failed', at, {
        error: {
          code: event.payload.error_code,
          message: event.payload.message,
          retryable: event.payload.retryable,
        },
      });
    case 'run.cancelled':
      return finish(activity, 'cancelled', at, {});
  }
}

function finish(
  activity: RunActivity,
  status: Extract<RunStatus, 'completed' | 'failed' | 'cancelled'>,
  at: number,
  patch: { readonly error?: RunFailure | null },
): RunActivity {
  return {
    ...activity,
    ...patch,
    status,
    statusText: '',
    interrupt: null,
    finishedAt: activity.finishedAt ?? at,
  };
}
