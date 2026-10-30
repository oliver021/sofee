import { describe, expect, it } from 'vitest';
import {
  createRunActivity,
  type ChatMessage,
  type Citation,
  type RunActivity,
  type Translate,
} from '@sofee/core';
import {
  agentFileViews,
  basename,
  formatSize,
  planView,
  sourceMeta,
  sourceViews,
  subagentName,
  toolRunViews,
  type AgentViewContext,
} from './agent-view.js';

/** Returns the key and its parameters, so a test can assert which copy was asked for. */
const t: Translate = (path, params) =>
  params === undefined ? path : `${path}${JSON.stringify(params)}`;

const ctx: AgentViewContext = { t, locale: 'en' };

function activity(overrides: Partial<RunActivity>): RunActivity {
  return { ...createRunActivity('run-1', 'running', 1_000), ...overrides };
}

const message = (id: string, role: ChatMessage['role'], text = ''): ChatMessage => ({
  id,
  role,
  status: 'complete',
  text,
  createdAt: 0,
});

describe('planView', () => {
  it('is absent when the run has not written a plan', () => {
    expect(planView(activity({}), ctx)).toBeNull();
  });

  it('shows the current step and live sources while the run works', () => {
    const view = planView(
      activity({
        todos: [
          { content: 'Leer', status: 'completed' },
          { content: 'Comparar', status: 'in_progress' },
          { content: 'Concluir', status: 'pending' },
        ],
        sources: [
          { index: 1, title: 'A', url: null, kind: 'kb', ref: null },
          { index: 2, title: 'B', url: null, kind: 'kb', ref: null },
        ],
      }),
      ctx,
    );
    expect(view).toMatchObject({
      running: true,
      headline: 'agent.plan.running{"step":2,"total":3}',
      liveSources: 'agent.sources.live{"count":2}',
      steps: [
        { content: 'Leer', status: 'completed', statusLabel: 'agent.plan.status.completed' },
        { content: 'Comparar', status: 'in_progress', statusLabel: 'agent.plan.status.inProgress' },
        { content: 'Concluir', status: 'pending', statusLabel: 'agent.plan.status.pending' },
      ],
    });
  });

  it('folds into a one-line summary with the run time once it has finished', () => {
    const view = planView(
      activity({
        status: 'completed',
        todos: [{ content: 'Leer', status: 'completed' }],
        startedAt: 1_000,
        finishedAt: 49_000,
        sources: [],
      }),
      ctx,
    );
    expect(view?.running).toBe(false);
    expect(view?.liveSources).toBeNull();
    expect(view?.headline).toBe('agent.plan.label');
    expect(view?.summary).toBe(
      'agent.plan.summary{"steps":"agent.plan.stepCount{\\"count\\":1}","sources":"agent.sources.live{\\"count\\":0}","seconds":"agent.plan.seconds{\\"seconds\\":\\"48\\"}"}',
    );
  });

  it('drops the time from the summary when it is not known', () => {
    const view = planView(
      activity({
        status: 'failed',
        todos: [{ content: 'Leer', status: 'pending' }],
        finishedAt: null,
      }),
      ctx,
    );
    expect(view?.summary).toContain('agent.plan.summaryNoTime');
  });
});

describe('subagentName', () => {
  it('translates the two known subagents and shows any other name as sent', () => {
    expect(subagentName('investigador', t)).toBe('agent.subagents.researcher');
    expect(subagentName('critico', t)).toBe('agent.subagents.critic');
    expect(subagentName('custom', t)).toBe('custom');
  });
});

describe('sources', () => {
  it('names a web source by its host and a team document by where it lives', () => {
    expect(sourceMeta({ index: 1, title: 'X', url: 'https://www.docs.dev/a' }, t)).toBe('docs.dev');
    expect(sourceMeta({ index: 2, title: 'Y', url: null, kind: 'kb' }, t)).toBe(
      'agent.sources.teamDocument',
    );
    expect(sourceMeta({ index: 3, title: 'Z', url: null, kind: 'attachment' }, t)).toBe(
      'agent.sources.attachment',
    );
  });

  it('orders sources by index and keeps an untitled one readable', () => {
    const citations: Citation[] = [
      { index: 2, title: '  ', url: null, kind: 'kb', snippet: 'Fragmento' },
      { index: 1, title: 'Guía', url: 'https://example.com/guia' },
    ];
    const views = sourceViews(citations, ctx);
    expect(views.map((view) => view.index)).toEqual([1, 2]);
    expect(views[0]?.meta).toBe('example.com');
    expect(views[1]).toMatchObject({ title: 'agent.sources.untitled', snippet: 'Fragmento' });
  });
});

describe('toolRunViews', () => {
  it('groups each run by agent, main agent first, and names the run after its question', () => {
    const messages = [
      message('u1', 'user', '¿Cómo se despliega un servicio aquí?'),
      message('a1', 'assistant', 'respuesta'),
    ];
    const runs = toolRunViews(
      messages,
      {
        a1: activity({
          runId: 'run-1',
          tools: [
            {
              id: 't1',
              name: 'task',
              agent: 'main',
              argsPreview: '{"description":"x"}',
              status: 'success',
              resultPreview: null,
              durationMs: 1_250,
            },
            {
              id: 't2',
              name: 'web_search',
              agent: 'investigador',
              argsPreview: 'query',
              status: 'running',
              resultPreview: null,
              durationMs: null,
            },
          ],
        }),
      },
      ctx,
    );
    expect(runs).toHaveLength(1);
    expect(runs[0]?.title).toBe('¿Cómo se despliega un servicio aquí?');
    expect(runs[0]?.groups.map((group) => [group.key, group.label, group.main])).toEqual([
      ['main', 'agent.tools.mainAgent', true],
      ['investigador', 'agent.subagents.researcher', false],
    ]);
    expect(runs[0]?.groups[0]?.rows[0]).toMatchObject({
      name: 'agent.tools.names.task',
      statusLabel: 'panel.toolCalls.statusSuccess',
      durationLabel: 'agent.plan.seconds{"seconds":"1.3"}',
    });
    expect(runs[0]?.groups[1]?.rows[0]?.durationLabel).toBe('agent.tools.running');
  });

  it('skips assistant messages whose run made no tool calls', () => {
    const runs = toolRunViews(
      [message('u1', 'user', 'hola'), message('a1', 'assistant', 'hola')],
      { a1: activity({ runId: 'run-1' }) },
      ctx,
    );
    expect(runs).toEqual([]);
  });
});

describe('agentFileViews and formatSize', () => {
  it('names each file by its last path segment and sizes it', () => {
    expect(basename('/notes/informe.md')).toBe('informe.md');
    expect(agentFileViews([{ path: '/notes/a/b.md', size: 2048 }], ctx)).toEqual([
      { path: '/notes/a/b.md', name: 'b.md', sizeLabel: '2 KB' },
    ]);
  });

  it('chooses the unit by size', () => {
    expect(formatSize(512, 'en')).toBe('512 B');
    expect(formatSize(5 * 1024, 'en')).toBe('5 KB');
    expect(formatSize(3 * 1024 * 1024, 'en')).toBe('3 MB');
  });
});
