/**
 * Turns the run state into the view models packages/ui draws (roadmap §5: U2–U12). Pure on purpose:
 * every label goes through the `t` it is given and every number through the locale it is given, so
 * the same functions run in the app and under test. The UI never decides what a status means; this
 * module does.
 */
import {
  groupByAgent,
  hostnameOf,
  isActiveRunStatus,
  MAIN_AGENT,
  planProgress,
  runSeconds,
  type ChatMessage,
  type Citation,
  type RunActivity,
  type RunSubagent,
  type RunTodo,
  type RunTool,
  type Translate,
} from '@sofee/core';
import type {
  AgentFileView,
  AgentStatus,
  PlanStepStatus,
  PlanView,
  SourceView,
  SubagentView,
  ToolRowView,
  ToolRunView,
} from '@sofee/ui';

export interface AgentViewContext {
  readonly t: Translate;
  /** The active locale, used for numbers. */
  readonly locale: string;
}

/** How much of a user message names a run in the tool timeline. */
const RUN_TITLE_LIMIT = 60;

function formatNumber(value: number, locale: string, maximumFractionDigits = 0): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits }).format(value);
}

function truncate(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}

/** The last path segment, e.g. "informe.md" for "/notes/informe.md". */
export function basename(path: string): string {
  return (
    path
      .split('/')
      .filter((segment) => segment.length > 0)
      .pop() ?? path
  );
}

/** Bytes as a short size, e.g. "512 B", "4 KB", "1.2 MB". The unit names are the same in every
 * locale, so only the number is localised. */
export function formatSize(bytes: number, locale: string): string {
  if (bytes < 1024) return `${formatNumber(bytes, locale)} B`;
  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) return `${formatNumber(Math.round(kilobytes), locale)} KB`;
  return `${formatNumber(kilobytes / 1024, locale, 1)} MB`;
}

/** Each step's status, spoken next to its glyph. */
export function stepStatusLabel(status: RunTodo['status'], t: Translate): string {
  switch (status) {
    case 'pending':
      return t('agent.plan.status.pending');
    case 'in_progress':
      return t('agent.plan.status.inProgress');
    case 'completed':
      return t('agent.plan.status.completed');
  }
}

/** A sub-agent's status. Tool calls use the panel's own status words, see toolStatusLabel. */
export function agentStatusLabel(status: AgentStatus, t: Translate): string {
  switch (status) {
    case 'running':
      return t('agent.subagents.status.running');
    case 'success':
      return t('agent.subagents.status.success');
    case 'error':
      return t('agent.subagents.status.error');
  }
}

export function toolStatusLabel(status: AgentStatus, t: Translate): string {
  switch (status) {
    case 'running':
      return t('panel.toolCalls.statusRunning');
    case 'success':
      return t('panel.toolCalls.statusSuccess');
    case 'error':
      return t('panel.toolCalls.statusError');
  }
}

/** The name the backend gives a subagent. The two that exist have translated names; any other
 * name is shown as the backend sent it. */
export function subagentName(name: string, t: Translate): string {
  switch (name) {
    case 'investigador':
      return t('agent.subagents.researcher');
    case 'critico':
      return t('agent.subagents.critic');
    default:
      return name;
  }
}

/** The tool names the agent uses, translated. Anything else is shown as the backend named it. */
export function toolName(name: string, t: Translate): string {
  switch (name) {
    case 'write_todos':
      return t('agent.tools.names.writeTodos');
    case 'task':
      return t('agent.tools.names.task');
    case 'web_search':
      return t('agent.tools.names.webSearch');
    case 'search_team_docs':
      return t('agent.tools.names.searchTeamDocs');
    case 'read_file':
      return t('agent.tools.names.readFile');
    case 'write_file':
      return t('agent.tools.names.writeFile');
    case 'edit_file':
      return t('agent.tools.names.editFile');
    case 'ls':
      return t('agent.tools.names.ls');
    case 'grep':
      return t('agent.tools.names.grep');
    case 'glob':
      return t('agent.tools.names.glob');
    case 'suggest_directions':
      return t('agent.tools.names.suggestDirections');
    case 'check_understanding':
      return t('agent.tools.names.checkUnderstanding');
    default:
      return name;
  }
}

/** The plan as the reply shows it: a live checklist while the run works, a one-line summary once
 * it has finished. Null when the run has not written a plan. */
export function planView(activity: RunActivity, ctx: AgentViewContext): PlanView | null {
  if (activity.todos.length === 0) return null;
  const { t, locale } = ctx;
  const progress = planProgress(activity.todos);
  const running = isActiveRunStatus(activity.status);
  const sourceCount = activity.sources.length;
  const stepsText = t('agent.plan.stepCount', { count: progress.total });
  const sourcesText = t('agent.sources.live', { count: sourceCount });
  const seconds = runSeconds(activity.startedAt, activity.finishedAt);
  const summary =
    seconds === null
      ? t('agent.plan.summaryNoTime', { steps: stepsText, sources: sourcesText })
      : t('agent.plan.summary', {
          steps: stepsText,
          sources: sourcesText,
          seconds: t('agent.plan.seconds', { seconds: formatNumber(seconds, locale) }),
        });
  return {
    steps: activity.todos.map((todo) => ({
      content: todo.content,
      status: todo.status as PlanStepStatus,
      statusLabel: stepStatusLabel(todo.status, t),
    })),
    running,
    headline: running
      ? t('agent.plan.running', { step: progress.current, total: progress.total })
      : t('agent.plan.label'),
    summary,
    liveSources: running && sourceCount > 0 ? sourcesText : null,
  };
}

export function subagentViews(
  subagents: readonly RunSubagent[],
  ctx: AgentViewContext,
): SubagentView[] {
  return subagents.map((agent) => ({
    id: agent.id,
    name: subagentName(agent.name, ctx.t),
    task: agent.task,
    status: agent.status,
    statusLabel: agentStatusLabel(agent.status, ctx.t),
    summary: agent.summary,
  }));
}

/** Where a source lives, in words: the host of a web page, or "Team document" / "Attachment". */
export function sourceMeta(citation: Citation, t: Translate): string {
  if (citation.kind === 'kb') return t('agent.sources.teamDocument');
  if (citation.kind === 'attachment') return t('agent.sources.attachment');
  const host = hostnameOf(citation.url);
  if (host) return host;
  return citation.url ? '' : t('agent.sources.teamDocument');
}

/** The reply's sources in citation order. Team documents keep their own title, and an untitled one
 * gets a readable name rather than an empty row. */
export function sourceViews(citations: readonly Citation[], ctx: AgentViewContext): SourceView[] {
  return [...citations]
    .sort((a, b) => a.index - b.index)
    .map((citation) => ({
      index: citation.index,
      title: citation.title.trim().length > 0 ? citation.title : ctx.t('agent.sources.untitled'),
      meta: sourceMeta(citation, ctx.t),
      snippet: citation.snippet ?? null,
      citation,
    }));
}

function toolRow(tool: RunTool, ctx: AgentViewContext): ToolRowView {
  const { t, locale } = ctx;
  return {
    id: tool.id,
    name: toolName(tool.name, t),
    argsPreview: tool.argsPreview,
    status: tool.status,
    statusLabel: toolStatusLabel(tool.status, t),
    durationLabel:
      tool.durationMs === null
        ? t('agent.tools.running')
        : t('agent.plan.seconds', {
            seconds: formatNumber(tool.durationMs / 1000, locale, 1),
          }),
  };
}

/**
 * The tool calls of every run in the thread, oldest first, each grouped by the agent that made
 * them: the main agent's calls first, then one collapsible group per subagent. A run is named after
 * the user message that started it.
 */
export function toolRunViews(
  messages: readonly ChatMessage[],
  activityByMessage: Readonly<Record<string, RunActivity | undefined>>,
  ctx: AgentViewContext,
): ToolRunView[] {
  const { t } = ctx;
  const runs: ToolRunView[] = [];
  let lastUserText = '';
  for (const message of messages) {
    if (message.role === 'user') {
      lastUserText = message.text.trim();
      continue;
    }
    const activity = activityByMessage[message.id];
    if (!activity || activity.tools.length === 0) continue;
    const title =
      lastUserText.length > 0
        ? truncate(lastUserText, RUN_TITLE_LIMIT)
        : t('agent.tools.runTitle', { number: runs.length + 1 });
    runs.push({
      runId: activity.runId,
      title,
      groups: groupByAgent(activity.tools).map((group) => ({
        key: group.agent,
        label:
          group.agent === MAIN_AGENT ? t('agent.tools.mainAgent') : subagentName(group.agent, t),
        main: group.agent === MAIN_AGENT,
        rows: group.items.map((tool) => toolRow(tool, ctx)),
      })),
    });
  }
  return runs;
}

export function agentFileViews(
  files: readonly { readonly path: string; readonly size: number }[],
  ctx: AgentViewContext,
): AgentFileView[] {
  return files.map((file) => ({
    path: file.path,
    name: basename(file.path),
    sizeLabel: formatSize(file.size, ctx.locale),
  }));
}
