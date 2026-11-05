<!--
  The app shell: wires @sofee/ui's presentational components to apps/web's own state
  (app-state.svelte.ts) and to @sofee/core's framework-free logic (i18n, the scroll controller,
  the mock assistant). ux-foundations.md §2 — two 56px rails flanking one canvas, no sidebar.
-->
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import {
    contextMarks,
    isActiveRunStatus,
    type ChatMessage,
    type ComposerMode,
    type ContextMarkKind,
    type Thread,
  } from '@sofee/core';
  import { DEFAULT_PALETTE, type PaletteId } from '@sofee/tokens';
  import {
    AgentFiles,
    CommandPalette,
    ConfirmDialog,
    Composer,
    ContextDivider,
    ContextMeter,
    DirectionChips,
    DottedCanvas,
    EmptyState,
    LiveRegion,
    Menu,
    MessageItem,
    MessageList,
    DropdownPanel,
    OverlayPanel,
    IconToolbar,
    PlanBlock,
    PlanReview,
    QuizBlock,
    SettingsDialog,
    ShortcutsDialog,
    SourceList,
    SubagentCards,
    ToolTimeline,
    type MenuItemConfig,
    type SettingsSection,
    type ToolbarItem,
  } from '@sofee/ui';
  import {
    IconAttachments,
    IconChats,
    IconCompact,
    IconGlobe,
    IconKeyboard,
    IconMcp,
    IconMore,
    IconPalette,
    IconPlus,
    IconProjects,
    IconSettings,
    IconToolCalls,
    IconTrash,
  } from '@sofee/icons';
  import { appState, type PanelId } from './lib/app-state.svelte.js';
  import {
    agentFileViews,
    planView,
    sourceViews,
    subagentViews,
    toolRunViews,
    type AgentViewContext,
  } from './lib/agent-view.js';
  import { formatClockTime, getLocale, setLocale, t, tWide } from './lib/i18n.svelte.js';
  import { getPaletteId, listPalettes, setPaletteId } from './lib/palette.svelte.js';
  import AuthScreen from './AuthScreen.svelte';
  import { auth, type AuthStatus } from './lib/auth.svelte.js';
  import { models } from './lib/models.svelte.js';
  import { preferences } from './lib/preferences.svelte.js';
  import { uploadFile } from './lib/api.js';
  import {
    loadConversations,
    setConversationSync,
    syncMessage,
    syncMessageRemoved,
    syncThread,
    threadSettled,
  } from './lib/backend.svelte.js';

  let messageListRef: MessageList<ChatMessage> | null = $state(null);
  let composerRef: Composer | null = $state(null);
  let copiedMessageId: string | null = $state(null);

  const appVersion = __APP_VERSION__;
  const sourceUrl = 'https://github.com/oliver021/sofee';

  let settingsSection = $state<SettingsSection>('general');
  let notificationPermission = $state<'default' | 'denied' | 'granted' | 'unsupported'>('default');
  let settingsUser = $derived(
    auth.user
      ? {
          displayName: auth.user.display_name,
          email: auth.user.email,
          role: auth.user.role,
        }
      : null,
  );
  let hasConversations = $derived(
    appState.threads.some((thread) => thread.messages.length > 0),
  );
  let paletteId = $derived(getPaletteId());
  let paletteOptions = $derived(listPalettes());

  onMount(() => {
    notificationPermission =
      typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
    void auth.bootstrap();
  });

  function openSettings(
    section: SettingsSection = 'general',
    triggerEl: HTMLElement | null = null,
  ): void {
    appState.closeMenusAndPanels();
    settingsSection = section;
    appState.settingsTriggerEl = triggerEl;
    appState.settingsOpen = true;
  }

  async function handleNotificationToggle(value: boolean): Promise<void> {
    if (!value) {
      preferences.set('notifyOnComplete', false);
      return;
    }
    if (typeof Notification === 'undefined') {
      notificationPermission = 'unsupported';
      return;
    }
    // requestPermission must run from the click itself; awaiting it is fine, but it cannot be
    // deferred behind another async step or the browser drops the user gesture.
    let permission = Notification.permission;
    if (permission === 'default') permission = await Notification.requestPermission();
    notificationPermission = permission;
    preferences.set('notifyOnComplete', permission === 'granted');
  }

  async function requestNotificationPermission(): Promise<void> {
    if (typeof Notification === 'undefined') {
      notificationPermission = 'unsupported';
      return;
    }
    const permission = await Notification.requestPermission();
    notificationPermission = permission;
    if (permission === 'granted') preferences.set('notifyOnComplete', true);
  }

  function exportConversations(): void {
    const payload = {
      app: 'sofee',
      exportedAt: new Date().toISOString(),
      threads: appState.threads.map((thread) => ({
        id: thread.id,
        title: thread.title,
        mode: thread.mode,
        temporary: thread.isTemporary,
        createdAt: new Date(thread.createdAt).toISOString(),
        messages: thread.messages.map((message) => ({
          id: message.id,
          role: message.role,
          status: message.status,
          text: message.text,
          createdAt: new Date(message.createdAt).toISOString(),
          citations: message.citations ?? [],
          attachmentIds: message.attachmentIds ?? [],
        })),
      })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `sofee-conversations-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  function resetSettings(): void {
    preferences.reset();
    setPaletteId(DEFAULT_PALETTE);
    setLocale('en');
  }

  // Auth transitions drive the backend wiring: sign-in installs persistence hooks, loads the
  // user's conversations and the model catalogue; sign-out tears all of it down and resets the
  // canvas. `lastAuthStatus` is a plain variable (not $state) so this effect only runs on an
  // actual transition, never in a loop.
  let lastAuthStatus: AuthStatus | null = null;
  $effect(() => {
    const status = auth.status;
    if (status === lastAuthStatus) return;
    lastAuthStatus = status;
    if (status === 'signedIn') {
      setConversationSync(true);
      appState.setPersistence({
        threadChanged: (thread) => syncThread(thread),
        messageChanged: (thread, message) => syncMessage(thread, message),
        messageRemoved: (threadId, messageId) => syncMessageRemoved(threadId, messageId),
        threadSettled: (threadId) => threadSettled(threadId),
      });
      appState.setUploader(uploadFile);
      appState.reset();
      void models.load().catch(() => undefined);
      void loadConversations()
        .then((threads) => {
          appState.hydrateThreads(threads);
          void appState.loadRuns(appState.activeThreadId);
        })
        .catch(() => undefined);
    } else if (status === 'signedOut') {
      setConversationSync(false);
      appState.clearPersistence();
      appState.clearUploader();
      models.reset();
      appState.reset();
    }
  });

  async function handleLogout(): Promise<void> {
    appState.settingsOpen = false;
    appState.closeMenusAndPanels();
    await auth.logout();
  }

  // ux-foundations.md §5: "Drafts: Persisted per thread; switching away and back restores the
  // text." `composerValue` is plain, two-way-bound $state (Composer's `value` prop is
  // `$bindable`) rather than a writable $derived: the latter looks tempting here, but Svelte 5
  // rejects a child component's `bind:` write landing on a $derived binding
  // ("state_unsafe_mutation: updating state inside $derived") — writable-derived reassignment is
  // only for the declaring scope itself. So this is the ordinary pair of effects instead: one
  // syncs the store's value in on thread switch, the other writes keystrokes back out.
  // eslint-disable-next-line svelte/prefer-writable-derived -- crashes when reassigned via bind:value from a child; see comment above
  let composerValue = $state(appState.draftFor(appState.activeThreadId));
  $effect(() => {
    composerValue = appState.draftFor(appState.activeThreadId);
  });
  $effect(() => {
    appState.setDraft(appState.activeThreadId, composerValue);
  });

  /** The server sends a stable `statusKey` so the status reads in the interface language; its own
   * `statusText` (Spanish) is only the fallback for statuses without a key. */
  function statusLabel(run: { statusKey: string; statusText: string } | undefined): string {
    switch (run?.statusKey) {
      case 'searching_docs':
        return t('thread.status.searchingDocs');
      case 'searching_web':
        return t('thread.status.searchingWeb');
      default:
        return run?.statusText ?? '';
    }
  }

  function mcpStatusLabel(connected: boolean): string {
    return connected ? t('panel.mcp.connected') : t('panel.mcp.disconnected');
  }

  function threadTitle(thread: Thread): string {
    const firstUser = thread.messages.find((m) => m.role === 'user');
    return firstUser ? firstUser.text.slice(0, 60) : t('menu.new.newChat');
  }

  function guardTemporaryLeave(proceed: () => void): void {
    const thread = appState.activeThread;
    if (thread.isTemporary && thread.messages.length > 0) {
      appState.pendingTemporaryLeave = proceed;
    } else {
      proceed();
    }
  }

  async function selectThread(threadId: string): Promise<void> {
    if (threadId === appState.activeThreadId) return;
    guardTemporaryLeave(async () => {
      const previousId = appState.activeThreadId;
      appState.scrollMemory.save(
        previousId,
        messageListRef?.captureScrollMemory() ?? { scrollTop: 0, topMostMessageId: null },
      );
      appState.switchThread(threadId);
      void appState.loadRuns(threadId);
      await tick();
      messageListRef?.restoreScrollMemory(appState.scrollMemory.restore(threadId));
    });
  }

  async function handleSend(): Promise<void> {
    const threadId = appState.activeThreadId;
    const message = appState.sendMessage(
      threadId,
      composerValue,
      appState.pendingAttachmentStorageIds,
    );
    if (!message) return;
    composerValue = '';
    await tick();
    await messageListRef?.prepareForSend(message.id);
    composerRef?.focus();
  }

  function handleStop(): void {
    appState.stopStreaming(appState.activeThreadId);
  }

  function handleModeChange(mode: ComposerMode): void {
    appState.setMode(appState.activeThreadId, mode);
  }

  async function handleEdit(messageId: string): Promise<void> {
    composerValue = appState.beginEdit(appState.activeThreadId, messageId);
    await tick();
    composerRef?.focus();
  }

  async function handleCopy(messageId: string, text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      copiedMessageId = messageId;
      setTimeout(() => {
        if (copiedMessageId === messageId) copiedMessageId = null;
      }, 1500);
    } catch {
      // Clipboard permission can be denied by the browser/OS; there is no in-thread fallback
      // worth the complexity for a demo build.
    }
  }

  function onStarterSelect(starterText: string): void {
    composerValue = starterText;
    void handleSend();
  }

  function onLongPaste(text: string): void {
    appState.addAttachment(`${t('composer.longPasteTitle')}.txt`, 'file', formatBytes(text.length));
  }

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    return kb < 1024 ? `${Math.round(kb)} KB` : `${(kb / 1024).toFixed(1)} MB`;
  }

  function onCanvasDragOver(event: DragEvent): void {
    event.preventDefault();
    appState.isDropTargetActive = true;
  }
  function onCanvasDragLeave(): void {
    appState.isDropTargetActive = false;
  }
  function onCanvasDrop(event: DragEvent): void {
    event.preventDefault();
    appState.isDropTargetActive = false;
    const files = event.dataTransfer?.files;
    if (!files) return;
    for (const file of Array.from(files)) {
      appState.addAttachment(
        file.name,
        file.type.startsWith('image/') ? 'image' : 'file',
        formatBytes(file.size),
        file,
      );
    }
  }

  let fileInputEl: HTMLInputElement | null = $state(null);

  /** The composer's paperclip and a drop on the canvas end in the same place (§5). */
  function openFilePicker(): void {
    fileInputEl?.click();
  }

  function onFilesPicked(event: Event): void {
    const input = event.currentTarget as HTMLInputElement;
    for (const file of Array.from(input.files ?? [])) {
      appState.addAttachment(
        file.name,
        file.type.startsWith('image/') ? 'image' : 'file',
        formatBytes(file.size),
        file,
      );
    }
    // Cleared so picking the same file twice in a row still fires a change event.
    input.value = '';
  }

  /** §2.2: "home" is a thread with nothing in it yet — the empty-state canvas. */
  let isHome = $derived(appState.activeThread.messages.length === 0);

  // --- Agent surface (roadmap §5, U2–U18) ---------------------------------------------------
  // Every label and number the agent's parts show is built here from the run state, so the
  // components below receive strings and never decide what a status means.
  let agentCtx = $derived<AgentViewContext>({ t: tWide, locale: getLocale() });

  /** Starting questions from the admin for this mode, else the client's own (roadmap U7). */
  let starterTexts = $derived.by(() => {
    const fromServer = appState.startersFor(appState.activeThread.mode, getLocale());
    if (fromServer.length > 0) return [...fromServer];
    return [t('thread.starter1'), t('thread.starter2'), t('thread.starter3')];
  });

  /** Where the Compact and Clear dividers sit in the active thread (roadmap U16). */
  let contextMarkMap = $derived(
    contextMarks(appState.activeThread.messages, {
      summaryThroughSeq: appState.activeThread.summaryThroughSeq,
      contextStartSeq: appState.activeThread.contextStartSeq,
    }),
  );

  let toolRuns = $derived(
    toolRunViews(appState.activeThread.messages, appState.activityByMessage, agentCtx),
  );

  let focusedView = $derived(
    appState.focusedSource ? sourceViews([appState.focusedSource], agentCtx)[0] : undefined,
  );

  let agentFiles = $derived(
    agentFileViews(appState.agentFilesByThread[appState.activeThreadId] ?? [], agentCtx),
  );

  let filePreview = $derived(
    appState.filePreview && appState.filePreview.threadId === appState.activeThreadId
      ? appState.filePreview
      : null,
  );

  /** The waiting state replaces Stop while a plan review is open (roadmap U8). */
  let waitingLabel = $derived(
    appState.waitingReviewMessageId !== null ? t('agent.review.waiting') : null,
  );

  $effect(() => {
    if (auth.status !== 'signedIn') return;
    void appState.loadStarters(appState.activeThread.mode, getLocale());
  });

  function contextMarkLabel(kind: ContextMarkKind): string {
    return kind === 'compacted' ? t('agent.context.compacted') : t('agent.context.cleared');
  }

  async function copyAgentFile(content: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(content);
    } catch {
      // Clipboard permission can be denied; there is no in-panel fallback worth the complexity.
    }
  }

  /** Saves an agent file as Markdown. The file is only a blob in memory until the user clicks. */
  function downloadAgentFile(name: string, content: string): void {
    const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = name.endsWith('.md') ? name : `${name}.md`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  // --- Toolbars -----------------------------------------------------------------------------

  let headerItems = $derived<ToolbarItem[]>([
    {
      id: 'new',
      icon: IconPlus,
      label: t('toolbar.new.label'),
      tooltip: t('toolbar.new.tooltip'),
      active: appState.newMenuOpen,
      ariaHasPopup: 'menu',
      ariaExpanded: appState.newMenuOpen,
      onActivate: (btn) => {
        appState.newMenuAnchor = btn;
        appState.newMenuOpen = !appState.newMenuOpen;
        appState.moreMenuOpen = false;
        appState.contextMoreMenuOpen = false;
      },
    },
    {
      id: 'chats',
      icon: IconChats,
      label: t('toolbar.chats.label'),
      tooltip: t('toolbar.chats.tooltip'),
      active: appState.activePanel === 'chats',
      ariaHasPopup: 'dialog',
      ariaExpanded: appState.activePanel === 'chats',
      onActivate: (btn) => appState.openPanel('chats', btn),
    },
    {
      id: 'projects',
      icon: IconProjects,
      label: t('toolbar.projects.label'),
      tooltip: t('toolbar.projects.tooltip'),
      active: appState.activePanel === 'projects',
      ariaHasPopup: 'dialog',
      ariaExpanded: appState.activePanel === 'projects',
      onActivate: (btn) => appState.openPanel('projects', btn),
    },
    {
      id: 'more',
      icon: IconMore,
      label: t('toolbar.more.label'),
      tooltip: t('toolbar.more.tooltip'),
      active: appState.moreMenuOpen,
      ariaHasPopup: 'menu',
      ariaExpanded: appState.moreMenuOpen,
      onActivate: (btn) => {
        appState.moreMenuAnchor = btn;
        appState.moreMenuOpen = !appState.moreMenuOpen;
        appState.moreMenuView = 'root';
        appState.newMenuOpen = false;
        appState.contextMoreMenuOpen = false;
      },
    },
  ]);

  let contextItems = $derived<ToolbarItem[]>([
    {
      id: 'toolCalls',
      icon: IconToolCalls,
      // The visible badge (design-system.md §6) is aria-hidden by design — the accessible name
      // carries the count instead, via the plural message, rather than leaving a screen reader
      // user to discover it only by opening the panel.
      label:
        appState.toolCalls.length > 0
          ? t('toolbar.toolCalls.count', { count: appState.toolCalls.length })
          : t('toolbar.toolCalls.label'),
      tooltip: t('toolbar.toolCalls.tooltip'),
      badge: appState.toolCalls.length,
      active: appState.activePanel === 'toolCalls',
      ariaHasPopup: 'dialog',
      ariaExpanded: appState.activePanel === 'toolCalls',
      onActivate: (btn) => appState.openPanel('toolCalls', btn),
    },
    {
      id: 'mcp',
      icon: IconMcp,
      label:
        appState.mcpServers.filter((s) => s.connected).length > 0
          ? t('toolbar.mcp.count', { count: appState.mcpServers.filter((s) => s.connected).length })
          : t('toolbar.mcp.label'),
      tooltip: t('toolbar.mcp.tooltip'),
      badge: appState.mcpServers.filter((s) => s.connected).length,
      active: appState.activePanel === 'mcp',
      ariaHasPopup: 'dialog',
      ariaExpanded: appState.activePanel === 'mcp',
      onActivate: (btn) => appState.openPanel('mcp', btn),
    },
    {
      id: 'attachments',
      icon: IconAttachments,
      label:
        appState.attachments.length > 0
          ? t('toolbar.attachments.count', { count: appState.attachments.length })
          : t('toolbar.attachments.label'),
      tooltip: t('toolbar.attachments.tooltip'),
      badge: appState.attachments.length,
      active: appState.activePanel === 'attachments',
      ariaHasPopup: 'dialog',
      ariaExpanded: appState.activePanel === 'attachments',
      onActivate: (btn) => appState.openPanel('attachments', btn),
    },
    {
      id: 'contextMore',
      icon: IconMore,
      label: t('toolbar.more.label'),
      tooltip: t('toolbar.more.tooltip'),
      active: appState.contextMoreMenuOpen,
      ariaHasPopup: 'menu',
      ariaExpanded: appState.contextMoreMenuOpen,
      onActivate: (btn) => {
        appState.contextMoreMenuAnchor = btn;
        appState.contextMoreMenuOpen = !appState.contextMoreMenuOpen;
        appState.newMenuOpen = false;
        appState.moreMenuOpen = false;
      },
    },
  ]);

  // --- Menus -------------------------------------------------------------------------------

  let newMenuItems = $derived<MenuItemConfig[]>([
    {
      id: 'new-chat',
      label: t('menu.new.newChat'),
      icon: IconChats,
      onActivate: () => guardTemporaryLeave(() => appState.createThread(false)),
    },
    {
      id: 'new-project',
      label: t('menu.new.newProject'),
      icon: IconProjects,
      onActivate: () => guardTemporaryLeave(() => appState.createProject()),
    },
    {
      id: 'new-temp',
      label: t('menu.new.newTemporaryChat'),
      icon: IconChats,
      onActivate: () => guardTemporaryLeave(() => appState.createThread(true)),
    },
  ]);

  let moreMenuItems = $derived<MenuItemConfig[]>(buildMoreMenuItems());

  function buildMoreMenuItems(): MenuItemConfig[] {
    if (appState.moreMenuView === 'language') {
      return [
        {
          id: 'back',
          label: t('menu.more.back'),
          keepOpen: true,
          onActivate: () => (appState.moreMenuView = 'root'),
        },
        {
          id: 'lang-en',
          label: t('language.en'),
          checked: getLocale() === 'en',
          keepOpen: true,
          onActivate: () => {
            setLocale('en');
            appState.moreMenuView = 'root';
          },
        },
        {
          id: 'lang-es',
          label: t('language.es'),
          checked: getLocale() === 'es',
          keepOpen: true,
          onActivate: () => {
            setLocale('es');
            appState.moreMenuView = 'root';
          },
        },
      ];
    }
    if (appState.moreMenuView === 'palette') {
      return [
        {
          id: 'back',
          label: t('menu.more.back'),
          keepOpen: true,
          onActivate: () => (appState.moreMenuView = 'root'),
        },
        ...listPalettes().map((palette) => ({
          id: `palette-${palette.id}`,
          label: palette.label,
          checked: getPaletteId() === palette.id,
          keepOpen: true,
          onActivate: () => {
            setPaletteId(palette.id);
            appState.moreMenuView = 'root';
          },
        })),
      ];
    }
    return [
      {
        id: 'settings',
        label: t('menu.more.settings'),
        icon: IconSettings,
        onActivate: () => openSettings('general', appState.moreMenuAnchor),
      },
      {
        id: 'language',
        label: t('menu.more.language'),
        icon: IconGlobe,
        keepOpen: true,
        onActivate: () => (appState.moreMenuView = 'language'),
      },
      {
        id: 'palette',
        label: t('menu.more.palette'),
        icon: IconPalette,
        keepOpen: true,
        onActivate: () => (appState.moreMenuView = 'palette'),
      },
      {
        id: 'shortcuts',
        label: t('menu.more.shortcuts'),
        icon: IconKeyboard,
        onActivate: () => {
          appState.shortcutsTriggerEl = appState.moreMenuAnchor;
          appState.shortcutsOpen = true;
          appState.moreMenuOpen = false;
        },
      },
      {
        id: 'logout',
        label: t('menu.more.logout'),
        onActivate: () => void handleLogout(),
      },
    ];
  }

  let contextMoreMenuItems = $derived<MenuItemConfig[]>([
    {
      id: 'compact',
      label: t('menu.context.compact'),
      icon: IconCompact,
      onActivate: () => void appState.compactContext(appState.activeThreadId),
    },
    {
      id: 'clear',
      label: t('menu.context.clear'),
      icon: IconTrash,
      destructive: true,
      onActivate: () => void appState.clearContext(appState.activeThreadId),
    },
  ]);

  let commandPaletteCommands = $derived<MenuItemConfig[]>([
    {
      id: 'cmd-new-chat',
      label: t('commandPalette.newChat'),
      icon: IconChats,
      onActivate: () => guardTemporaryLeave(() => appState.createThread(false)),
    },
    {
      id: 'cmd-new-project',
      label: t('commandPalette.newProject'),
      icon: IconProjects,
      onActivate: () => guardTemporaryLeave(() => appState.createProject()),
    },
    {
      id: 'cmd-new-temp',
      label: t('commandPalette.newTemporaryChat'),
      icon: IconChats,
      onActivate: () => guardTemporaryLeave(() => appState.createThread(true)),
    },
    {
      id: 'cmd-toggle-chats',
      label: t('commandPalette.toggleChats'),
      icon: IconChats,
      onActivate: () => (appState.activePanel = appState.activePanel === 'chats' ? null : 'chats'),
    },
    {
      id: 'cmd-toggle-projects',
      label: t('commandPalette.toggleProjects'),
      icon: IconProjects,
      onActivate: () =>
        (appState.activePanel = appState.activePanel === 'projects' ? null : 'projects'),
    },
    {
      id: 'cmd-settings',
      label: t('commandPalette.openSettings'),
      icon: IconSettings,
      onActivate: () => openSettings('general'),
    },
    {
      id: 'cmd-shortcuts',
      label: t('commandPalette.openShortcuts'),
      icon: IconKeyboard,
      onActivate: () => (appState.shortcutsOpen = true),
    },
  ]);

  function closePanel(panel: PanelId): void {
    if (appState.activePanel === panel) appState.activePanel = null;
  }

  // --- Global keyboard (ux-foundations.md §6) --------------------------------------------

  function moveMessageFocus(direction: 1 | -1): void {
    const articles = Array.from(document.querySelectorAll<HTMLElement>('[data-message-id]'));
    if (articles.length === 0) return;
    const currentIndex = articles.findIndex((el) => el === document.activeElement);
    const nextIndex =
      currentIndex === -1
        ? direction === 1
          ? 0
          : articles.length - 1
        : Math.min(Math.max(currentIndex + direction, 0), articles.length - 1);
    articles[nextIndex]?.focus();
  }

  function onGlobalKeydown(event: KeyboardEvent): void {
    if (auth.status !== 'signedIn') return;
    const mod = event.metaKey || event.ctrlKey;

    if (mod && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      appState.commandPaletteOpen = true;
      return;
    }
    if (mod && event.shiftKey && event.key.toLowerCase() === 'n') {
      event.preventDefault();
      guardTemporaryLeave(() => appState.createThread(true));
      return;
    }
    if (mod && event.key.toLowerCase() === 'n') {
      event.preventDefault();
      guardTemporaryLeave(() => appState.createThread(false));
      return;
    }
    if (mod && event.key.toLowerCase() === 'j') {
      event.preventDefault();
      appState.activePanel = appState.activePanel === 'chats' ? null : 'chats';
      return;
    }
    if (mod && event.key === ',') {
      event.preventDefault();
      if (appState.settingsOpen) appState.settingsOpen = false;
      else openSettings('general');
      return;
    }
    if (mod && event.key === '/') {
      event.preventDefault();
      appState.shortcutsOpen = !appState.shortcutsOpen;
      return;
    }
    if (event.key === 'Escape') {
      if (appState.commandPaletteOpen) {
        appState.commandPaletteOpen = false;
      } else if (appState.settingsOpen) {
        appState.settingsOpen = false;
      } else if (appState.shortcutsOpen) {
        appState.shortcutsOpen = false;
      } else if (appState.pendingTemporaryLeave) {
        appState.pendingTemporaryLeave = null;
      } else if (appState.activePanel) {
        appState.activePanel = null;
      } else if (appState.newMenuOpen || appState.moreMenuOpen || appState.contextMoreMenuOpen) {
        appState.newMenuOpen = false;
        appState.moreMenuOpen = false;
        appState.contextMoreMenuOpen = false;
      } else if (appState.isActiveThreadBusy) {
        appState.stopStreaming(appState.activeThreadId);
      }
      return;
    }
    if (
      event.key === 'ArrowUp' &&
      (event.target as HTMLElement)?.tagName === 'TEXTAREA' &&
      composerValue === ''
    ) {
      const lastUser = [...appState.activeThread.messages].reverse().find((m) => m.role === 'user');
      if (lastUser) {
        event.preventDefault();
        void handleEdit(lastUser.id);
      }
      return;
    }
    if (event.altKey && event.key === 'ArrowUp') {
      event.preventDefault();
      moveMessageFocus(-1);
    } else if (event.altKey && event.key === 'ArrowDown') {
      event.preventDefault();
      moveMessageFocus(1);
    }
  }

  $effect(() => {
    window.addEventListener('keydown', onGlobalKeydown);
    return () => window.removeEventListener('keydown', onGlobalKeydown);
  });

  $effect(() => {
    function onBeforeUnload(event: BeforeUnloadEvent): void {
      if (appState.activeThread.isTemporary && appState.activeThread.messages.length > 0) {
        event.preventDefault();
        event.returnValue = '';
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  });
</script>

{#if auth.status === 'bootstrapping'}
  <div class="boot-screen">{t('auth.bootstrapping')}</div>
{:else if auth.status === 'signedOut'}
  <AuthScreen />
{:else}
  <input
    bind:this={fileInputEl}
    type="file"
    multiple
    class="visually-hidden-input"
    tabindex="-1"
    aria-hidden="true"
    onchange={onFilesPicked}
  />

  <a class="skip-link" href="#composer">{t('app.skipToComposer')}</a>

  <div class="shell">
    <main
      class="canvas"
      ondragover={onCanvasDragOver}
      ondragleave={onCanvasDragLeave}
      ondrop={onCanvasDrop}
    >
      <DottedCanvas />

      {#if appState.isDropTargetActive}
        <div class="drop-overlay">{t('composer.dropHint')}</div>
      {/if}

      <!-- §2.1: the navigation cluster floats over the canvas as a header rather than occupying
         a column, so the canvas is the full width of the window under it. -->
      <div class="header-dock">
        <IconToolbar
          orientation="horizontal"
          label={t('toolbar.header.label')}
          items={headerItems}
        />
      </div>

      <!-- §2.2: context management only has anything to say once there is a conversation to
         manage, so it is absent on the home canvas. Its gutter is reserved either way (see
         .canvas below), so arriving here on send reflows nothing. -->
      {#if !isHome}
        <div class="context-dock">
          <IconToolbar
            orientation="vertical"
            label={t('toolbar.context.label')}
            items={contextItems}
          >
            <ContextMeter
              percent={appState.contextPercent}
              label={t('toolbar.contextMeter.label')}
              valueText={t('toolbar.contextMeter.value', {
                percent: Math.round(appState.contextPercent),
              })}
            />
          </IconToolbar>
        </div>
      {/if}

      <div class="canvas-content">
        {#if appState.activeThread.isTemporary}
          <div class="canvas-header">
            <span class="temporary-badge">{t('temporaryChat.badge')}</span>
          </div>
        {/if}

        <MessageList
          bind:this={messageListRef}
          controller={appState.activeScrollController}
          t={tWide}
          items={appState.activeThread.messages}
        >
          {#snippet empty()}
            <EmptyState t={tWide} starters={starterTexts} {onStarterSelect} />
          {/snippet}
          {#snippet item(message)}
            {@const run =
              message.role === 'assistant' ? appState.activityByMessage[message.id] : undefined}
            {@const plan = run ? planView(run, agentCtx) : null}
            {@const review = run?.interrupt && plan ? plan.steps : null}
            {@const subagents = run ? subagentViews(run.subagents, agentCtx) : []}
            {@const sources =
              message.role === 'assistant' && message.citations && message.citations.length > 0
                ? sourceViews(message.citations, agentCtx)
                : []}
            {@const marks = contextMarkMap[message.id]}
            {#each marks?.before ?? [] as kind (kind)}
              <ContextDivider label={contextMarkLabel(kind)} />
            {/each}
            <MessageItem
              id={message.id}
              role={message.role}
              status={message.status}
              text={message.text}
              citations={appState.citationsFor(message)}
              errorCode={message.errorCode}
              errorResetLabel={message.errorResetAt
                ? formatClockTime(message.errorResetAt)
                : undefined}
              statusText={statusLabel(run)}
              feedback={appState.feedback[message.id]}
              copied={copiedMessageId === message.id}
              t={tWide}
              onCopy={() => handleCopy(message.id, message.text)}
              onEdit={message.role === 'user' ? () => handleEdit(message.id) : undefined}
              onRegenerate={message.role === 'assistant' && message.status === 'complete'
                ? () => appState.regenerate(appState.activeThreadId, message.id)
                : undefined}
              onGoodResponse={message.role === 'assistant'
                ? () => appState.setFeedback(appState.activeThreadId, message.id, 'good')
                : undefined}
              onBadResponse={message.role === 'assistant'
                ? () => appState.setFeedback(appState.activeThreadId, message.id, 'bad')
                : undefined}
              onRetry={message.status === 'error'
                ? () => appState.retryMessage(appState.activeThreadId, message.id)
                : undefined}
              onChangeModel={() => openSettings('assistant')}
              onContinue={message.status === 'stopped'
                ? () => appState.continueMessage(appState.activeThreadId, message.id)
                : undefined}
              onOpenSource={(citation, trigger) => appState.showSource(citation, trigger)}
            >
              {#snippet activity()}
                {#if plan && !review}
                  <PlanBlock {plan} t={tWide} />
                {:else if !plan && run && isActiveRunStatus(run.status) && run.sources.length > 0}
                  <p class="live-sources">
                    {t('agent.sources.live', { count: run.sources.length })}
                  </p>
                {/if}
                {#if subagents.length > 0}
                  <SubagentCards
                    {subagents}
                    heading={t('agent.subagents.heading', { count: subagents.length })}
                    t={tWide}
                  />
                {/if}
                {#if review && run}
                  <PlanReview
                    steps={review}
                    t={tWide}
                    onApprove={() => void appState.approvePlan(message.id)}
                    onEdit={(steps) => void appState.editPlan(message.id, steps)}
                    onSkipReview={() => void appState.skipPlanReview(message.id)}
                    onStop={handleStop}
                  />
                {/if}
              {/snippet}
              {#snippet footer()}
                {#if preferences.values.showSources && sources.length > 0}
                  <SourceList
                    {sources}
                    t={tWide}
                    onOpen={(citation, trigger) => appState.showSource(citation, trigger)}
                  />
                {/if}
                {#if preferences.values.showDirections && run && run.directions.length > 0}
                  <DirectionChips
                    directions={run.directions}
                    t={tWide}
                    onPick={(text) => onStarterSelect(text)}
                  />
                {/if}
                {#if preferences.values.showQuiz && run && run.quiz.length > 0}
                  <QuizBlock items={run.quiz} t={tWide} />
                {/if}
              {/snippet}
            </MessageItem>
            {#each marks?.after ?? [] as kind (kind)}
              <ContextDivider label={contextMarkLabel(kind)} />
            {/each}
          {/snippet}
        </MessageList>

        <div class="composer-dock" id="composer">
          <Composer
            bind:this={composerRef}
            bind:value={composerValue}
            mode={appState.activeThread.mode}
            isStreaming={appState.isActiveThreadBusy && waitingLabel === null}
            {waitingLabel}
            isTemporary={appState.activeThread.isTemporary}
            invertSendKey={preferences.values.invertSendKey}
            pinnedSourceCount={appState.pinnedSourceCount}
            t={tWide}
            onSend={handleSend}
            onStop={handleStop}
            onModeChange={handleModeChange}
            onAttach={openFilePicker}
            {onLongPaste}
          />
        </div>
      </div>
    </main>
  </div>

  <Menu
    items={newMenuItems}
    label={t('toolbar.new.label')}
    open={appState.newMenuOpen}
    anchor={appState.newMenuAnchor}
    align="left"
    onClose={() => (appState.newMenuOpen = false)}
  />
  <Menu
    items={moreMenuItems}
    label={t('toolbar.more.label')}
    open={appState.moreMenuOpen}
    anchor={appState.moreMenuAnchor}
    align="left"
    onClose={() => (appState.moreMenuOpen = false)}
  />
  <Menu
    items={contextMoreMenuItems}
    label={t('toolbar.more.label')}
    open={appState.contextMoreMenuOpen}
    anchor={appState.contextMoreMenuAnchor}
    align="right"
    onClose={() => (appState.contextMoreMenuOpen = false)}
  />

  <DropdownPanel
    open={appState.activePanel === 'chats'}
    titleText={t('panel.chats.title')}
    closeLabel={t('panel.close')}
    triggerEl={appState.panelTriggerEl}
    onClose={() => closePanel('chats')}
  >
    <div class="panel-list">
      {#each appState.threads as thread (thread.id)}
        <button
          type="button"
          class="panel-row"
          class:current={thread.id === appState.activeThreadId}
          onclick={() => selectThread(thread.id)}
        >
          <span class="panel-row-title">{threadTitle(thread)}</span>
          {#if thread.isTemporary}<span class="panel-row-tag">{t('temporaryChat.badge')}</span>{/if}
        </button>
      {:else}
        <p class="panel-empty">{t('panel.chats.empty')}</p>
      {/each}
    </div>
  </DropdownPanel>

  <DropdownPanel
    open={appState.activePanel === 'projects'}
    titleText={t('panel.projects.title')}
    closeLabel={t('panel.close')}
    triggerEl={appState.panelTriggerEl}
    onClose={() => closePanel('projects')}
  >
    <div class="panel-list">
      {#each appState.projects as project (project.id)}
        <div class="panel-row static">
          <span class="panel-row-title">{project.name}</span>
          <span class="panel-row-tag">{project.threadIds.length}</span>
        </div>
      {:else}
        <p class="panel-empty">{t('panel.projects.empty')}</p>
      {/each}
    </div>
  </DropdownPanel>

  <OverlayPanel
    open={appState.activePanel === 'toolCalls'}
    titleText={t('panel.toolCalls.title')}
    closeLabel={t('panel.close')}
    triggerEl={appState.panelTriggerEl}
    onClose={() => closePanel('toolCalls')}
  >
    {#if toolRuns.length === 0}
      <p class="panel-empty">{t('panel.toolCalls.empty')}</p>
    {:else}
      <ToolTimeline runs={toolRuns} />
    {/if}
  </OverlayPanel>

  <OverlayPanel
    open={appState.activePanel === 'mcp'}
    titleText={t('panel.mcp.title')}
    closeLabel={t('panel.close')}
    triggerEl={appState.panelTriggerEl}
    onClose={() => closePanel('mcp')}
  >
    <div class="panel-list">
      {#each appState.mcpServers as server (server.id)}
        <div class="panel-row static">
          <span class="panel-row-title">{server.name}</span>
          <span class="panel-row-tag">{mcpStatusLabel(server.connected)}</span>
        </div>
      {:else}
        <p class="panel-empty">{t('panel.mcp.empty')}</p>
      {/each}
    </div>
  </OverlayPanel>

  <OverlayPanel
    open={appState.activePanel === 'attachments'}
    titleText={t('panel.attachments.title')}
    closeLabel={t('panel.close')}
    triggerEl={appState.panelTriggerEl}
    onClose={() => closePanel('attachments')}
  >
    {#if focusedView}
      <section class="source-focus" aria-label={focusedView.title}>
        <p class="panel-row-tag">{focusedView.meta}</p>
        <p class="source-title">{focusedView.title}</p>
        {#if focusedView.snippet}<p class="source-snippet">{focusedView.snippet}</p>{/if}
        <p class="panel-row-tag">{t('agent.source.openedFrom')}</p>
      </section>
    {/if}
    <div class="panel-list">
      {#each appState.attachments as attachment (attachment.id)}
        <div
          class="panel-row static"
          class:current={attachment.storageId !== undefined &&
            attachment.storageId === appState.focusedSource?.ref}
        >
          <span class="panel-row-title">{attachment.name}</span>
          {#if attachment.uploading}
            <span class="panel-row-tag">{t('panel.attachments.uploading')}</span>
          {:else if attachment.error}
            <span class="panel-row-tag"
              >{attachment.errorReason === 'tooLarge'
                ? t('panel.attachments.errorTooLarge')
                : t('panel.attachments.error')}</span
            >
          {:else if attachment.sizeLabel}
            <span class="panel-row-tag">{attachment.sizeLabel}</span>
          {/if}
        </div>
      {:else}
        <p class="panel-empty">{t('panel.attachments.empty')}</p>
      {/each}
    </div>
    <div class="panel-section">
      <AgentFiles
        files={agentFiles}
        preview={filePreview}
        t={tWide}
        onOpen={(path) => void appState.openAgentFile(appState.activeThreadId, path)}
        onBack={() => appState.closeAgentFile()}
        onCopy={(content) => void copyAgentFile(content)}
        onDownload={downloadAgentFile}
      />
    </div>
  </OverlayPanel>

  {#if appState.settingsOpen}
    <SettingsDialog
      t={tWide}
      triggerEl={appState.settingsTriggerEl}
      section={settingsSection}
      onChangeSection={(section) => (settingsSection = section)}
      onClose={() => (appState.settingsOpen = false)}
      invertSendKey={preferences.values.invertSendKey}
      onChangeInvertSendKey={(value) => preferences.set('invertSendKey', value)}
      palettes={paletteOptions}
      selectedPaletteId={paletteId}
      onChangePalette={(id) => setPaletteId(id as PaletteId)}
      locale={getLocale()}
      onChangeLocale={(next) => setLocale(next)}
      motion={preferences.values.motion}
      onChangeMotion={(value) => preferences.set('motion', value)}
      defaultMode={preferences.values.defaultMode}
      onChangeDefaultMode={(mode) => preferences.set('defaultMode', mode)}
      showSources={preferences.values.showSources}
      onChangeShowSources={(value) => preferences.set('showSources', value)}
      showDirections={preferences.values.showDirections}
      onChangeShowDirections={(value) => preferences.set('showDirections', value)}
      showQuiz={preferences.values.showQuiz}
      onChangeShowQuiz={(value) => preferences.set('showQuiz', value)}
      modelOptions={models.options}
      selectedModelId={models.selectedId}
      onChangeModel={(id) => models.select(id)}
      notifyOnComplete={preferences.values.notifyOnComplete &&
        notificationPermission === 'granted'}
      onChangeNotifyOnComplete={(value) => void handleNotificationToggle(value)}
      notificationPermission={notificationPermission}
      onRequestNotificationPermission={() => void requestNotificationPermission()}
      user={settingsUser}
      hasConversations={hasConversations}
      onExportConversations={exportConversations}
      onLogout={() => void handleLogout()}
      version={appVersion}
      sourceUrl={sourceUrl}
      onResetSettings={resetSettings}
    />
  {/if}

  {#if appState.shortcutsOpen}
    <ShortcutsDialog
      t={tWide}
      triggerEl={appState.shortcutsTriggerEl}
      onClose={() => (appState.shortcutsOpen = false)}
    />
  {/if}

  {#if appState.commandPaletteOpen}
    <CommandPalette
      t={tWide}
      commands={commandPaletteCommands}
      onClose={() => (appState.commandPaletteOpen = false)}
    />
  {/if}

  {#if appState.pendingTemporaryLeave}
    <ConfirmDialog
      titleText={t('temporaryChat.confirmTitle')}
      bodyText={t('temporaryChat.confirmBody')}
      confirmLabel={t('temporaryChat.confirmLeave')}
      cancelLabel={t('temporaryChat.confirmStay')}
      onConfirm={() => {
        const proceed = appState.pendingTemporaryLeave;
        appState.pendingTemporaryLeave = null;
        proceed?.();
      }}
      onCancel={() => (appState.pendingTemporaryLeave = null)}
    />
  {/if}

  <LiveRegion message={appState.liveMessage} />
{/if}

<style>
  .shell {
    flex: 1;
    min-height: 0;
    display: flex;
  }

  .boot-screen {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--p-mut);
    font-size: 14px;
  }

  .canvas {
    position: relative;
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    /* Both gutters are reserved unconditionally, including on the home canvas where the
       context toolbar is absent: showing it on send must not move a single pixel of the
       conversation, which is the whole point of §3.2's top-anchored hold. */
    padding-block-start: var(--toolbar-inset-block);
    padding-inline: var(--toolbar-gutter);
  }

  .header-dock,
  .context-dock {
    position: absolute;
    top: var(--space-4);
    z-index: 5;
  }

  .header-dock {
    left: var(--space-4);
  }

  .context-dock {
    right: var(--space-4);
  }

  @media (max-width: 640px) {
    .canvas {
      padding-inline: var(--space-2);
    }

    /* The context toolbar floats over the right edge: once a conversation shows it, keep the
       text clear of it instead of letting the toolbar cover the end of every line. */
    .canvas:has(.context-dock) {
      padding-inline-end: var(--toolbar-gutter);
    }

    /* The composer sits below the toolbar, so it keeps the full width. */
    .canvas:has(.context-dock) .composer-dock {
      margin-inline-end: calc(var(--space-2) - var(--toolbar-gutter));
    }
  }

  .canvas-content {
    position: relative;
    z-index: 1;
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .canvas-header {
    display: flex;
    justify-content: center;
    padding: var(--space-3) 0 0;
  }

  .temporary-badge {
    padding: 4px var(--space-3);
    border-radius: var(--radius-capsule);
    border: 1px dashed var(--p-line-2);
    color: var(--p-mut);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .composer-dock {
    padding: var(--space-4);
  }

  .visually-hidden-input {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
    border: 0;
  }

  .drop-overlay {
    position: absolute;
    inset: var(--space-3);
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px dashed var(--p-acc);
    border-radius: var(--radius-panel);
    background: color-mix(in oklab, var(--p-acc) 10%, transparent);
    color: var(--p-ink);
    font-size: 14px;
    pointer-events: none;
  }

  .panel-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .panel-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--target-min);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: 1px solid var(--p-line);
    background: var(--p-surf);
    color: var(--p-ink);
    font: inherit;
    font-size: 13px;
    text-align: left;
    cursor: pointer;
  }

  .panel-row.static {
    cursor: default;
  }

  .panel-row:not(.static):hover {
    border-color: var(--p-line-2);
  }

  .panel-row.current {
    border-color: var(--p-acc);
  }

  .panel-row:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .panel-row-title {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .panel-row-tag {
    flex-shrink: 0;
    color: var(--p-mut);
    font-size: 11px;
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
  }

  .panel-empty {
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.6;
  }

  .panel-section {
    margin-top: var(--space-4);
    padding-top: var(--space-4);
    border-top: 1px solid var(--p-line);
  }

  .source-focus {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-bottom: var(--space-4);
    padding: var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: 1px solid var(--p-line-2);
    background: var(--p-surf-2);
  }

  .source-title {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--p-ink);
    overflow-wrap: anywhere;
  }

  .source-snippet {
    margin: 0;
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  /* The live source count of a run that has not written a plan (roadmap U4). */
  .live-sources {
    margin: 0;
    color: var(--p-mut);
    font-size: 12px;
  }
</style>
