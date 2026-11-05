import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RunEvent, Thread } from '@sofee/core';
import { ApiError } from './api.js';
import { appState } from './app-state.svelte.js';

// The run client is replaced with fakes: no network, and the event streams are driven by the tests.
const runClient = vi.hoisted(() => ({
  createRun: vi.fn(),
  cancelRun: vi.fn(),
  subscribeToRun: vi.fn(),
  listRuns: vi.fn(),
  getLatestRun: vi.fn(),
  compactThread: vi.fn(),
  clearThreadContext: vi.fn(),
  resumeRun: vi.fn(),
}));

vi.mock('./run-client.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./run-client.js')>()),
  ...runClient,
}));

// The agent's REST helpers and the thread's cut state are faked too, for the same reason.
const agentData = vi.hoisted(() => ({
  fetchStarters: vi.fn(),
  listAgentFiles: vi.fn(),
  readAgentFile: vi.fn(),
  putFeedback: vi.fn(),
}));
const backendData = vi.hoisted(() => ({ loadThreadCutState: vi.fn() }));
vi.mock('./agent-data.js', () => agentData);
vi.mock('./backend.svelte.js', () => backendData);
vi.mock('./assistant-mode.js', () => ({ isMockAssistant: false }));
vi.mock('./models.svelte.js', () => ({ models: { selectedId: 'sofee-pro' } }));
vi.mock('./i18n.svelte.js', () => ({ t: (path: string) => path, getLocale: () => 'es' }));

interface Subscription {
  readonly runId: string;
  readonly after: number;
  readonly onEvent: (seq: number, event: RunEvent) => void;
  readonly onClosed: () => void;
}

let subscriptions: Subscription[] = [];

/** Delivers an event on the most recent stream for a run, as the EventSource would. */
function emit(runId: string, seq: number, event: RunEvent): void {
  const sub = [...subscriptions].reverse().find((s) => s.runId === runId);
  if (!sub) throw new Error(`no stream for ${runId}`);
  sub.onEvent(seq, event);
}

/** Lets queued frames (the one-frame text flush) and pending promises run. */
function settle(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 10));
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function threadWith(id: string, messages: Thread['messages']): Thread {
  return { id, title: '', isTemporary: false, createdAt: 0, messages, mode: 'learn' };
}

beforeEach(() => {
  vi.clearAllMocks();
  agentData.fetchStarters.mockResolvedValue([]);
  agentData.listAgentFiles.mockResolvedValue([]);
  agentData.putFeedback.mockResolvedValue(undefined);
  backendData.loadThreadCutState.mockResolvedValue({
    seqs: {},
    summaryThroughSeq: null,
    contextStartSeq: null,
  });
  runClient.resumeRun.mockResolvedValue(undefined);
  subscriptions = [];
  globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) =>
    setTimeout(() => cb(0), 0)) as unknown as typeof requestAnimationFrame;
  globalThis.cancelAnimationFrame = ((id: number) =>
    clearTimeout(id)) as unknown as typeof cancelAnimationFrame;
  runClient.subscribeToRun.mockImplementation(
    (runId: string, after: number, onEvent: Subscription['onEvent'], onClosed: () => void) => {
      subscriptions.push({ runId, after, onEvent, onClosed });
      return { close: vi.fn() };
    },
  );
  runClient.cancelRun.mockResolvedValue(undefined);
  appState.setPersistence({
    threadChanged: () => undefined,
    messageChanged: () => undefined,
    messageRemoved: () => undefined,
    threadSettled: async () => undefined,
  });
  appState.reset();
});

describe('agent send', () => {
  it('creates the run, streams the reply in, and completes it with its citations', async () => {
    runClient.createRun.mockResolvedValue({
      run_id: 'run-1',
      assistant_message_id: 'x',
      status: 'queued',
    });
    const threadId = appState.activeThread.id;

    const user = appState.sendMessage(threadId, '¿Qué es un deploy?', []);
    await settle();

    expect(runClient.createRun).toHaveBeenCalledWith(
      threadId,
      expect.objectContaining({
        kind: 'send',
        mode: 'learn',
        model_slug: 'sofee-pro',
        user_message: expect.objectContaining({ client_id: user?.id, text: '¿Qué es un deploy?' }),
      }),
    );
    const [userMessage, reply] = appState.activeThread.messages;
    expect(userMessage?.status).toBe('complete');
    expect(reply?.role).toBe('assistant');
    expect(appState.activityByMessage[reply?.id ?? '']?.runId).toBe('run-1');
    expect(subscriptions[0]).toMatchObject({ runId: 'run-1', after: 0 });

    emit('run-1', 1, {
      type: 'run.started',
      payload: {
        run_id: 'run-1',
        assistant_message_id: reply?.id ?? '',
        mode: 'learn',
        model_label: 'Sofee Pro',
      },
    });
    emit('run-1', 2, { type: 'message.delta', payload: { text: 'Un ' } });
    emit('run-1', 3, { type: 'message.delta', payload: { text: 'deploy.' } });
    await settle();
    expect(reply?.text).toBe('Un deploy.');
    expect(reply?.status).toBe('streaming');

    emit('run-1', 4, {
      type: 'run.completed',
      payload: {
        assistant_message_id: reply?.id ?? '',
        text: 'Un deploy es una publicación [1].',
        citations: [
          {
            index: 1,
            title: 'Guía',
            url: 'https://example.com/g',
            kind: 'web',
            snippet: null,
            ref: null,
          },
        ],
      },
    });
    expect(reply?.status).toBe('complete');
    expect(reply?.text).toBe('Un deploy es una publicación [1].');
    expect(reply?.citations).toHaveLength(1);
    expect(appState.activityByMessage[reply?.id ?? '']?.status).toBe('completed');
  });

  it('upserts a thread that was only hydrated locally before naming it in the run', async () => {
    runClient.createRun.mockResolvedValue({
      run_id: 'run-1',
      assistant_message_id: 'x',
      status: 'queued',
    });
    const threadChanged = vi.fn();
    appState.setPersistence({
      threadChanged,
      messageChanged: () => undefined,
      messageRemoved: () => undefined,
      threadSettled: async () => undefined,
    });
    // A fresh account has no conversations: the empty canvas is created without being persisted.
    appState.hydrateThreads([]);
    const thread = appState.activeThread;
    expect(threadChanged).not.toHaveBeenCalled();

    appState.sendMessage(thread.id, 'Hola', []);
    await settle();

    expect(threadChanged).toHaveBeenCalledWith(expect.objectContaining({ id: thread.id }));
    expect(runClient.createRun).toHaveBeenCalled();
  });

  it('removes the reply and marks the user message with the quota reset when the run is refused', async () => {
    runClient.createRun.mockRejectedValue(
      new ApiError(429, 'quota_exceeded', {
        detail: 'quota_exceeded',
        reset_at: '2026-10-30T00:00:00+00:00',
      }),
    );
    const threadId = appState.activeThread.id;

    appState.sendMessage(threadId, 'Hola', []);
    await settle();

    const messages = appState.activeThread.messages;
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      role: 'user',
      status: 'error',
      errorCode: 'quota_exceeded',
      errorResetAt: '2026-10-30T00:00:00+00:00',
    });
    expect(subscriptions).toHaveLength(0);
  });

  it('retries a refused send by sending it again with a fresh reply', async () => {
    runClient.createRun.mockRejectedValueOnce(new ApiError(503, 'agent_disabled'));
    runClient.createRun.mockResolvedValueOnce({
      run_id: 'run-9',
      assistant_message_id: 'y',
      status: 'queued',
    });
    const threadId = appState.activeThread.id;

    const user = appState.sendMessage(threadId, 'Otra vez', []);
    await settle();
    expect(appState.activeThread.messages[0]?.errorCode).toBe('agent_disabled');

    appState.retryMessage(threadId, user?.id ?? '');
    await settle();
    expect(runClient.createRun).toHaveBeenLastCalledWith(
      threadId,
      expect.objectContaining({
        kind: 'send',
        user_message: expect.objectContaining({ client_id: user?.id }),
      }),
    );
    expect(appState.activeThread.messages[0]?.status).toBe('complete');
    expect(appState.activeThread.messages[1]?.role).toBe('assistant');
  });

  it('keeps the partial reply and records the error code when a run fails mid-stream', async () => {
    runClient.createRun.mockResolvedValue({
      run_id: 'run-4',
      assistant_message_id: 'z',
      status: 'queued',
    });
    appState.sendMessage(appState.activeThread.id, 'Pregunta', []);
    await settle();
    const reply = appState.activeThread.messages[1];

    emit('run-4', 1, { type: 'message.delta', payload: { text: 'Parcial' } });
    await settle();
    emit('run-4', 2, {
      type: 'run.failed',
      payload: { error_code: 'provider_error', message: 'upstream', retryable: true },
    });

    expect(reply).toMatchObject({ status: 'error', errorCode: 'provider_error', text: 'Parcial' });
    expect(appState.activityByMessage[reply?.id ?? '']?.error?.retryable).toBe(true);
  });

  it('stops a reply whose run id is still on its way, as soon as the id arrives', async () => {
    const created = deferred<{ run_id: string; assistant_message_id: string; status: string }>();
    runClient.createRun.mockReturnValue(created.promise);
    const threadId = appState.activeThread.id;

    appState.sendMessage(threadId, 'Rápido', []);
    await settle();
    appState.stopStreaming(threadId);
    expect(runClient.cancelRun).not.toHaveBeenCalled();

    created.resolve({ run_id: 'run-5', assistant_message_id: 'w', status: 'queued' });
    await settle();
    expect(runClient.cancelRun).toHaveBeenCalledWith('run-5');
  });
});

describe('regenerate and reattach', () => {
  it('clears the old reply only once the server has accepted the regeneration', async () => {
    const threadId = appState.activeThread.id;
    const pending = deferred<{ run_id: string; assistant_message_id: string; status: string }>();
    runClient.createRun.mockReturnValue(pending.promise);
    appState.hydrateThreads([
      threadWith(threadId, [
        { id: 'u1', role: 'user', status: 'complete', text: 'Pregunta', createdAt: 0 },
        { id: 'a1', role: 'assistant', status: 'complete', text: 'Viejo', createdAt: 0 },
      ]),
    ]);

    appState.regenerate(threadId, 'a1');
    await settle();
    expect(appState.activeThread.messages[1]?.text).toBe('Viejo');

    pending.resolve({ run_id: 'run-6', assistant_message_id: 'a1', status: 'queued' });
    await settle();
    expect(appState.activeThread.messages[1]?.text).toBe('');
    expect(runClient.createRun).toHaveBeenCalledWith(
      threadId,
      expect.objectContaining({ kind: 'regenerate', assistant_client_id: 'a1' }),
    );

    emit('run-6', 1, { type: 'message.delta', payload: { text: 'Nuevo' } });
    await settle();
    expect(appState.activeThread.messages[1]?.text).toBe('Nuevo');
  });

  it('reattaches to a run that is still going and does not repeat the text already stored', async () => {
    const threadId = 'thread-reload';
    appState.hydrateThreads([
      threadWith(threadId, [
        { id: 'u2', role: 'user', status: 'complete', text: 'Hola', createdAt: 0 },
        // The server had flushed only "Hol" when the page reloaded.
        { id: 'a2', role: 'assistant', status: 'streaming', text: 'Hol', createdAt: 0 },
      ]),
    ]);
    runClient.listRuns.mockResolvedValue([
      {
        run_id: 'run-7',
        assistant_message_id: 'a2',
        status: 'running',
        mode: 'learn',
        started_at: null,
        finished_at: null,
        events: [
          {
            seq: 1,
            type: 'run.started',
            payload: {
              run_id: 'run-7',
              assistant_message_id: 'a2',
              mode: 'learn',
              model_label: 'x',
            },
          },
        ],
      },
    ]);
    runClient.getLatestRun.mockResolvedValue({
      run_id: 'run-7',
      assistant_message_id: 'a2',
      status: 'running',
      mode: 'learn',
      started_at: null,
      finished_at: null,
    });

    await appState.loadRuns(threadId);
    expect(subscriptions[0]).toMatchObject({ runId: 'run-7', after: 0 });
    expect(appState.activityByMessage.a2?.status).toBe('running');

    emit('run-7', 2, { type: 'message.delta', payload: { text: 'Hola ' } });
    emit('run-7', 3, { type: 'message.delta', payload: { text: 'mundo' } });
    await settle();
    expect(appState.activeThread.messages[1]?.text).toBe('Hola mundo');
  });

  it('hydrates a finished run from its stored events and records a failure on the reply', async () => {
    const threadId = 'thread-history';
    appState.hydrateThreads([
      threadWith(threadId, [
        { id: 'u3', role: 'user', status: 'complete', text: 'Pregunta', createdAt: 0 },
        { id: 'a3', role: 'assistant', status: 'error', text: 'Medio', createdAt: 0 },
      ]),
    ]);
    runClient.listRuns.mockResolvedValue([
      {
        run_id: 'run-8',
        assistant_message_id: 'a3',
        status: 'failed',
        mode: 'learn',
        started_at: '2026-10-29T10:00:00+00:00',
        finished_at: '2026-10-29T10:00:05+00:00',
        events: [
          {
            seq: 1,
            type: 'tool.started',
            payload: { id: 'c1', name: 'search_team_docs', agent: 'main', args_preview: 'q' },
          },
          {
            seq: 2,
            type: 'run.failed',
            payload: { error_code: 'model_unavailable', message: 'x', retryable: false },
          },
        ],
      },
    ]);
    runClient.getLatestRun.mockResolvedValue(undefined);

    await appState.loadRuns(threadId);

    const activity = appState.activityByMessage.a3;
    expect(activity?.status).toBe('failed');
    expect(activity?.tools.map((tool) => tool.name)).toEqual(['search_team_docs']);
    expect(appState.activeThread.messages[1]?.errorCode).toBe('model_unavailable');
    expect(subscriptions).toHaveLength(0);
  });
});

describe('sources, context and the tool calls panel', () => {
  it('resolves [n] markers against the sources reported so far while the reply streams', async () => {
    runClient.createRun.mockResolvedValue({
      run_id: 'run-10',
      assistant_message_id: 'v',
      status: 'queued',
    });
    appState.sendMessage(appState.activeThread.id, 'Fuentes', []);
    await settle();
    const reply = appState.activeThread.messages[1];
    if (!reply) throw new Error('expected a reply');

    emit('run-10', 1, {
      type: 'source.added',
      payload: { index: 1, title: 'Manual', url: null, kind: 'kb', ref: 'doc-1' },
    });
    expect(appState.citationsFor(reply)).toEqual([
      { index: 1, title: 'Manual', url: null, kind: 'kb', ref: 'doc-1' },
    ]);
  });

  it('reads the meter from the last usage event and empties it when the context is cleared', async () => {
    runClient.createRun.mockResolvedValue({
      run_id: 'run-11',
      assistant_message_id: 'u',
      status: 'queued',
    });
    const threadId = appState.activeThread.id;
    appState.sendMessage(threadId, 'Medidor', []);
    await settle();

    emit('run-11', 1, {
      type: 'usage',
      payload: { input_tokens: 900, output_tokens: 50, context_percent: 40 },
    });
    expect(appState.contextPercent).toBe(40);

    runClient.clearThreadContext.mockResolvedValue({ context_start_seq: 3 });
    await appState.clearContext(threadId);
    expect(runClient.clearThreadContext).toHaveBeenCalledWith(threadId);
    expect(appState.contextPercent).toBe(0);
  });

  it('keeps the meter and announces the failure when compacting fails', async () => {
    runClient.createRun.mockResolvedValue({
      run_id: 'run-12',
      assistant_message_id: 't',
      status: 'queued',
    });
    const threadId = appState.activeThread.id;
    appState.sendMessage(threadId, 'Compacto', []);
    await settle();
    emit('run-12', 1, {
      type: 'usage',
      payload: { input_tokens: 500, output_tokens: 5, context_percent: 12 },
    });

    runClient.compactThread.mockRejectedValue(new ApiError(502, 'summary_failed'));
    await appState.compactContext(threadId);

    expect(appState.contextPercent).toBe(12);
    expect(appState.liveMessage).toBe('thread.contextFailed');
  });

  it('lists the tool calls of the active thread from its replies', async () => {
    runClient.createRun.mockResolvedValue({
      run_id: 'run-13',
      assistant_message_id: 's',
      status: 'queued',
    });
    appState.sendMessage(appState.activeThread.id, 'Herramientas', []);
    await settle();
    emit('run-13', 1, {
      type: 'tool.started',
      payload: { id: 'call-a', name: 'read_file', agent: 'main', args_preview: '' },
    });
    expect(appState.toolCalls).toEqual([{ id: 'call-a', name: 'read_file', status: 'running' }]);

    emit('run-13', 2, {
      type: 'tool.finished',
      payload: {
        id: 'call-a',
        name: 'read_file',
        agent: 'main',
        status: 'success',
        result_preview: '',
        duration_ms: 3,
      },
    });
    expect(appState.toolCalls[0]?.status).toBe('success');
  });
});

/** Starts a run with one reply in the active thread, and returns the ids the tests need. */
async function startRun(runId: string): Promise<{ threadId: string; replyId: string }> {
  runClient.createRun.mockResolvedValue({
    run_id: runId,
    assistant_message_id: 'x',
    status: 'queued',
  });
  const threadId = appState.activeThread.id;
  appState.sendMessage(threadId, 'Pregunta de prueba', []);
  await settle();
  const reply = appState.activeThread.messages.find((m) => m.role === 'assistant');
  return { threadId, replyId: reply?.id ?? '' };
}

describe('plan review, announcements and feedback', () => {
  it('announces a finished step politely and says when the run waits for review', async () => {
    await startRun('run-20');
    appState.liveMessage = '';
    emit('run-20', 1, {
      type: 'todos.updated',
      payload: {
        items: [
          { content: 'Leer', status: 'in_progress' },
          { content: 'Comparar', status: 'pending' },
        ],
      },
    });
    expect(appState.liveMessage).toBe('');
    emit('run-20', 2, {
      type: 'todos.updated',
      payload: {
        items: [
          { content: 'Leer', status: 'completed' },
          { content: 'Comparar', status: 'pending' },
        ],
      },
    });
    expect(appState.liveMessage).toBe('agent.announce.stepCompleted');

    emit('run-20', 3, {
      type: 'interrupt',
      payload: {
        interrupt_id: 'i-1',
        kind: 'plan_review',
        todos: [{ content: 'Leer', status: 'pending' }],
      },
    });
    expect(appState.liveMessage).toBe('agent.review.waiting');
    expect(appState.waitingReviewMessageId).not.toBeNull();
  });

  it('approves a waiting plan and resumes the run as running', async () => {
    const { replyId } = await startRun('run-21');
    emit('run-21', 1, {
      type: 'interrupt',
      payload: { interrupt_id: 'i-2', kind: 'plan_review', todos: [] },
    });

    await appState.approvePlan(replyId);

    expect(runClient.resumeRun).toHaveBeenCalledWith('run-21', 'approve', null);
    expect(appState.activityByMessage[replyId]?.status).toBe('running');
    expect(appState.waitingReviewMessageId).toBeNull();
  });

  it('sends the edited steps and refuses to send an empty plan', async () => {
    const { replyId } = await startRun('run-22');
    emit('run-22', 1, {
      type: 'interrupt',
      payload: { interrupt_id: 'i-3', kind: 'plan_review', todos: [] },
    });

    await appState.editPlan(replyId, ['  ', '']);
    expect(runClient.resumeRun).not.toHaveBeenCalled();

    await appState.editPlan(replyId, [' Leer la guía ', 'Comparar']);
    expect(runClient.resumeRun).toHaveBeenCalledWith('run-22', 'edit', [
      { content: 'Leer la guía', status: 'pending' },
      { content: 'Comparar', status: 'pending' },
    ]);
  });

  it('keeps the card and says so when the server refuses the answer', async () => {
    const { replyId } = await startRun('run-23');
    emit('run-23', 1, {
      type: 'interrupt',
      payload: { interrupt_id: 'i-4', kind: 'plan_review', todos: [] },
    });
    runClient.resumeRun.mockRejectedValue(new ApiError(409, 'not_interrupted'));

    await appState.approvePlan(replyId);

    expect(appState.liveMessage).toBe('agent.review.failed');
    expect(appState.activityByMessage[replyId]?.status).toBe('interrupted');
  });

  it('approves this plan and every later plan in the thread without asking again', async () => {
    const { threadId, replyId } = await startRun('run-24');
    emit('run-24', 1, {
      type: 'interrupt',
      payload: { interrupt_id: 'i-5', kind: 'plan_review', todos: [] },
    });

    await appState.skipPlanReview(replyId);
    expect(runClient.resumeRun).toHaveBeenCalledWith('run-24', 'approve', null);
    expect(appState.skipsPlanReview(threadId)).toBe(true);

    // A later run in the same thread: its plan is approved as soon as it arrives.
    runClient.createRun.mockResolvedValue({
      run_id: 'run-25',
      assistant_message_id: 'y',
      status: 'queued',
    });
    appState.sendMessage(threadId, 'Otra pregunta', []);
    await settle();
    const nextReply = appState.activeThread.messages.at(-1);
    emit('run-25', 1, {
      type: 'interrupt',
      payload: { interrupt_id: 'i-6', kind: 'plan_review', todos: [] },
    });
    await settle();
    expect(runClient.resumeRun).toHaveBeenCalledWith('run-25', 'approve', null);
    expect(nextReply?.role).toBe('assistant');
  });

  it('saves a rating at once and puts it back when the save fails', async () => {
    const { threadId, replyId } = await startRun('run-26');
    emit('run-26', 1, {
      type: 'run.completed',
      payload: { assistant_message_id: 'x', text: 'ok', citations: [] },
    });

    appState.setFeedback(threadId, replyId, 'good');
    expect(appState.feedback[replyId]).toBe('good');
    expect(agentData.putFeedback).toHaveBeenCalledWith(threadId, replyId, 'good');

    agentData.putFeedback.mockRejectedValueOnce(new Error('offline'));
    appState.setFeedback(threadId, replyId, 'bad');
    await settle();
    expect(appState.feedback[replyId]).toBe('good');
    expect(appState.liveMessage).toBe('agent.feedback.failed');

    appState.setFeedback(threadId, replyId, 'good');
    expect(appState.feedback[replyId]).toBeUndefined();
    expect(agentData.putFeedback).toHaveBeenLastCalledWith(threadId, replyId, null);
  });
});

describe('context cut points, starters, agent files and sources', () => {
  it('reads each message seq and the cut points from the server after Compact', async () => {
    const { threadId, replyId } = await startRun('run-30');
    emit('run-30', 1, {
      type: 'run.completed',
      payload: { assistant_message_id: 'x', text: 'ok', citations: [] },
    });
    runClient.compactThread.mockResolvedValue({ summary_through_seq: 2 });
    backendData.loadThreadCutState.mockResolvedValue({
      seqs: { [appState.activeThread.messages[0]?.id ?? '']: 1, [replyId]: 2 },
      summaryThroughSeq: 2,
      contextStartSeq: null,
    });

    await appState.compactContext(threadId);

    expect(backendData.loadThreadCutState).toHaveBeenCalledWith(threadId);
    expect(appState.activeThread.summaryThroughSeq).toBe(2);
    expect(appState.activeThread.messages.find((m) => m.id === replyId)?.seq).toBe(2);
  });

  it("loads a mode's starting questions once, and falls back to none on failure", async () => {
    agentData.fetchStarters.mockResolvedValueOnce([{ text: 'Cómo se despliega?' }]);
    await appState.loadStarters('learn', 'es');
    await appState.loadStarters('learn', 'es');
    expect(agentData.fetchStarters).toHaveBeenCalledTimes(1);
    expect(appState.startersFor('learn', 'es')).toEqual(['Cómo se despliega?']);

    agentData.fetchStarters.mockRejectedValueOnce(new Error('down'));
    await appState.loadStarters('explore', 'es');
    expect(appState.startersFor('explore', 'es')).toEqual([]);
  });

  it('previews an agent file and drops the preview when it is closed', async () => {
    agentData.readAgentFile.mockResolvedValue({ path: '/notes/informe.md', content: '# Informe' });
    const threadId = appState.activeThread.id;

    const opening = appState.openAgentFile(threadId, '/notes/informe.md');
    expect(appState.filePreview).toMatchObject({ name: 'informe.md', loading: true });
    await opening;
    expect(appState.filePreview).toMatchObject({
      content: '# Informe',
      loading: false,
      error: false,
    });

    appState.closeAgentFile();
    expect(appState.filePreview).toBeNull();
  });

  it('opens the Attachments panel on the source a citation names', () => {
    const trigger = {} as HTMLElement;
    appState.showSource(
      { index: 1, title: 'Guía de despliegue', url: null, kind: 'kb', ref: 'doc-1' },
      trigger,
    );
    expect(appState.activePanel).toBe('attachments');
    expect(appState.focusedSource?.ref).toBe('doc-1');
    expect(appState.panelTriggerEl).toBe(trigger);
  });
});
