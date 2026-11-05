/**
 * The application's own state — everything packages/ui deliberately does not own (repo layout:
 * "packages/ui: Svelte components, no domain state"). One instance, created once in App.svelte.
 *
 * Two assistants run through this module. With `VITE_ASSISTANT=mock` (see assistant-mode.ts) the
 * reply is the simulated stream from packages/core: a made-up delay, an occasional failure so the
 * Error+Retry state is reachable, and canned text. Otherwise a reply is a server-side agent run
 * (roadmap §3.7): the client creates the run, subscribes to its event stream and folds each event
 * into the assistant message and into that message's RunActivity. The server writes the messages
 * in agent mode, so the persistence hooks only ever upsert threads there (roadmap §3.9).
 */
import {
  applyRunEvent,
  createId,
  createMockReply,
  createRunActivity,
  editedPlan,
  isActiveRunStatus,
  MockAssistantStream,
  newlyCompletedStep,
  ScrollController,
  ScrollMemoryStore,
  type AttachmentRecord,
  type ChatMessage,
  type Citation,
  type ComposerMode,
  type McpServerRecord,
  type Project,
  type RunActivity,
  type RunErrorCode,
  type RunEvent,
  type RunTodo,
  toRunEvent,
  type Thread,
  type ToolCallRecord,
} from '@sofee/core';
import { SvelteMap, SvelteSet } from 'svelte/reactivity';
import { ApiError } from './api.js';
import { isMockAssistant } from './assistant-mode.js';
import { getLocale, t } from './i18n.svelte.js';
import { models } from './models.svelte.js';
import { preferences } from './preferences.svelte.js';
import {
  cancelRun,
  clearThreadContext,
  compactThread,
  createRun,
  failureInfoOf,
  getLatestRun,
  listRuns,
  resumeRun,
  subscribeToRun,
  type CreateRunBody,
  type RunSubscription,
  type RunWithEvents,
} from './run-client.js';
import {
  fetchStarters,
  listAgentFiles,
  putFeedback,
  readAgentFile,
  type AgentFileRow,
} from './agent-data.js';
import { basename } from './agent-view.js';
import { loadThreadCutState } from './backend.svelte.js';

export type PanelId = 'chats' | 'projects' | 'toolCalls' | 'mcp' | 'attachments';
export type MoreMenuView = 'root' | 'language' | 'palette';

/**
 * The app shell owns *what* to persist (it has the auth-aware backend client); AppState owns
 * *when* something changed. These callbacks are that seam. They are deliberately no-ops until the
 * shell installs them after sign-in, so the whole state module keeps working standalone.
 */
export interface PersistenceHooks {
  threadChanged(thread: Thread): void;
  messageChanged(thread: Thread, message: ChatMessage): void;
  messageRemoved(threadId: string, messageId: string): void;
  /** Resolves once the thread's queued writes have reached the server; a run needs the thread there. */
  threadSettled(threadId: string): Promise<void>;
}

type Uploader = (file: File) => Promise<string>;

/** A made-up budget purely for the simulated context meter — there is no real token count
 * without a backend, so this stands in for one. Mock mode only. */
const CONTEXT_BUDGET_CHARS = 12000;
const SIMULATED_LATENCY_MS = 380;
const SIMULATED_FAILURE_RATE = 0.15;

/** One run this page is listening to, keyed by run id. */
interface RunSession {
  readonly runId: string;
  readonly threadId: string;
  readonly messageId: string;
  subscription: RunSubscription | null;
  /** Reattaching after a reload replays the whole run, but the message already holds the text
   * the server had flushed. This many leading characters of the replay are that text, and are
   * skipped as they arrive. */
  skip: number;
  /** The reply text so far, flushed to the message one animation frame at a time. */
  buffer: string;
  frame: number | null;
}

/** What a launch needs: the assistant placeholder, the run kind, and the user message for `send`. */
interface Launch {
  readonly threadId: string;
  readonly messageId: string;
  readonly kind: CreateRunBody['kind'];
  readonly userMessageId: string | null;
}

function createEmptyThread(isTemporary: boolean): Thread {
  return {
    id: createId('thread'),
    title: '',
    isTemporary,
    createdAt: Date.now(),
    messages: [],
    mode: preferences.values.defaultMode,
  };
}

/** The threads whose plan reviews are approved without asking ("Seguir sin revisar", roadmap U8).
 * Kept in this browser only: the server has no per-thread flag yet, so this is a per-viewer
 * convenience and reads as empty whenever storage is unavailable. */
const SKIPPED_REVIEWS_KEY = 'sofee:skipped-plan-reviews';
const MAX_SKIPPED_REVIEWS = 200;

function readSkippedPlanReviews(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(SKIPPED_REVIEWS_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
}

function writeSkippedPlanReviews(threadIds: readonly string[]): void {
  try {
    localStorage.setItem(
      SKIPPED_REVIEWS_KEY,
      JSON.stringify(threadIds.slice(-MAX_SKIPPED_REVIEWS)),
    );
  } catch {
    // Storage disabled: the choice lasts for this page only.
  }
}

/** A file the agent wrote, open in the Attachments panel (roadmap U10). `content` is null while it
 * loads and after a failure. */
export interface AgentFilePreview {
  readonly threadId: string;
  readonly path: string;
  readonly name: string;
  readonly content: string | null;
  readonly loading: boolean;
  readonly error: boolean;
}

function parseTime(value: string | null): number | null {
  if (!value) return null;
  return Date.parse(value) || null;
}

const initialThread = createEmptyThread(false);

export class AppState {
  threads = $state<Thread[]>([initialThread]);
  projects = $state<Project[]>([]);
  activeThreadId = $state<string>(initialThread.id);

  activePanel = $state<PanelId | null>(null);
  panelTriggerEl = $state<HTMLElement | null>(null);

  newMenuOpen = $state(false);
  newMenuAnchor = $state<HTMLElement | null>(null);
  moreMenuOpen = $state(false);
  moreMenuAnchor = $state<HTMLElement | null>(null);
  moreMenuView = $state<MoreMenuView>('root');
  contextMoreMenuOpen = $state(false);
  contextMoreMenuAnchor = $state<HTMLElement | null>(null);

  settingsOpen = $state(false);
  settingsTriggerEl = $state<HTMLElement | null>(null);
  shortcutsOpen = $state(false);
  shortcutsTriggerEl = $state<HTMLElement | null>(null);
  commandPaletteOpen = $state(false);

  /** Set while a navigate-away-from-a-non-empty-temporary-chat confirmation is pending
   * (ux-foundations.md §2.3); calling it performs the navigation the user confirmed. */
  pendingTemporaryLeave = $state<(() => void) | null>(null);

  drafts = $state<Record<string, string>>({});

  #mockToolCalls = $state<ToolCallRecord[]>([]);
  mcpServers = $state<McpServerRecord[]>([{ id: 'mcp-docs', name: 'docs-index', connected: true }]);
  attachments = $state<AttachmentRecord[]>([]);
  isDropTargetActive = $state(false);

  compactedBaseline = $state<Record<string, number>>({});
  feedback = $state<Record<string, 'good' | 'bad' | undefined>>({});

  /** Agent mode: what each assistant reply's run has done, keyed by the message's client id. */
  activityByMessage = $state<Record<string, RunActivity>>({});

  /** The admin's starting questions, keyed by `${mode}:${locale}`. An empty list means none are set
   * and the client's own copy is used (roadmap U7). */
  starters = $state<Record<string, readonly string[]>>({});
  /** The files each thread's agent wrote under /notes/ (roadmap U10), and the one being read. */
  agentFilesByThread = $state<Record<string, AgentFileRow[]>>({});
  filePreview = $state<AgentFilePreview | null>(null);
  /** The team document or attachment a citation last opened in the Attachments panel (roadmap U4). */
  focusedSource = $state<Citation | null>(null);
  /** Threads that approve their plans without a review, see skipPlanReview. */
  skippedPlanReviews = $state<string[]>(readSkippedPlanReviews());

  liveMessage = $state('');

  readonly scrollMemory = new ScrollMemoryStore();
  readonly #scrollControllers = new SvelteMap<string, ScrollController>();
  readonly #streams = new SvelteMap<string, MockAssistantStream>();
  /** Agent mode: live runs by run id. */
  readonly #sessions = new SvelteMap<string, RunSession>();
  /** Agent mode: replies stopped before their run id came back from the server. */
  readonly #pendingStops = new SvelteSet<string>();
  /** Agent mode: threads whose runs have been loaded from the server this session. */
  readonly #loadedThreads = new SvelteSet<string>();
  #persistence: PersistenceHooks | null = null;
  #uploader: Uploader | null = null;

  constructor() {
    this.#ensureScrollController(initialThread.id);
  }

  setPersistence(hooks: PersistenceHooks): void {
    this.#persistence = hooks;
  }

  clearPersistence(): void {
    this.#persistence = null;
  }

  setUploader(uploader: Uploader): void {
    this.#uploader = uploader;
  }

  clearUploader(): void {
    this.#uploader = null;
  }

  #notifyThread(thread: Thread): void {
    this.#persistence?.threadChanged(thread);
  }

  #notifyMessage(threadId: string, messageId: string): void {
    // In agent mode the server writes run-owned messages (roadmap §3.9); only the mock path
    // upserts them from here.
    if (!isMockAssistant) return;
    const thread = this.threads.find((th) => th.id === threadId);
    const message = thread?.messages.find((m) => m.id === messageId);
    if (thread && message) this.#persistence?.messageChanged(thread, message);
  }

  /** Replaces the in-memory conversations with what the backend returned (called once after
   * sign-in). Never notifies persistence: these threads came *from* the backend. */
  hydrateThreads(threads: Thread[]): void {
    const next = threads.length > 0 ? threads : [createEmptyThread(false)];
    for (const thread of next) this.#ensureScrollController(thread.id);
    this.threads = next;
    this.activeThreadId = next[0]?.id ?? initialThread.id;
  }

  /** Sign-out teardown: back to a single empty canvas with no server state attached. */
  reset(): void {
    for (const session of [...this.#sessions.values()]) this.#endSession(session);
    this.#pendingStops.clear();
    this.#loadedThreads.clear();
    this.activityByMessage = {};
    const thread = createEmptyThread(false);
    this.#ensureScrollController(thread.id);
    this.threads = [thread];
    this.activeThreadId = thread.id;
    this.attachments = [];
    this.#mockToolCalls = [];
    this.feedback = {};
    this.drafts = {};
    this.compactedBaseline = {};
    this.agentFilesByThread = {};
    this.filePreview = null;
    this.focusedSource = null;
    this.closeMenusAndPanels();
  }

  /** Storage ids of this session's uploaded attachments — attached to the next sent message. */
  get pendingAttachmentStorageIds(): string[] {
    return this.attachments
      .map((attachment) => attachment.storageId)
      .filter((id): id is string => Boolean(id));
  }

  get activeThread(): Thread {
    return (
      this.threads.find((thread) => thread.id === this.activeThreadId) ??
      this.threads[0] ??
      initialThread
    );
  }

  get isActiveThreadBusy(): boolean {
    return this.activeThread.messages.some(
      (m) => m.status === 'pending' || m.status === 'streaming',
    );
  }

  /** The reply whose run is paused for a plan review in the active thread, or null. While it is,
   * the composer shows the waiting state instead of Stop (roadmap U8). */
  get waitingReviewMessageId(): string | null {
    for (const message of [...this.activeThread.messages].reverse()) {
      if (this.activityByMessage[message.id]?.status === 'interrupted') return message.id;
    }
    return null;
  }

  get pinnedSourceCount(): number {
    const lastAssistant = [...this.activeThread.messages]
      .reverse()
      .find((m) => m.role === 'assistant');
    return lastAssistant?.citations?.length ?? 0;
  }

  /** The citations that resolve a reply's `[n]` markers. A finished reply carries its own list. A
   * reply still streaming resolves against the sources its run has reported so far, so a marker
   * links as soon as its source arrives rather than when the run ends. */
  citationsFor(message: ChatMessage): readonly Citation[] | undefined {
    const live = message.status === 'pending' || message.status === 'streaming';
    if (isMockAssistant || !live) return message.citations;
    const sources = this.activityByMessage[message.id]?.sources ?? [];
    return sources.map((source) => ({
      index: source.index,
      title: source.title,
      url: source.url,
      kind: source.kind,
      ref: source.ref,
    }));
  }

  /** The tool calls of the active thread, in order. Mock mode keeps its own list; with the agent
   * the list is read from each reply's run activity (roadmap U5 builds the timeline on top). */
  get toolCalls(): ToolCallRecord[] {
    if (isMockAssistant) return this.#mockToolCalls;
    const records: ToolCallRecord[] = [];
    for (const message of this.activeThread.messages) {
      const tools = this.activityByMessage[message.id]?.tools ?? [];
      for (const tool of tools) {
        records.push({ id: tool.id, name: tool.name, status: tool.status });
      }
    }
    return records;
  }

  /** The most recent context reading in the active thread. Agent mode takes it from the server's
   * `usage` event; a thread with no run yet reads as empty. */
  get contextPercent(): number {
    if (!isMockAssistant) return this.#latestContextPercent();
    const thread = this.activeThread;
    const totalChars = thread.messages.reduce((sum, m) => sum + m.text.length, 0);
    const baseline = this.compactedBaseline[thread.id] ?? 0;
    const effective = Math.max(0, totalChars - baseline);
    return Math.min(100, (effective / CONTEXT_BUDGET_CHARS) * 100);
  }

  #latestContextPercent(): number {
    for (const message of [...this.activeThread.messages].reverse()) {
      const percent = this.activityByMessage[message.id]?.usage?.contextPercent;
      if (percent !== undefined && percent !== null) return percent;
    }
    return 0;
  }

  /** Creates and stores a controller for a thread. Called only from imperative contexts (thread
   * creation) — never lazily from `scrollControllerFor`, which templates read via `$derived`
   * (MessageList.svelte's `$controller` auto-subscription): writing to #scrollControllers from
   * inside that derived's evaluation is exactly the "state_unsafe_mutation" Svelte forbids. */
  #ensureScrollController(threadId: string): void {
    if (!this.#scrollControllers.has(threadId)) {
      this.#scrollControllers.set(threadId, new ScrollController());
    }
  }

  /** Pure read, safe to call from a $derived — see #ensureScrollController. The fallback instance
   * is only ever reached if a thread id somehow has no pre-created controller. */
  scrollControllerFor(threadId: string): ScrollController {
    return this.#scrollControllers.get(threadId) ?? new ScrollController();
  }

  get activeScrollController(): ScrollController {
    return this.scrollControllerFor(this.activeThreadId);
  }

  closeMenusAndPanels(): void {
    this.activePanel = null;
    this.newMenuOpen = false;
    this.moreMenuOpen = false;
    this.moreMenuView = 'root';
    this.contextMoreMenuOpen = false;
  }

  createThread(isTemporary: boolean): Thread {
    const thread = createEmptyThread(isTemporary);
    this.#ensureScrollController(thread.id);
    this.threads = [thread, ...this.threads];
    this.activeThreadId = thread.id;
    this.closeMenusAndPanels();
    this.#notifyThread(thread);
    return thread;
  }

  switchThread(threadId: string): void {
    this.activeThreadId = threadId;
    this.filePreview = null;
    this.focusedSource = null;
    this.closeMenusAndPanels();
  }

  createProject(): void {
    const thread = createEmptyThread(false);
    this.#ensureScrollController(thread.id);
    const project: Project = {
      id: createId('project'),
      name: t('panel.projects.untitledName'),
      threadIds: [thread.id],
    };
    this.projects = [project, ...this.projects];
    this.threads = [thread, ...this.threads];
    this.activeThreadId = thread.id;
    this.closeMenusAndPanels();
    this.#notifyThread(thread);
  }

  openPanel(panel: PanelId, trigger: HTMLElement | null): void {
    this.activePanel = this.activePanel === panel ? null : panel;
    this.panelTriggerEl = trigger;
    this.newMenuOpen = false;
    this.moreMenuOpen = false;
    this.contextMoreMenuOpen = false;
    if (this.activePanel === 'attachments') {
      this.focusedSource = null;
      this.filePreview = null;
      void this.loadAgentFiles(this.activeThreadId);
    }
  }

  /** Opens the Attachments panel on the team document or attachment a citation names (roadmap
   * U4). `trigger` gets focus back when the panel closes. */
  showSource(citation: Citation, trigger: HTMLElement): void {
    this.focusedSource = citation;
    this.filePreview = null;
    this.panelTriggerEl = trigger;
    this.newMenuOpen = false;
    this.moreMenuOpen = false;
    this.contextMoreMenuOpen = false;
    this.activePanel = 'attachments';
    void this.loadAgentFiles(this.activeThreadId);
  }

  setDraft(threadId: string, value: string): void {
    this.drafts[threadId] = value;
  }

  draftFor(threadId: string): string {
    return this.drafts[threadId] ?? '';
  }

  setMode(threadId: string, mode: ComposerMode): void {
    const thread = this.threads.find((th) => th.id === threadId);
    if (thread) {
      thread.mode = mode;
      this.#notifyThread(thread);
    }
  }

  /** Truncates the thread back to just before the given message and hands its text back so the
   * caller can drop it into the composer — ux-foundations.md §4.4's "Edit and resend", kept
   * simple (see the README's judgement-call notes on branch history). */
  beginEdit(threadId: string, messageId: string): string {
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) return '';
    const index = thread.messages.findIndex((m) => m.id === messageId);
    if (index === -1) return '';
    const text = thread.messages[index]?.text ?? '';
    const removed = thread.messages.slice(index);
    thread.messages = thread.messages.slice(0, index);
    for (const message of removed) {
      this.#persistence?.messageRemoved(threadId, message.id);
      if (!isMockAssistant) this.#detachMessage(message.id);
    }
    this.#notifyThread(thread);
    return text;
  }

  /**
   * Looks up a message fresh from the live, reactive `threads` array. This matters more than it
   * looks: Svelte 5 wraps a plain object in its own reactive proxy at the moment it is *inserted*
   * into `$state`-tracked storage (e.g. `thread.messages.push(message)`) — the pre-insertion
   * `message` reference you still hold keeps working as plain data, but writes through it no
   * longer notify Svelte, so the UI silently stops updating. Every mutation below that has to
   * survive an `async` boundary (a `setTimeout`, a stream callback, an animation frame) therefore
   * re-fetches the message by id right before touching it, instead of closing over the object
   * from before it was pushed.
   */
  #findMessage(threadId: string, messageId: string): ChatMessage | undefined {
    return this.threads.find((th) => th.id === threadId)?.messages.find((m) => m.id === messageId);
  }

  sendMessage(threadId: string, rawText: string, attachmentIds?: string[]): ChatMessage | null {
    const text = rawText.trim();
    if (text.length === 0) return null;
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) return null;
    const id = createId('msg');
    const message: ChatMessage = {
      id,
      role: 'user',
      status: 'pending',
      text,
      createdAt: Date.now(),
      attachmentIds: attachmentIds && attachmentIds.length > 0 ? [...attachmentIds] : undefined,
    };
    thread.messages.push(message);
    this.drafts[threadId] = '';
    this.#notifyMessage(threadId, id);
    if (isMockAssistant) this.#settleUserMessage(threadId, id);
    else this.#startSend(threadId, id);
    // `id` never changes after creation, so returning this pre-insertion reference is fine —
    // callers only ever read `.id` off it (see #findMessage's doc comment for what would NOT be
    // fine: mutating this object later and expecting the UI to notice).
    return message;
  }

  /** Retries a message that failed: a user message re-sends, an assistant reply regenerates. */
  retryMessage(threadId: string, messageId: string): void {
    if (isMockAssistant) {
      this.#settleUserMessage(threadId, messageId);
      return;
    }
    const message = this.#findMessage(threadId, messageId);
    if (!message || message.status !== 'error') return;
    if (message.role === 'user') this.#startSend(threadId, messageId);
    else this.#launchFor(threadId, messageId, 'regenerate');
  }

  #settleUserMessage(threadId: string, messageId: string): void {
    const message = this.#findMessage(threadId, messageId);
    if (!message) return;
    message.status = 'pending';
    setTimeout(() => {
      const current = this.#findMessage(threadId, messageId);
      if (!current) return;
      const failed = Math.random() < SIMULATED_FAILURE_RATE;
      current.status = failed ? 'error' : 'complete';
      this.#notifyMessage(threadId, messageId);
      if (!failed) this.#beginAssistantReply(threadId, messageId);
    }, SIMULATED_LATENCY_MS);
  }

  #beginAssistantReply(threadId: string, forMessageId: string): void {
    const thread = this.threads.find((th) => th.id === threadId);
    const forMessage = this.#findMessage(threadId, forMessageId);
    if (!thread || !forMessage) return;
    const assistantId = createId('msg');
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      status: 'pending',
      text: '',
      createdAt: Date.now(),
    };
    thread.messages.push(assistantMessage);
    // §3.4: counts toward the Jump-to-latest badge if the reader is currently scrolled away —
    // a no-op if they are pinned, which they always are right after sending (see prepareForSend).
    this.scrollControllerFor(threadId).notifyMessageArrived();
    if (thread.mode === 'research') {
      this.#mockToolCalls = [
        ...this.#mockToolCalls,
        { id: createId('tool'), name: t('panel.toolCalls.webSearchName'), status: 'success' },
      ];
    }
    this.liveMessage = t('thread.responseStarted');
    const { stream, citations } = createMockReply(forMessage.text, thread.mode, getLocale());
    const live = this.#findMessage(threadId, assistantId);
    if (live) {
      live.citations = citations;
      live.status = 'streaming';
    }
    this.#runStream(threadId, assistantId, stream);
  }

  regenerate(threadId: string, messageId: string): void {
    if (!isMockAssistant) {
      this.#launchFor(threadId, messageId, 'regenerate');
      return;
    }
    const thread = this.threads.find((th) => th.id === threadId);
    const message = thread?.messages.find((m) => m.id === messageId && m.role === 'assistant');
    if (!thread || !message) return;
    const index = thread.messages.indexOf(message);
    const priorUser = [...thread.messages.slice(0, index)].reverse().find((m) => m.role === 'user');
    if (!priorUser) return;
    const { stream, citations } = createMockReply(priorUser.text, thread.mode, getLocale());
    message.text = '';
    message.status = 'streaming';
    message.citations = citations;
    this.liveMessage = t('thread.responseStarted');
    this.#runStream(threadId, messageId, stream);
  }

  continueMessage(threadId: string, messageId: string): void {
    if (!isMockAssistant) {
      this.#launchFor(threadId, messageId, 'continue');
      return;
    }
    const message = this.#findMessage(threadId, messageId);
    const stream = this.#streams.get(messageId);
    if (!message || !stream) return;
    message.status = 'streaming';
    this.liveMessage = t('thread.responseStarted');
    this.#runStream(threadId, messageId, stream);
  }

  stopStreaming(threadId: string): void {
    if (!isMockAssistant) {
      this.#stopRun(threadId);
      return;
    }
    const thread = this.threads.find((th) => th.id === threadId);
    const message = thread?.messages.find((m) => m.status === 'streaming');
    if (!thread || !message) return;
    this.#streams.get(message.id)?.stop();
    message.status = 'stopped';
    this.#notifyMessage(threadId, message.id);
    this.scrollControllerFor(threadId).notifyStreamSettled();
  }

  #runStream(threadId: string, messageId: string, stream: MockAssistantStream): void {
    this.#streams.set(messageId, stream);
    let pendingText = this.#findMessage(threadId, messageId)?.text ?? '';
    let frame: number | null = null;
    const flush = (): void => {
      const message = this.#findMessage(threadId, messageId);
      if (message) message.text = pendingText;
      frame = null;
    };
    stream.start(
      // ux-foundations.md §4.2: buffer to one animation frame and flush, rather than rendering
      // every chunk as it lands.
      (_chunk, textSoFar) => {
        pendingText = textSoFar;
        if (frame === null) frame = requestAnimationFrame(flush);
      },
      () => {
        if (frame !== null) {
          cancelAnimationFrame(frame);
          flush();
        }
        const message = this.#findMessage(threadId, messageId);
        if (message) message.status = 'complete';
        this.#streams.delete(messageId);
        this.#notifyMessage(threadId, messageId);
        this.liveMessage = t('thread.responseComplete');
        this.scrollControllerFor(threadId).notifyStreamSettled();
      },
    );
  }

  // --- agent runs -----------------------------------------------------------------------------

  /** A new send: the server persists the user message and the reply placeholder when the run is
   * created, so this only adds the optimistic assistant placeholder and asks for the run. */
  #startSend(threadId: string, userMessageId: string): void {
    const thread = this.threads.find((th) => th.id === threadId);
    const userMessage = this.#findMessage(threadId, userMessageId);
    if (!thread || !userMessage) return;
    userMessage.status = 'pending';
    userMessage.errorCode = undefined;
    userMessage.errorResetAt = undefined;
    const messageId = createId('msg');
    thread.messages.push({
      id: messageId,
      role: 'assistant',
      status: 'pending',
      text: '',
      createdAt: Date.now(),
    });
    // §3.4: same as the mock reply — counts toward Jump-to-latest when the reader is away.
    this.scrollControllerFor(threadId).notifyMessageArrived();
    void this.#launch({ threadId, messageId, kind: 'send', userMessageId });
  }

  /** Regenerate or continue an existing assistant reply. */
  #launchFor(threadId: string, messageId: string, kind: 'regenerate' | 'continue'): void {
    const message = this.#findMessage(threadId, messageId);
    if (!message || message.role !== 'assistant') return;
    if (this.#isRunActive(messageId)) return;
    message.status = 'pending';
    message.errorCode = undefined;
    message.errorResetAt = undefined;
    void this.#launch({ threadId, messageId, kind, userMessageId: null });
  }

  #isRunActive(messageId: string): boolean {
    const activity = this.activityByMessage[messageId];
    return activity !== undefined && isActiveRunStatus(activity.status);
  }

  /** Creates the run on the server, then attaches to its stream. The thread's pending writes go
   * first, so a brand-new thread exists on the server before the run names it. */
  async #launch(launch: Launch): Promise<void> {
    const { threadId, messageId, kind, userMessageId } = launch;
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) {
      this.#runRejected(launch, new Error('thread not found'));
      return;
    }
    // Captured before the await: the user may cycle the mode while the request is in flight.
    const mode = thread.mode;
    let runId: string;
    try {
      // A thread hydrated locally (an account with no conversations yet) was never upserted, and
      // the server writes run-owned messages, so nothing else would create it before the run.
      this.#notifyThread(thread);
      await this.#persistence?.threadSettled(threadId);
      const userMessage = userMessageId ? this.#findMessage(threadId, userMessageId) : undefined;
      const created = await createRun(threadId, {
        kind,
        assistant_client_id: messageId,
        mode,
        model_slug: models.selectedId,
        user_message: userMessage
          ? {
              client_id: userMessage.id,
              text: userMessage.text,
              attachment_ids: userMessage.attachmentIds ?? null,
            }
          : null,
      });
      runId = created.run_id;
    } catch (error) {
      this.#runRejected(launch, error);
      return;
    }
    this.#runCreated(launch, runId);
  }

  #runCreated(launch: Launch, runId: string): void {
    const { threadId, messageId, kind, userMessageId } = launch;
    this.activityByMessage[messageId] = createRunActivity(runId);
    if (userMessageId) {
      const userMessage = this.#findMessage(threadId, userMessageId);
      if (userMessage) userMessage.status = 'complete';
    }
    if (kind === 'regenerate') {
      // The server has just cleared the reply; the text the user saw is replaced from here on.
      const message = this.#findMessage(threadId, messageId);
      if (message) {
        message.text = '';
        message.citations = undefined;
      }
    }
    this.#attach(threadId, messageId, runId, 'live');
    if (this.#pendingStops.delete(messageId)) void cancelRun(runId).catch(() => undefined);
  }

  /** The run was never created, so nothing exists on the server. A send disappears with its
   * placeholder and leaves its user message in the error state; the other kinds keep their text
   * and show the error on the reply. Either way the error sits in the thread with Retry. */
  #runRejected(launch: Launch, error: unknown): void {
    const { threadId, messageId, kind, userMessageId } = launch;
    const info = failureInfoOf(error);
    this.#pendingStops.delete(messageId);
    delete this.activityByMessage[messageId];
    const thread = this.threads.find((th) => th.id === threadId);
    if (kind === 'send') {
      if (thread) thread.messages = thread.messages.filter((m) => m.id !== messageId);
      const userMessage = userMessageId ? this.#findMessage(threadId, userMessageId) : undefined;
      if (userMessage) {
        userMessage.status = 'error';
        userMessage.errorCode = info.code;
        userMessage.errorResetAt = info.resetAt;
      }
    } else {
      const message = this.#findMessage(threadId, messageId);
      if (message) {
        message.status = 'error';
        message.errorCode = info.code;
        message.errorResetAt = info.resetAt;
      }
    }
    this.scrollControllerFor(threadId).notifyStreamSettled();
  }

  /** Starts listening to a run. `reattach` is for a run already underway when this page loaded:
   * its replay begins with the text the message already holds, so that prefix is skipped. */
  #attach(threadId: string, messageId: string, runId: string, mode: 'live' | 'reattach'): void {
    if (this.#sessions.has(runId)) return;
    const message = this.#findMessage(threadId, messageId);
    const session: RunSession = {
      runId,
      threadId,
      messageId,
      subscription: null,
      skip: mode === 'reattach' ? (message?.text.length ?? 0) : 0,
      buffer: message?.text ?? '',
      frame: null,
    };
    this.#sessions.set(runId, session);
    session.subscription = subscribeToRun(
      runId,
      0,
      (_seq, event) => this.#onRunEvent(session, event),
      () => this.#streamLost(session),
    );
  }

  #onRunEvent(session: RunSession, event: RunEvent): void {
    const current = this.activityByMessage[session.messageId] ?? createRunActivity(session.runId);
    const next = applyRunEvent(current, event);
    if (next !== current) this.activityByMessage[session.messageId] = next;

    switch (event.type) {
      case 'run.started':
        this.liveMessage = t('thread.responseStarted');
        break;
      case 'todos.updated': {
        // roadmap U18: a finished step is announced politely. The streamed text never is.
        const progress = newlyCompletedStep(current.todos, next.todos);
        if (progress) {
          this.liveMessage = t('agent.announce.stepCompleted', {
            done: progress.completed,
            total: progress.total,
          });
        }
        break;
      }
      case 'interrupt':
        this.liveMessage = t('agent.review.waiting');
        if (this.skipsPlanReview(session.threadId)) {
          void this.resumePlan(session.messageId, 'approve', null, true);
        }
        break;
      case 'file.written':
        void this.loadAgentFiles(session.threadId);
        break;
      case 'message.delta':
        this.#appendText(session, event.payload.text);
        break;
      case 'run.completed':
        this.#finish(session, 'complete', {
          text: event.payload.text,
          citations: [...event.payload.citations],
        });
        this.liveMessage = t('thread.responseComplete');
        break;
      case 'run.cancelled':
        this.#finish(session, 'stopped', { text: event.payload.text });
        break;
      case 'run.failed':
        this.#finish(session, 'error', { errorCode: event.payload.error_code });
        break;
      default:
        break;
    }
  }

  #appendText(session: RunSession, text: string): void {
    let fresh = text;
    if (session.skip > 0) {
      const cut = Math.min(session.skip, fresh.length);
      session.skip -= cut;
      fresh = fresh.slice(cut);
    }
    if (fresh.length === 0) return;
    session.buffer += fresh;
    // ux-foundations.md §4.2: buffer to one animation frame and flush.
    if (session.frame === null) {
      session.frame = requestAnimationFrame(() => this.#flush(session));
    }
  }

  #flush(session: RunSession): void {
    session.frame = null;
    const message = this.#findMessage(session.threadId, session.messageId);
    if (!message) return;
    message.text = session.buffer;
    if (message.status === 'pending') message.status = 'streaming';
  }

  #finish(
    session: RunSession,
    status: 'complete' | 'stopped' | 'error',
    outcome: {
      readonly text?: string;
      readonly citations?: readonly Citation[];
      readonly errorCode?: RunErrorCode;
    },
  ): void {
    if (session.frame !== null) cancelAnimationFrame(session.frame);
    session.frame = null;
    const message = this.#findMessage(session.threadId, session.messageId);
    if (message) {
      // The server's final text is authoritative: it includes anything that was not yet flushed.
      message.text = outcome.text ?? session.buffer;
      message.status = status;
      if (outcome.citations) message.citations = [...outcome.citations];
      message.errorCode = outcome.errorCode;
    }
    this.#endSession(session);
    this.scrollControllerFor(session.threadId).notifyStreamSettled();
    if (status === 'complete' && message) this.#notifyAnswerComplete(message);
  }

  /** The Notifications setting is intentionally narrow: a completed answer, this tab hidden,
   * and permission already granted. Nothing fires when the reader is looking at the tab. */
  #notifyAnswerComplete(message: ChatMessage): void {
    if (!preferences.values.notifyOnComplete) return;
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    if (typeof document === 'undefined' || !document.hidden) return;
    const body =
      message.text.replace(/\s+/g, ' ').trim().slice(0, 140) ||
      t('settings.notifications.completeFallback');
    try {
      new Notification(t('settings.notifications.completeTitle'), {
        body,
        tag: 'sofee-answer',
      });
    } catch {
      // Some browsers expose the API but refuse construction outside a service worker.
    }
  }

  /** The browser gave up on the stream (an HTTP error) while the run was still going. */
  #streamLost(session: RunSession): void {
    this.#finish(session, 'error', { errorCode: 'internal' });
  }

  #endSession(session: RunSession): void {
    if (session.frame !== null) cancelAnimationFrame(session.frame);
    session.frame = null;
    session.subscription?.close();
    session.subscription = null;
    this.#sessions.delete(session.runId);
  }

  #detachMessage(messageId: string): void {
    for (const session of [...this.#sessions.values()]) {
      if (session.messageId === messageId) this.#endSession(session);
    }
    const runId = this.activityByMessage[messageId]?.runId;
    if (runId && this.#isRunActive(messageId)) void cancelRun(runId).catch(() => undefined);
    delete this.activityByMessage[messageId];
    this.#pendingStops.delete(messageId);
  }

  #stopRun(threadId: string): void {
    const thread = this.threads.find((th) => th.id === threadId);
    const message = [...(thread?.messages ?? [])]
      .reverse()
      .find((m) => m.role === 'assistant' && (m.status === 'pending' || m.status === 'streaming'));
    if (!message) return;
    const runId = this.activityByMessage[message.id]?.runId;
    if (!runId) {
      // The run is still being created; it is cancelled as soon as its id is known.
      this.#pendingStops.add(message.id);
      return;
    }
    void cancelRun(runId).catch(() => undefined);
  }

  /** Reads the thread's runs from the server, rebuilds their activity, and reattaches to a run
   * that is still going. Runs once per thread per session; call it when a thread is opened. */
  async loadRuns(threadId: string): Promise<void> {
    if (isMockAssistant || this.#loadedThreads.has(threadId)) return;
    this.#loadedThreads.add(threadId);
    try {
      const [list, latest] = await Promise.all([listRuns(threadId), getLatestRun(threadId)]);
      for (const run of list) this.#hydrateRun(threadId, run);
      if (latest && isActiveRunStatus(latest.status)) {
        const thread = this.threads.find((th) => th.id === threadId);
        if (thread?.messages.some((m) => m.id === latest.assistant_message_id)) {
          this.#attach(threadId, latest.assistant_message_id, latest.run_id, 'reattach');
        }
      }
    } catch {
      // Unloaded: the next time this thread opens it is tried again.
      this.#loadedThreads.delete(threadId);
    }
  }

  /** Folds a stored run into its reply's activity. The replay ends with the server's own status and
   * times, so the result matches the run even where the stored events are not complete. */
  #hydrateRun(threadId: string, run: RunWithEvents): void {
    const startedAt = parseTime(run.started_at);
    const finishedAt = parseTime(run.finished_at);
    let activity = createRunActivity(run.run_id, run.status, startedAt);
    for (const stored of run.events) {
      const event = toRunEvent(stored.type, stored.payload);
      if (event) activity = applyRunEvent(activity, event, finishedAt ?? startedAt ?? 0);
    }
    this.activityByMessage[run.assistant_message_id] = {
      ...activity,
      status: run.status,
      startedAt,
      finishedAt,
    };
    const message = this.#findMessage(threadId, run.assistant_message_id);
    if (message && activity.error) message.errorCode = activity.error.code;
  }

  /**
   * Answers a plan-review pause (roadmap §3.8). Until the server accepts the answer the card stays as
   * it is. Once it does, the run is shown as running again; the events that follow confirm it. A
   * refusal leaves the run waiting and says so politely, so the user can answer again. `quiet` is
   * for an answer nobody asked for (a thread that skips review), where a refusal is not news.
   */
  async resumePlan(
    messageId: string,
    decision: 'approve' | 'edit' | 'reject',
    todos: readonly RunTodo[] | null,
    quiet = false,
  ): Promise<void> {
    const activity = this.activityByMessage[messageId];
    if (!activity || activity.status !== 'interrupted') return;
    try {
      await resumeRun(activity.runId, decision, todos ? [...todos] : null);
    } catch {
      if (!quiet) this.liveMessage = t('agent.review.failed');
      return;
    }
    const current = this.activityByMessage[messageId];
    if (current) {
      this.activityByMessage[messageId] = { ...current, status: 'running', interrupt: null };
    }
  }

  /** "Approve": the plan runs as the agent wrote it. */
  async approvePlan(messageId: string): Promise<void> {
    await this.resumePlan(messageId, 'approve', null);
  }

  /** "Edit": the plan runs as the user changed it. Blank steps are dropped; with no step left there
   * is nothing to send, and the card keeps asking. */
  async editPlan(messageId: string, steps: readonly string[]): Promise<void> {
    const todos = editedPlan([...steps]);
    if (todos === null) return;
    await this.resumePlan(messageId, 'edit', todos);
  }

  /** "Continue without review": approves this plan, and every later plan in the thread, without
   * asking. */
  async skipPlanReview(messageId: string): Promise<void> {
    const threadId = this.#threadIdOf(messageId);
    if (threadId !== null && !this.skippedPlanReviews.includes(threadId)) {
      this.skippedPlanReviews = [...this.skippedPlanReviews, threadId];
      writeSkippedPlanReviews(this.skippedPlanReviews);
    }
    await this.resumePlan(messageId, 'approve', null);
  }

  skipsPlanReview(threadId: string): boolean {
    return this.skippedPlanReviews.includes(threadId);
  }

  #threadIdOf(messageId: string): string | null {
    return this.threads.find((th) => th.messages.some((m) => m.id === messageId))?.id ?? null;
  }

  // --- starting questions and agent files ---------------------------------------------------

  /** The admin's starting questions for a mode and locale, or none (the caller falls back). */
  startersFor(mode: ComposerMode, locale: string): readonly string[] {
    return this.starters[`${mode}:${locale}`] ?? [];
  }

  /** Loads the starting questions once per mode and locale. A failure leaves the client's own copy
   * in place, and the next request tries again. */
  async loadStarters(mode: ComposerMode, locale: string): Promise<void> {
    const key = `${mode}:${locale}`;
    if (isMockAssistant || this.starters[key] !== undefined) return;
    try {
      const rows = await fetchStarters(mode, locale);
      this.starters[key] = rows.map((row) => row.text);
    } catch {
      // The client's own starting questions stand in.
    }
  }

  /** Refreshes the list of files the agent wrote in a thread. */
  async loadAgentFiles(threadId: string): Promise<void> {
    if (isMockAssistant) return;
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread || thread.isTemporary) return;
    try {
      this.agentFilesByThread[threadId] = await listAgentFiles(threadId);
    } catch {
      // The list already on screen stays.
    }
  }

  /** Reads one agent file for the preview. Only the latest request for a path is shown. */
  async openAgentFile(threadId: string, path: string): Promise<void> {
    this.filePreview = {
      threadId,
      path,
      name: basename(path),
      content: null,
      loading: true,
      error: false,
    };
    try {
      const file = await readAgentFile(threadId, path);
      const current = this.filePreview;
      if (current?.path === path)
        this.filePreview = { ...current, content: file.content, loading: false };
    } catch {
      const current = this.filePreview;
      if (current?.path === path) this.filePreview = { ...current, loading: false, error: true };
    }
  }

  closeAgentFile(): void {
    this.filePreview = null;
  }

  // --- context --------------------------------------------------------------------------------

  async compactContext(threadId: string): Promise<void> {
    if (!isMockAssistant) {
      const compacted = await this.#contextCall(threadId, () => compactThread(threadId));
      if (compacted !== null) await this.#refreshCutState(threadId);
      return;
    }
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) return;
    const totalChars = thread.messages.reduce((sum, m) => sum + m.text.length, 0);
    // Simulates a summarisation pass that keeps roughly a third of the current usage.
    this.compactedBaseline[threadId] = Math.round(totalChars * 0.65);
  }

  async clearContext(threadId: string): Promise<void> {
    if (!isMockAssistant) {
      const cleared = await this.#contextCall(threadId, () => clearThreadContext(threadId));
      if (cleared === null) return;
      this.#forgetUsage(threadId);
      const thread = this.threads.find((th) => th.id === threadId);
      if (thread) thread.contextStartSeq = cleared.context_start_seq;
      await this.#refreshCutState(threadId);
      return;
    }
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) return;
    const totalChars = thread.messages.reduce((sum, m) => sum + m.text.length, 0);
    this.compactedBaseline[threadId] = totalChars;
  }

  /** Runs a context call once the thread is on the server. Its answer, or null on failure. */
  async #contextCall<T>(threadId: string, call: () => Promise<T>): Promise<T | null> {
    try {
      await this.#persistence?.threadSettled(threadId);
      return await call();
    } catch {
      this.liveMessage = t('thread.contextFailed');
      return null;
    }
  }

  /**
   * Reads each message's seq and the two cut points from the server, so the context dividers sit in
   * the right place. Runs write their replies on the server, and their seq only comes back this way.
   * A failure leaves the dividers where they were until the next refresh.
   */
  async #refreshCutState(threadId: string): Promise<void> {
    try {
      const state = await loadThreadCutState(threadId);
      const thread = this.threads.find((th) => th.id === threadId);
      if (!thread) return;
      for (const message of thread.messages) {
        const seq = state.seqs[message.id];
        if (seq !== undefined) message.seq = seq;
      }
      thread.summaryThroughSeq = state.summaryThroughSeq;
      thread.contextStartSeq = state.contextStartSeq;
    } catch {
      // The dividers wait for the next refresh.
    }
  }

  /** After Clear the meter reads empty until the next run reports usage again. */
  #forgetUsage(threadId: string): void {
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) return;
    for (const message of thread.messages) {
      const activity = this.activityByMessage[message.id];
      if (activity?.usage) this.activityByMessage[message.id] = { ...activity, usage: null };
    }
  }

  addAttachment(
    name: string,
    kind: AttachmentRecord['kind'],
    sizeLabel?: string,
    file?: File,
  ): void {
    const id = createId('att');
    this.attachments = [
      ...this.attachments,
      { id, name, kind, sizeLabel, uploading: file !== undefined },
    ];
    if (file && this.#uploader) {
      this.#uploader(file)
        .then((storageId) =>
          this.#finishAttachment(id, {
            storageId,
            url: `/api/v1/storage/${storageId}`,
            uploading: false,
          }),
        )
        .catch((error: unknown) =>
          this.#finishAttachment(id, {
            uploading: false,
            error: true,
            // 413: the server's upload limit; any other failure has no reason worth showing.
            ...(error instanceof ApiError && error.status === 413 ? { errorReason: 'tooLarge' as const } : {}),
          }),
        );
    }
  }

  #finishAttachment(id: string, patch: Partial<AttachmentRecord>): void {
    this.attachments = this.attachments.map((attachment) =>
      attachment.id === id ? { ...attachment, ...patch } : attachment,
    );
  }

  /**
   * Rates a reply. The rating shows at once and is saved to the server in agent mode (roadmap U15-lite).
   * Choosing the same rating again clears it. If the save fails, the rating goes back and the
   * failure is announced.
   */
  setFeedback(threadId: string, messageId: string, value: 'good' | 'bad'): void {
    const previous = this.feedback[messageId];
    const next = previous === value ? undefined : value;
    this.feedback[messageId] = next;
    if (isMockAssistant) return;
    putFeedback(threadId, messageId, next ?? null).catch(() => {
      this.feedback[messageId] = previous;
      this.liveMessage = t('agent.feedback.failed');
    });
  }
}

export const appState = new AppState();
