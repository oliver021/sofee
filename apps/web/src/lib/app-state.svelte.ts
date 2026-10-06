/**
 * The application's own state — everything packages/ui deliberately does not own (repo layout:
 * "packages/ui: Svelte components, no domain state"). One instance, created once in App.svelte.
 *
 * The assistant reply is still simulated: sending a message optimistically appends it
 * (ux-foundations.md §4.1), "acknowledges" it after a short simulated delay with an occasional
 * simulated failure so the Error+Retry state in §4.3 is actually reachable, and the reply comes
 * from packages/core's mock stream. Since M8 conversations *are* persisted: the shell installs
 * `PersistenceHooks` (see below) to mirror thread/message changes to the API, while this module
 * stays backend-agnostic.
 */
import {
  createId,
  createMockReply,
  MockAssistantStream,
  ScrollController,
  ScrollMemoryStore,
  type AttachmentRecord,
  type ChatMessage,
  type ComposerMode,
  type McpServerRecord,
  type Project,
  type Thread,
  type ToolCallRecord,
} from '@sofee/core';
import { SvelteMap } from 'svelte/reactivity';
import { getLocale, t } from './i18n.svelte.js';

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
}

type Uploader = (file: File) => Promise<string>;

/** A made-up budget purely for the simulated context meter — there is no real token count
 * without a backend, so this stands in for one. */
const CONTEXT_BUDGET_CHARS = 12000;
const SIMULATED_LATENCY_MS = 380;
const SIMULATED_FAILURE_RATE = 0.15;

function createEmptyThread(isTemporary: boolean): Thread {
  return {
    id: createId('thread'),
    title: '',
    isTemporary,
    createdAt: Date.now(),
    messages: [],
    mode: 'learn',
  };
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
  invertSendKey = $state(false);

  toolCalls = $state<ToolCallRecord[]>([]);
  mcpServers = $state<McpServerRecord[]>([{ id: 'mcp-docs', name: 'docs-index', connected: true }]);
  attachments = $state<AttachmentRecord[]>([]);
  isDropTargetActive = $state(false);

  compactedBaseline = $state<Record<string, number>>({});
  feedback = $state<Record<string, 'good' | 'bad' | undefined>>({});

  liveMessage = $state('');

  readonly scrollMemory = new ScrollMemoryStore();
  readonly #scrollControllers = new SvelteMap<string, ScrollController>();
  readonly #streams = new SvelteMap<string, MockAssistantStream>();
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
    const thread = createEmptyThread(false);
    this.#ensureScrollController(thread.id);
    this.threads = [thread];
    this.activeThreadId = thread.id;
    this.attachments = [];
    this.toolCalls = [];
    this.feedback = {};
    this.drafts = {};
    this.compactedBaseline = {};
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

  get pinnedSourceCount(): number {
    const lastAssistant = [...this.activeThread.messages]
      .reverse()
      .find((m) => m.role === 'assistant');
    return lastAssistant?.citations?.length ?? 0;
  }

  get contextPercent(): number {
    const thread = this.activeThread;
    const totalChars = thread.messages.reduce((sum, m) => sum + m.text.length, 0);
    const baseline = this.compactedBaseline[thread.id] ?? 0;
    const effective = Math.max(0, totalChars - baseline);
    return Math.min(100, (effective / CONTEXT_BUDGET_CHARS) * 100);
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
    for (const message of removed) this.#persistence?.messageRemoved(threadId, message.id);
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
    this.#settleUserMessage(threadId, id);
    // `id` never changes after creation, so returning this pre-insertion reference is fine —
    // callers only ever read `.id` off it (see #findMessage's doc comment for what would NOT be
    // fine: mutating this object later and expecting the UI to notice).
    return message;
  }

  retryUserMessage(threadId: string, messageId: string): void {
    this.#settleUserMessage(threadId, messageId);
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
      this.toolCalls = [
        ...this.toolCalls,
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
    const message = this.#findMessage(threadId, messageId);
    const stream = this.#streams.get(messageId);
    if (!message || !stream) return;
    message.status = 'streaming';
    this.liveMessage = t('thread.responseStarted');
    this.#runStream(threadId, messageId, stream);
  }

  stopStreaming(threadId: string): void {
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

  compactContext(threadId: string): void {
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) return;
    const totalChars = thread.messages.reduce((sum, m) => sum + m.text.length, 0);
    // Simulates a summarisation pass that keeps roughly a third of the current usage.
    this.compactedBaseline[threadId] = Math.round(totalChars * 0.65);
  }

  clearContext(threadId: string): void {
    const thread = this.threads.find((th) => th.id === threadId);
    if (!thread) return;
    const totalChars = thread.messages.reduce((sum, m) => sum + m.text.length, 0);
    this.compactedBaseline[threadId] = totalChars;
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
        .catch(() => this.#finishAttachment(id, { uploading: false, error: true }));
    }
  }

  #finishAttachment(id: string, patch: Partial<AttachmentRecord>): void {
    this.attachments = this.attachments.map((attachment) =>
      attachment.id === id ? { ...attachment, ...patch } : attachment,
    );
  }

  setFeedback(messageId: string, value: 'good' | 'bad'): void {
    this.feedback[messageId] = this.feedback[messageId] === value ? undefined : value;
  }
}

export const appState = new AppState();
