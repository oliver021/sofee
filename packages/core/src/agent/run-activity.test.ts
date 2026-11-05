import { describe, expect, it } from 'vitest';
import { applyRunEvent, createRunActivity, type RunActivity } from './run-activity.js';
import type { RunEvent } from './run-events.js';

const AT = 1_000;

function fold(events: RunEvent[], start: RunActivity = createRunActivity('run-1')): RunActivity {
  return events.reduce((activity, event) => applyRunEvent(activity, event, AT), start);
}

describe('createRunActivity', () => {
  it('starts queued with nothing recorded', () => {
    const activity = createRunActivity('run-1');
    expect(activity).toMatchObject({
      runId: 'run-1',
      status: 'queued',
      statusText: '',
      statusKey: '',
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
      startedAt: null,
      finishedAt: null,
    });
  });
});

describe('applyRunEvent — lifecycle', () => {
  it('run.started moves to running and stamps the start time once', () => {
    const started = applyRunEvent(
      createRunActivity('run-1'),
      {
        type: 'run.started',
        payload: {
          run_id: 'run-1',
          assistant_message_id: 'msg-1',
          mode: 'research',
          model_label: 'Sofee Pro',
        },
      },
      AT,
    );
    expect(started.status).toBe('running');
    expect(started.startedAt).toBe(AT);

    const again = applyRunEvent(
      started,
      {
        type: 'run.started',
        payload: {
          run_id: 'run-1',
          assistant_message_id: 'msg-1',
          mode: 'research',
          model_label: 'x',
        },
      },
      AT + 500,
    );
    expect(again.startedAt).toBe(AT);
  });

  it('run.completed finishes with no error and clears the status text', () => {
    const done = fold([
      { type: 'status', payload: { text: 'Buscando…' } },
      {
        type: 'run.completed',
        payload: { assistant_message_id: 'msg-1', text: 'Listo', citations: [] },
      },
    ]);
    expect(done.status).toBe('completed');
    expect(done.statusText).toBe('');
    expect(done.finishedAt).toBe(AT);
    expect(done.error).toBeNull();
  });

  it('run.failed records the error code, message and retryable flag', () => {
    const failed = fold([
      {
        type: 'run.failed',
        payload: { error_code: 'provider_error', message: 'upstream 502', retryable: true },
      },
    ]);
    expect(failed.status).toBe('failed');
    expect(failed.error).toEqual({
      code: 'provider_error',
      message: 'upstream 502',
      retryable: true,
    });
    expect(failed.finishedAt).toBe(AT);
  });

  it('run.cancelled marks the run cancelled and keeps the finish time', () => {
    const cancelled = fold([
      { type: 'run.cancelled', payload: { assistant_message_id: 'msg-1', text: 'parcial' } },
    ]);
    expect(cancelled.status).toBe('cancelled');
    expect(cancelled.finishedAt).toBe(AT);
    const later = applyRunEvent(
      cancelled,
      { type: 'run.cancelled', payload: { assistant_message_id: 'msg-1', text: '' } },
      AT + 9,
    );
    expect(later.finishedAt).toBe(AT);
  });
});

describe('applyRunEvent — progress', () => {
  it('message.delta returns the same object once the run is already running', () => {
    const running = fold([
      {
        type: 'run.started',
        payload: { run_id: 'r', assistant_message_id: 'm', mode: 'learn', model_label: 'x' },
      },
    ]);
    expect(applyRunEvent(running, { type: 'message.delta', payload: { text: 'hola' } })).toBe(
      running,
    );
  });

  it('message.delta moves a queued run to running without touching its text', () => {
    const next = applyRunEvent(createRunActivity('r'), {
      type: 'message.delta',
      payload: { text: 'hola' },
    });
    expect(next.status).toBe('running');
  });

  it('status sets the status text', () => {
    const next = fold([{ type: 'status', payload: { text: 'Leyendo deploy.md…' } }]);
    expect(next.statusText).toBe('Leyendo deploy.md…');
    expect(next.statusKey).toBe('');
  });

  it('status keeps the key the server sent so the interface can translate it', () => {
    const next = fold([
      { type: 'status', payload: { text: 'Buscando en la web', key: 'searching_web' } },
    ]);
    expect(next.statusKey).toBe('searching_web');
  });

  it('todos.updated replaces the plan', () => {
    const next = fold([
      {
        type: 'todos.updated',
        payload: {
          items: [
            { content: 'Buscar fuentes', status: 'in_progress' },
            { content: 'Redactar', status: 'pending' },
          ],
        },
      },
      {
        type: 'todos.updated',
        payload: { items: [{ content: 'Buscar fuentes', status: 'completed' }] },
      },
    ]);
    expect(next.todos).toEqual([{ content: 'Buscar fuentes', status: 'completed' }]);
  });

  it('usage stores run totals and the context percentage', () => {
    const next = fold([
      { type: 'usage', payload: { input_tokens: 1200, output_tokens: 300, context_percent: 9.5 } },
    ]);
    expect(next.usage).toEqual({ inputTokens: 1200, outputTokens: 300, contextPercent: 9.5 });
  });

  it('usage keeps a null context percentage when the model has no window', () => {
    const next = fold([
      { type: 'usage', payload: { input_tokens: 1, output_tokens: 1, context_percent: null } },
    ]);
    expect(next.usage?.contextPercent).toBeNull();
  });

  it('ui.directions and ui.quiz replace the previous suggestions', () => {
    const next = fold([
      { type: 'ui.directions', payload: { items: [{ title: 'A', why: 'a' }] } },
      {
        type: 'ui.directions',
        payload: {
          items: [
            { title: 'B', why: 'b' },
            { title: 'C', why: 'c' },
          ],
        },
      },
      { type: 'ui.quiz', payload: { items: [{ question: 'Q?', answer: 'A.' }] } },
    ]);
    expect(next.directions).toEqual([
      { title: 'B', why: 'b' },
      { title: 'C', why: 'c' },
    ]);
    expect(next.quiz).toEqual([{ question: 'Q?', answer: 'A.' }]);
  });
});

describe('applyRunEvent — tools', () => {
  it('tool.started records a running call', () => {
    const next = fold([
      {
        type: 'tool.started',
        payload: {
          id: 'call-1',
          name: 'search_team_docs',
          agent: 'main',
          args_preview: 'query=deploy',
        },
      },
    ]);
    expect(next.tools).toEqual([
      {
        id: 'call-1',
        name: 'search_team_docs',
        agent: 'main',
        argsPreview: 'query=deploy',
        status: 'running',
        resultPreview: null,
        durationMs: null,
      },
    ]);
  });

  it('tool.finished completes the matching call and keeps its arguments', () => {
    const next = fold([
      {
        type: 'tool.started',
        payload: { id: 'call-1', name: 'read_file', agent: 'main', args_preview: 'path=/kb/a.md' },
      },
      {
        type: 'tool.started',
        payload: { id: 'call-2', name: 'ls', agent: 'main', args_preview: '' },
      },
      {
        type: 'tool.finished',
        payload: {
          id: 'call-1',
          name: 'read_file',
          agent: 'main',
          status: 'success',
          result_preview: 'contenido',
          duration_ms: 42,
        },
      },
    ]);
    expect(next.tools).toHaveLength(2);
    expect(next.tools[0]).toMatchObject({
      id: 'call-1',
      status: 'success',
      argsPreview: 'path=/kb/a.md',
      resultPreview: 'contenido',
      durationMs: 42,
    });
    expect(next.tools[1]?.status).toBe('running');
  });

  it('tool.finished without a matching start still records the call', () => {
    const next = fold([
      {
        type: 'tool.finished',
        payload: {
          id: 'call-9',
          name: 'web_search',
          agent: 'investigador',
          status: 'error',
          result_preview: 'timeout',
          duration_ms: 900,
        },
      },
    ]);
    expect(next.tools).toEqual([
      {
        id: 'call-9',
        name: 'web_search',
        agent: 'investigador',
        argsPreview: '',
        status: 'error',
        resultPreview: 'timeout',
        durationMs: 900,
      },
    ]);
  });
});

describe('applyRunEvent — subagents, sources and files', () => {
  it('subagent.started then subagent.finished keep the task and add the summary', () => {
    const next = fold([
      {
        type: 'subagent.started',
        payload: { id: 'sub-1', name: 'investigador', task: 'Buscar la versión' },
      },
      {
        type: 'subagent.finished',
        payload: { id: 'sub-1', name: 'investigador', status: 'success', summary: 'Tres fuentes' },
      },
    ]);
    expect(next.subagents).toEqual([
      {
        id: 'sub-1',
        name: 'investigador',
        task: 'Buscar la versión',
        status: 'success',
        summary: 'Tres fuentes',
      },
    ]);
  });

  it('subagent.finished without a start still records the subagent', () => {
    const next = fold([
      {
        type: 'subagent.finished',
        payload: { id: 'sub-2', name: 'critico', status: 'error', summary: 'sin borrador' },
      },
    ]);
    expect(next.subagents[0]).toEqual({
      id: 'sub-2',
      name: 'critico',
      task: '',
      status: 'error',
      summary: 'sin borrador',
    });
  });

  it('source.added is keyed by index, so a repeated index replaces the source', () => {
    const next = fold([
      {
        type: 'source.added',
        payload: { index: 1, title: 'Guía', url: null, kind: 'kb', ref: 'doc-1' },
      },
      {
        type: 'source.added',
        payload: { index: 2, title: 'Blog', url: 'https://example.com/b', kind: 'web', ref: null },
      },
      {
        type: 'source.added',
        payload: { index: 1, title: 'Guía v2', url: null, kind: 'kb', ref: 'doc-1' },
      },
    ]);
    expect(next.sources.map((s) => [s.index, s.title])).toEqual([
      [1, 'Guía v2'],
      [2, 'Blog'],
    ]);
  });

  it('file.written is keyed by path and keeps the latest size', () => {
    const next = fold([
      { type: 'file.written', payload: { path: '/notes/informe.md', size: 100 } },
      { type: 'file.written', payload: { path: '/notes/informe.md', size: 480 } },
      { type: 'file.written', payload: { path: '/notes/plan.md', size: null } },
    ]);
    expect(next.files).toEqual([
      { path: '/notes/informe.md', size: 480 },
      { path: '/notes/plan.md', size: null },
    ]);
  });
});

describe('applyRunEvent — plan review interrupt', () => {
  const todos = [{ content: 'Comparar A y B', status: 'pending' as const }];

  it('interrupt pauses the run and exposes the plan for review', () => {
    const paused = fold([
      { type: 'interrupt', payload: { interrupt_id: 'int-1', kind: 'plan_review', todos } },
    ]);
    expect(paused.status).toBe('interrupted');
    expect(paused.interrupt).toEqual({ interruptId: 'int-1', kind: 'plan_review', todos });
    expect(paused.todos).toEqual(todos);
  });

  it('any event after the pause means the answer was taken and the run is running again', () => {
    const resumed = fold([
      { type: 'interrupt', payload: { interrupt_id: 'int-1', kind: 'plan_review', todos } },
      { type: 'status', payload: { text: 'Investigando…' } },
    ]);
    expect(resumed.status).toBe('running');
    expect(resumed.interrupt).toBeNull();
  });
});

describe('applyRunEvent — purity', () => {
  it('never mutates the activity it was given', () => {
    const before = fold([
      { type: 'tool.started', payload: { id: 'c', name: 'n', agent: 'main', args_preview: '' } },
    ]);
    const snapshot = JSON.stringify(before);
    applyRunEvent(before, {
      type: 'tool.finished',
      payload: {
        id: 'c',
        name: 'n',
        agent: 'main',
        status: 'success',
        result_preview: 'ok',
        duration_ms: 1,
      },
    });
    expect(JSON.stringify(before)).toBe(snapshot);
  });
});
