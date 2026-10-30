import type { RunTodo } from './run-events.js';

/**
 * Pure helpers over a run's view state (roadmap U2, U5, U16, U18). They return numbers and groups
 * only: the app turns them into labels, so this module stays free of copy and of any framework.
 */

/** The agent name the backend uses for the main agent in tool and source events. */
export const MAIN_AGENT = 'main';

export interface PlanProgress {
  /** Steps in the plan. */
  readonly total: number;
  /** Steps marked completed. */
  readonly completed: number;
  /** The step to show as current, 1-based: the one in progress, else the first not completed, else
   * `total`. Zero when there is no plan. */
  readonly current: number;
}

export function planProgress(todos: readonly RunTodo[]): PlanProgress {
  const total = todos.length;
  if (total === 0) return { total: 0, completed: 0, current: 0 };
  const completed = todos.filter((todo) => todo.status === 'completed').length;
  const inProgress = todos.findIndex((todo) => todo.status === 'in_progress');
  const firstOpen = todos.findIndex((todo) => todo.status !== 'completed');
  let current = total;
  if (inProgress !== -1) current = inProgress + 1;
  else if (firstOpen !== -1) current = firstOpen + 1;
  return { total, completed, current };
}

/** The plan's progress when at least one more step was completed between two plans, else null.
 * Used to announce progress politely (roadmap U18), never the streamed text. */
export function newlyCompletedStep(
  previous: readonly RunTodo[],
  next: readonly RunTodo[],
): PlanProgress | null {
  const before = planProgress(previous).completed;
  const after = planProgress(next);
  return after.completed > before ? after : null;
}

export interface AgentGroup<T> {
  readonly agent: string;
  readonly items: T[];
}

/**
 * Splits items by the agent that produced them. The main agent's group comes first; the others
 * follow in the order they first appear. Groups with no items never exist.
 */
export function groupByAgent<T extends { readonly agent: string }>(
  items: readonly T[],
): AgentGroup<T>[] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const list = groups.get(item.agent);
    if (list) list.push(item);
    else groups.set(item.agent, [item]);
  }
  const ordered = [...groups.entries()].map(([agent, list]) => ({ agent, items: list }));
  return [
    ...ordered.filter((group) => group.agent === MAIN_AGENT),
    ...ordered.filter((group) => group.agent !== MAIN_AGENT),
  ];
}

/** Whole seconds between a run's start and finish, or null until both are known. */
export function runSeconds(startedAt: number | null, finishedAt: number | null): number | null {
  if (startedAt === null || finishedAt === null) return null;
  return Math.max(0, Math.round((finishedAt - startedAt) / 1000));
}

/** The host of a web source without a leading "www.", or null when there is no usable URL. */
export function hostnameOf(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const host = new URL(url).hostname.replace(/^www\./, '');
    return host.length > 0 ? host : null;
  } catch {
    return null;
  }
}

export type ContextMarkKind = 'compacted' | 'cleared';

export interface ContextMarks {
  readonly before: readonly ContextMarkKind[];
  readonly after: readonly ContextMarkKind[];
}

/** The cut points a thread reports: `summary_through_seq` (Compact) and `context_start_seq` (Clear). */
export interface ContextCut {
  readonly summaryThroughSeq?: number | null;
  readonly contextStartSeq?: number | null;
}

/**
 * Where the "context compacted here" and "context cleared here" dividers sit (roadmap U16). A
 * compaction divider follows the last message its summary covers. A clear divider precedes the
 * first message the model still sees, or follows the last message when nothing came after the
 * clear. A message with no known seq was written after the last refresh, so it counts as newer
 * than any cut.
 */
export function contextMarks(
  messages: readonly { readonly id: string; readonly seq?: number }[],
  cut: ContextCut,
): Record<string, ContextMarks> {
  const draft: Record<string, { before: ContextMarkKind[]; after: ContextMarkKind[] }> = {};
  const slot = (id: string) => {
    draft[id] ??= { before: [], after: [] };
    return draft[id];
  };
  const seqOf = (message: { readonly seq?: number }): number =>
    message.seq ?? Number.POSITIVE_INFINITY;

  const compactedThrough = cut.summaryThroughSeq ?? null;
  if (compactedThrough !== null) {
    let anchor: string | null = null;
    for (const message of messages) {
      if (seqOf(message) <= compactedThrough) anchor = message.id;
    }
    if (anchor !== null) slot(anchor).after.push('compacted');
  }

  const contextStart = cut.contextStartSeq ?? null;
  const last = messages[messages.length - 1];
  if (contextStart !== null && last !== undefined) {
    const first = messages.find((message) => seqOf(message) >= contextStart);
    if (first) slot(first.id).before.push('cleared');
    else slot(last.id).after.push('cleared');
  }
  return draft;
}

/**
 * The plan as the user edited it, ready to send back with an `edit` decision: trimmed, blank steps
 * dropped, and every step pending because none has started. Null when no step is left, since the
 * server refuses an empty edit.
 */
export function editedPlan(steps: readonly string[]): RunTodo[] | null {
  const contents = steps.map((step) => step.trim()).filter((step) => step.length > 0);
  if (contents.length === 0) return null;
  return contents.map((content) => ({ content, status: 'pending' as const }));
}
