<!--
  Settings, ux-foundations.md §2.4: a large two-pane modal rather than a cramped single column.
  A vertical category rail on the left, one scrolling panel on the right, immediate-apply
  controls (no Save/Cancel), and a narrow-screen layout where the rail becomes a horizontal strip.
  Every visible string comes from the catalogue; palette swatches are data from packages/tokens.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import type { ComposerMode, Locale, Translate } from '@sofee/core';
  import Dialog from './Dialog.svelte';
  import { scrollbars } from '../actions/scrollbars.js';
  import { shortcutRows } from '../shortcuts.js';
  import type { SettingsPalette, SettingsSection, SettingsUser } from '../types.js';

  interface Props {
    t: Translate;
    triggerEl?: HTMLElement | null;
    section: SettingsSection;
    onChangeSection: (section: SettingsSection) => void;
    onClose: () => void;
    invertSendKey: boolean;
    onChangeInvertSendKey: (value: boolean) => void;
    palettes: readonly SettingsPalette[];
    selectedPaletteId: string;
    onChangePalette: (id: string) => void;
    locale: Locale;
    onChangeLocale: (locale: Locale) => void;
    motion: 'system' | 'reduce';
    onChangeMotion: (motion: 'system' | 'reduce') => void;
    defaultMode: ComposerMode;
    onChangeDefaultMode: (mode: ComposerMode) => void;
    showSources: boolean;
    onChangeShowSources: (value: boolean) => void;
    showDirections: boolean;
    onChangeShowDirections: (value: boolean) => void;
    showQuiz: boolean;
    onChangeShowQuiz: (value: boolean) => void;
    modelOptions?: readonly { id: string; label: string }[];
    selectedModelId?: string | null;
    onChangeModel: (id: string) => void;
    notifyOnComplete: boolean;
    onChangeNotifyOnComplete: (value: boolean) => void;
    notificationPermission: 'default' | 'denied' | 'granted' | 'unsupported';
    onRequestNotificationPermission: () => void;
    user?: SettingsUser | null;
    hasConversations: boolean;
    onExportConversations: () => void;
    onLogout: () => void;
    version: string;
    sourceUrl: string;
    onResetSettings: () => void;
  }

  let {
    t,
    triggerEl = null,
    section,
    onChangeSection,
    onClose,
    invertSendKey,
    onChangeInvertSendKey,
    palettes,
    selectedPaletteId,
    onChangePalette,
    locale,
    onChangeLocale,
    motion,
    onChangeMotion,
    defaultMode,
    onChangeDefaultMode,
    showSources,
    onChangeShowSources,
    showDirections,
    onChangeShowDirections,
    showQuiz,
    onChangeShowQuiz,
    modelOptions = [],
    selectedModelId = null,
    onChangeModel,
    notifyOnComplete,
    onChangeNotifyOnComplete,
    notificationPermission,
    onRequestNotificationPermission,
    user = null,
    hasConversations,
    onExportConversations,
    onLogout,
    version,
    sourceUrl,
    onResetSettings,
  }: Props = $props();

  const sections: readonly { id: SettingsSection; label: string }[] = [
    { id: 'general', label: 'settings.nav.general' },
    { id: 'assistant', label: 'settings.nav.assistant' },
    { id: 'chats', label: 'settings.nav.chats' },
    { id: 'notifications', label: 'settings.nav.notifications' },
    { id: 'shortcuts', label: 'settings.nav.shortcuts' },
    { id: 'account', label: 'settings.nav.account' },
    { id: 'about', label: 'settings.nav.about' },
  ];

  const modes: readonly { id: ComposerMode; label: string }[] = [
    { id: 'learn', label: 'settings.assistant.modeLearn' },
    { id: 'research', label: 'settings.assistant.modeResearch' },
    { id: 'explore', label: 'settings.assistant.modeExplore' },
  ];

  let shortcuts = $derived(shortcutRows(t));
  let contentEl: HTMLDivElement | null = $state(null);
  let resetDone = $state(false);
  // The rail is vertical on the wide shell and a horizontal strip below 760px (CSS below).
  // Mirror that in the tablist semantics so a screen reader announces the real axis.
  let isNarrow = $state(false);

  onMount(() => {
    const query = window.matchMedia('(max-width: 760px)');
    isNarrow = query.matches;
    const onChange = (event: MediaQueryListEvent): void => {
      isNarrow = event.matches;
    };
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  });

  let initials = $derived.by(() => {
    const name = user?.displayName.trim() || user?.email || '';
    const parts = name.split(/\s+/).filter(Boolean);
    return `${parts[0]?.[0] ?? ''}${parts[1]?.[0] ?? ''}`;
  });

  function onNavKeydown(event: KeyboardEvent): void {
    const tabs = Array.from(
      (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="tab"]'),
    );
    if (tabs.length === 0) return;
    const current = tabs.findIndex((tab) => tab === document.activeElement);
    let next: number;
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight')
      next = current < 0 ? 0 : (current + 1) % tabs.length;
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft')
      next = current <= 0 ? tabs.length - 1 : current - 1;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;

    event.preventDefault();
    const target = tabs[next];
    if (!target) return;
    target.focus();
    const nextSection = target.dataset.section as SettingsSection | undefined;
    if (nextSection) onChangeSection(nextSection);
  }

  function permissionLabel(): string {
    if (notificationPermission === 'granted') return t('settings.notifications.permissionGranted');
    if (notificationPermission === 'denied') return t('settings.notifications.permissionDenied');
    if (notificationPermission === 'unsupported')
      return t('settings.notifications.permissionUnsupported');
    return t('settings.notifications.permissionDefault');
  }

  function handleReset(): void {
    onResetSettings();
    resetDone = true;
  }

  $effect(() => {
    // Read `section` so this runs when the category changes, and return the scroll pocket to the
    // top: settings categories are independent pages, not one continuous document. The reset
    // confirmation is tied to the visit that produced it, not to every later visit to About.
    void section;
    resetDone = false;
    if (contentEl) contentEl.scrollTop = 0;
  });
</script>

{#snippet toggleRow(
  id: string,
  title: string,
  hint: string,
  checked: boolean,
  onChange: (value: boolean) => void,
  disabled: boolean = false,
)}
  <div class="row">
    <div class="row-copy">
      <p class="row-title" id={`${id}-label`}>{title}</p>
      <p class="row-hint" id={`${id}-hint`}>{hint}</p>
    </div>
    <button
      type="button"
      class="switch"
      class:on={checked}
      role="switch"
      aria-checked={checked}
      aria-labelledby={`${id}-label`}
      aria-describedby={`${id}-hint`}
      {disabled}
      onclick={() => onChange(!checked)}
    >
      <span class="switch-track" aria-hidden="true">
        <span class="switch-thumb"></span>
      </span>
    </button>
  </div>
{/snippet}

<Dialog
  titleText={t('settings.title')}
  {triggerEl}
  {onClose}
  size="lg"
  showClose
  closeLabel={t('settings.close')}
>
  <div class="settings-body">
    <div
      class="settings-nav"
      role="tablist"
      tabindex="-1"
      aria-label={t('settings.navLabel')}
      aria-orientation={isNarrow ? 'horizontal' : 'vertical'}
      onkeydown={onNavKeydown}
      use:scrollbars={{ autoHide: 'leave' }}
    >
      {#each sections as item (item.id)}
        <button
          type="button"
          role="tab"
          id={`settings-tab-${item.id}`}
          aria-controls={`settings-panel-${item.id}`}
          aria-selected={section === item.id}
          tabindex={section === item.id ? 0 : -1}
          class="nav-item"
          class:active={section === item.id}
          data-section={item.id}
          data-autofocus={section === item.id ? '' : undefined}
          onclick={() => onChangeSection(item.id)}
        >
          {t(item.label)}
        </button>
      {/each}
    </div>

    <div
      class="settings-content"
      bind:this={contentEl}
      use:scrollbars={{ autoHide: 'leave' }}
    >
      {#each sections as item (item.id)}
        <div
          id={`settings-panel-${item.id}`}
          class="settings-panel"
          role="tabpanel"
          aria-labelledby={`settings-tab-${item.id}`}
          hidden={section !== item.id}
          tabindex="0"
        >
          {#if item.id === 'general'}
            <h3>{t('settings.general.title')}</h3>
            <p class="section-description">{t('settings.general.description')}</p>

            <fieldset class="field">
              <legend>{t('settings.general.palette')}</legend>
              <p class="field-hint">{t('settings.general.paletteHint')}</p>
              <div class="palette-grid">
                {#each palettes as palette (palette.id)}
                  <label class="palette-card" class:active={palette.id === selectedPaletteId}>
                    <input
                      class="visually-hidden"
                      type="radio"
                      name="settings-palette"
                      value={palette.id}
                      checked={palette.id === selectedPaletteId}
                      onchange={() => onChangePalette(palette.id)}
                    />
                    <span
                      class="palette-preview"
                      style:background={palette.colors.bg}
                      aria-hidden="true"
                    >
                      <span class="palette-surface" style:background={palette.colors.surf}></span>
                      <span class="palette-accent" style:background={palette.colors.acc}></span>
                    </span>
                    <span class="palette-label">{palette.label}</span>
                  </label>
                {/each}
              </div>
            </fieldset>

            <div class="row">
              <div class="row-copy">
                <label class="row-title" for="settings-language">
                  {t('settings.general.language')}
                </label>
                <p class="row-hint" id="settings-language-hint">
                  {t('settings.general.languageHint')}
                </p>
              </div>
              <select
                id="settings-language"
                class="select"
                value={locale}
                aria-describedby="settings-language-hint"
                onchange={(event) =>
                  onChangeLocale((event.currentTarget as HTMLSelectElement).value as Locale)}
              >
                <option value="en">{t('language.en')}</option>
                <option value="es">{t('language.es')}</option>
              </select>
            </div>

            <div class="row">
              <div class="row-copy">
                <label class="row-title" for="settings-motion">
                  {t('settings.general.motion')}
                </label>
                <p class="row-hint" id="settings-motion-hint">{t('settings.general.motionHint')}</p>
              </div>
              <select
                id="settings-motion"
                class="select"
                value={motion}
                aria-describedby="settings-motion-hint"
                onchange={(event) => {
                  const value = (event.currentTarget as HTMLSelectElement).value;
                  onChangeMotion(value === 'reduce' ? 'reduce' : 'system');
                }}
              >
                <option value="system">{t('settings.general.motionSystem')}</option>
                <option value="reduce">{t('settings.general.motionReduce')}</option>
              </select>
            </div>

            <fieldset class="field">
              <legend>{t('settings.general.sendKey')}</legend>
              <label class="radio-option">
                <input
                  type="radio"
                  name="settings-send-key"
                  checked={!invertSendKey}
                  onchange={() => onChangeInvertSendKey(false)}
                />
                <span>{t('settings.general.enterSends')}</span>
              </label>
              <label class="radio-option">
                <input
                  type="radio"
                  name="settings-send-key"
                  checked={invertSendKey}
                  onchange={() => onChangeInvertSendKey(true)}
                />
                <span>{t('settings.general.shiftEnterSends')}</span>
              </label>
            </fieldset>
          {:else if item.id === 'assistant'}
            <h3>{t('settings.assistant.title')}</h3>
            <p class="section-description">{t('settings.assistant.description')}</p>

            <fieldset class="field">
              <legend>{t('settings.assistant.defaultMode')}</legend>
              <p class="field-hint">{t('settings.assistant.defaultModeHint')}</p>
              <div class="choice-grid">
                {#each modes as mode (mode.id)}
                  <label class="choice" class:active={defaultMode === mode.id}>
                    <input
                      type="radio"
                      name="settings-default-mode"
                      value={mode.id}
                      checked={defaultMode === mode.id}
                      onchange={() => onChangeDefaultMode(mode.id)}
                    />
                    <span>{t(mode.label)}</span>
                  </label>
                {/each}
              </div>
            </fieldset>

            <div class="row">
              <div class="row-copy">
                <label class="row-title" for="settings-model">
                  {t('settings.assistant.model')}
                </label>
                <p class="row-hint" id="settings-model-hint">
                  {t('settings.assistant.modelHint')}
                </p>
              </div>
              {#if modelOptions.length > 0}
                <select
                  id="settings-model"
                  class="select"
                  value={selectedModelId ?? ''}
                  aria-describedby="settings-model-hint"
                  onchange={(event) =>
                    onChangeModel((event.currentTarget as HTMLSelectElement).value)}
                >
                  {#each modelOptions as model (model.id)}
                    <option value={model.id}>{model.label}</option>
                  {/each}
                </select>
              {:else}
                <p class="row-value muted">{t('settings.assistant.noModels')}</p>
              {/if}
            </div>

            <div class="note">
              <p class="note-title">{t('settings.assistant.managedTitle')}</p>
              <p class="note-text">{t('settings.assistant.managedDescription')}</p>
            </div>
          {:else if item.id === 'chats'}
            <h3>{t('settings.chats.title')}</h3>
            <p class="section-description">{t('settings.chats.description')}</p>

            <p class="group-label">{t('settings.chats.displayTitle')}</p>
            {@render toggleRow(
              'settings-sources',
              t('settings.chats.showSources'),
              t('settings.chats.showSourcesHint'),
              showSources,
              onChangeShowSources,
            )}
            {@render toggleRow(
              'settings-directions',
              t('settings.chats.showDirections'),
              t('settings.chats.showDirectionsHint'),
              showDirections,
              onChangeShowDirections,
            )}
            {@render toggleRow(
              'settings-quiz',
              t('settings.chats.showQuiz'),
              t('settings.chats.showQuizHint'),
              showQuiz,
              onChangeShowQuiz,
            )}

            <div class="row">
              <div class="row-copy">
                <p class="row-title">{t('settings.chats.exportTitle')}</p>
                <p class="row-hint">{t('settings.chats.exportDescription')}</p>
              </div>
              <button
                type="button"
                class="btn"
                disabled={!hasConversations}
                onclick={onExportConversations}
              >
                {t('settings.chats.exportAction')}
              </button>
            </div>
            {#if !hasConversations}
              <p class="inline-hint">{t('settings.chats.exportEmpty')}</p>
            {/if}

            <div class="note">
              <p class="note-title">{t('settings.chats.storedTitle')}</p>
              <p class="note-text">{t('settings.chats.storedDescription')}</p>
            </div>
          {:else if item.id === 'notifications'}
            <h3>{t('settings.notifications.title')}</h3>
            <p class="section-description">{t('settings.notifications.description')}</p>

            {@render toggleRow(
              'settings-notify',
              t('settings.notifications.completeTitle'),
              t('settings.notifications.completeDescription'),
              notifyOnComplete,
              onChangeNotifyOnComplete,
              notificationPermission === 'unsupported' ||
                (notificationPermission === 'denied' && !notifyOnComplete),
            )}

            <div class="row">
              <div class="row-copy">
                <p class="row-title">{t('settings.notifications.permission')}</p>
                <p class="row-hint">{t('settings.notifications.permissionHint')}</p>
              </div>
              <div class="row-control">
                <span
                  class="status-pill"
                  class:allowed={notificationPermission === 'granted'}
                  class:blocked={notificationPermission === 'denied'}
                >
                  {permissionLabel()}
                </span>
                {#if notificationPermission === 'default'}
                  <button type="button" class="btn" onclick={onRequestNotificationPermission}>
                    {t('settings.notifications.requestPermission')}
                  </button>
                {/if}
              </div>
            </div>
          {:else if item.id === 'shortcuts'}
            <h3>{t('settings.shortcuts.title')}</h3>
            <p class="section-description">{t('settings.shortcuts.description')}</p>
            <dl class="shortcut-list">
              {#each shortcuts as row, index (index)}
                <div class="shortcut-row">
                  <dt><kbd>{row.keys}</kbd></dt>
                  <dd>{row.description}</dd>
                </div>
              {/each}
            </dl>
          {:else if item.id === 'account'}
            <h3>{t('settings.account.title')}</h3>
            <p class="section-description">{t('settings.account.description')}</p>

            {#if user}
              <div class="identity">
                <span class="avatar" aria-hidden="true">{initials}</span>
                <div class="identity-copy">
                  <p class="identity-name">{user.displayName}</p>
                  <p class="identity-email">{user.email}</p>
                </div>
              </div>

              <div class="row">
                <p class="row-title">{t('settings.account.role')}</p>
                <p class="row-value">
                  {user.role === 'admin'
                    ? t('settings.account.roleAdmin')
                    : t('settings.account.roleRegular')}
                </p>
              </div>

              {#if user.role === 'admin'}
                <div class="row">
                  <div class="row-copy">
                    <p class="row-title">{t('settings.account.admin')}</p>
                    <p class="row-hint">{t('settings.account.adminHint')}</p>
                  </div>
                  <a class="btn" href="/admin/">{t('settings.account.admin')}</a>
                </div>
              {/if}

              <div class="actions">
                <button type="button" class="btn" onclick={onLogout}>
                  {t('settings.account.signOut')}
                </button>
              </div>
              <p class="inline-hint">{t('settings.account.managedHint')}</p>
            {/if}
          {:else if item.id === 'about'}
            <h3>{t('settings.about.title')}</h3>
            <p class="about-blurb">{t('settings.about.description')}</p>

            <div class="row">
              <p class="row-title">{t('settings.about.version')}</p>
              <p class="row-value">{version}</p>
            </div>

            <div class="row">
              <div class="row-copy">
                <p class="row-title">{t('settings.about.source')}</p>
                <p class="row-hint">{t('settings.about.sourceHint')}</p>
              </div>
              <a class="btn" href={sourceUrl} target="_blank" rel="noreferrer">
                {t('settings.about.source')}
              </a>
            </div>

            <div class="row">
              <div class="row-copy">
                <p class="row-title">{t('settings.about.reset')}</p>
                <p class="row-hint">{t('settings.about.resetHint')}</p>
              </div>
              <button type="button" class="btn" onclick={handleReset}>
                {t('settings.about.resetAction')}
              </button>
            </div>
            {#if resetDone}
              <p class="inline-hint success" role="status">{t('settings.about.resetDone')}</p>
            {/if}
          {/if}
        </div>
      {/each}
    </div>
  </div>
</Dialog>

<style>
  .settings-body {
    display: flex;
    flex: 1;
    min-height: 0;
  }

  .settings-nav {
    flex: 0 0 220px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-3);
    border-right: 1px solid var(--p-line);
    background: color-mix(in oklab, var(--p-surf) 92%, var(--p-bg));
    overflow-y: auto;
  }

  .nav-item {
    appearance: none;
    display: flex;
    align-items: center;
    width: 100%;
    min-height: var(--target-min);
    padding: 0 var(--space-3);
    border: 1px solid transparent;
    border-radius: var(--radius-icon-btn);
    background: transparent;
    color: var(--p-mut);
    font: inherit;
    font-size: 14px;
    text-align: left;
    cursor: pointer;
    position: relative;
  }

  .nav-item:hover {
    color: var(--p-ink);
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
  }

  .nav-item.active {
    color: var(--p-ink);
    background: color-mix(in oklab, var(--p-acc) 14%, transparent);
  }

  .nav-item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 10px;
    bottom: 10px;
    width: 2px;
    border-radius: var(--radius-capsule);
    background: var(--p-acc);
  }

  .nav-item:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: -2px;
  }

  .settings-content {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    padding: var(--space-5) var(--space-6);
  }

  .settings-panel {
    max-width: 660px;
  }

  .settings-panel:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 4px;
    border-radius: var(--radius-swatch);
  }

  h3 {
    margin: 0 0 var(--space-2);
    color: var(--p-ink);
    font-family: var(--p-display);
    font-size: 20px;
    font-weight: 600;
  }

  .section-description,
  .about-blurb {
    margin: 0 0 var(--space-5);
    color: var(--p-mut);
    font-size: 14px;
    line-height: 1.55;
    max-width: 60ch;
  }

  .about-blurb {
    margin-bottom: var(--space-4);
  }

  .field {
    min-width: 0;
    margin: 0;
    padding: var(--space-4) 0;
    border: none;
    border-top: 1px solid var(--p-line);
  }

  legend {
    padding: 0 0 var(--space-2);
    color: var(--p-ink);
    font-size: 14px;
    font-weight: 600;
  }

  .field-hint {
    margin: 0 0 var(--space-3);
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.5;
    max-width: 52ch;
  }

  .row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--space-5);
    padding: var(--space-4) 0;
    border-top: 1px solid var(--p-line);
  }

  .row-copy {
    min-width: 0;
  }

  .row-title {
    margin: 0;
    color: var(--p-ink);
    font-size: 14px;
    font-weight: 600;
  }

  .row-hint {
    margin: var(--space-1) 0 0;
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.5;
    max-width: 52ch;
  }

  .row-value {
    margin: 0;
    color: var(--p-ink);
    font-size: 14px;
    white-space: nowrap;
  }

  .row-value.muted {
    color: var(--p-mut);
    font-size: 13px;
    white-space: normal;
    text-align: right;
  }

  .row-control {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: var(--space-2);
  }

  .group-label {
    margin: var(--space-4) 0 0;
    color: var(--p-mut);
    font-size: 12px;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }

  .palette-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .palette-card {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-menu);
    cursor: pointer;
  }

  .palette-card:hover {
    border-color: var(--p-line-2);
  }

  .palette-card.active {
    border-color: var(--p-acc);
    box-shadow: 0 0 0 1px var(--p-acc);
  }

  .palette-preview {
    display: block;
    position: relative;
    height: 42px;
    border: 1px solid var(--p-line);
    border-radius: var(--radius-swatch);
    overflow: hidden;
  }

  .palette-surface {
    position: absolute;
    inset: 8px;
    border-radius: var(--radius-swatch);
  }

  .palette-accent {
    position: absolute;
    right: 10px;
    bottom: 10px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }

  .palette-label {
    padding-inline: var(--space-1);
    color: var(--p-ink);
    font-size: 13px;
  }

  .visually-hidden {
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

  .visually-hidden:focus-visible + .palette-preview {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .select {
    min-width: 180px;
    max-width: 280px;
    min-height: var(--target-min);
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-icon-btn);
    background: var(--p-surf);
    color: var(--p-ink);
    font: inherit;
    font-size: 14px;
  }

  .select:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .radio-option {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--target-min);
    color: var(--p-ink);
    font-size: 14px;
  }

  .radio-option input,
  .choice input {
    width: 16px;
    height: 16px;
    accent-color: var(--p-acc);
  }

  .choice-grid {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .choice {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--target-min);
    padding: 0 var(--space-3);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-icon-btn);
    color: var(--p-ink);
    font-size: 14px;
    cursor: pointer;
  }

  .choice:hover {
    border-color: var(--p-line-2);
  }

  .choice.active {
    border-color: var(--p-acc);
    background: color-mix(in oklab, var(--p-acc) 10%, transparent);
  }

  .switch {
    appearance: none;
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    flex: none;
    min-width: var(--target-min);
    min-height: var(--target-min);
    padding: 0;
    border: none;
    background: transparent;
    cursor: pointer;
  }

  .switch-track {
    display: inline-flex;
    align-items: center;
    position: relative;
    width: 40px;
    height: 22px;
    border: 1px solid var(--p-line);
    border-radius: var(--radius-capsule);
    background: color-mix(in oklab, var(--p-ink) 18%, transparent);
    transition: background-color var(--motion-fast) ease-out, border-color var(--motion-fast) ease-out;
  }

  .switch.on .switch-track {
    border-color: var(--p-acc);
    background: var(--p-acc);
  }

  .switch-thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--p-bg);
    transition: transform var(--motion-fast) ease-out;
  }

  .switch.on .switch-thumb {
    transform: translateX(18px);
  }

  .switch:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: var(--radius-capsule);
  }

  .switch:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .btn {
    appearance: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: none;
    min-height: var(--target-min);
    padding: 0 var(--space-4);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-icon-btn);
    background: transparent;
    color: var(--p-ink);
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
    cursor: pointer;
  }

  .btn:hover {
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
  }

  .btn:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .note {
    margin: var(--space-4) 0 0;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--p-line);
    border-left: 3px solid var(--p-acc);
    border-radius: var(--radius-menu);
    background: color-mix(in oklab, var(--p-acc) 6%, transparent);
  }

  .note-title {
    margin: 0 0 var(--space-1);
    color: var(--p-ink);
    font-size: 13px;
    font-weight: 600;
  }

  .note-text {
    margin: 0;
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.5;
  }

  .inline-hint {
    margin: var(--space-2) 0 0;
    color: var(--p-mut);
    font-size: 12px;
    line-height: 1.5;
  }

  .inline-hint.success {
    color: var(--sem-success);
  }

  .status-pill {
    padding: 3px var(--space-2);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-capsule);
    color: var(--p-mut);
    font-size: 11px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .status-pill.allowed {
    border-color: color-mix(in oklab, var(--sem-success) 45%, transparent);
    color: var(--sem-success);
  }

  .status-pill.blocked {
    border-color: color-mix(in oklab, var(--sem-critical) 45%, transparent);
    color: var(--sem-critical);
  }

  .shortcut-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
  }

  .shortcut-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--p-line);
  }

  .shortcut-row:last-child {
    border-bottom: none;
  }

  .shortcut-row dt {
    flex-shrink: 0;
  }

  .shortcut-row dd {
    margin: 0;
    color: var(--p-ink);
    font-size: 14px;
    text-align: right;
  }

  kbd {
    padding: 3px var(--space-2);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-swatch);
    background: var(--p-surf-2);
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 12px;
    white-space: nowrap;
  }

  .identity {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4) 0;
    border-top: 1px solid var(--p-line);
  }

  .avatar {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: none;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: color-mix(in oklab, var(--p-acc) 20%, transparent);
    color: var(--p-ink);
    font-family: var(--p-display);
    font-size: 18px;
    text-transform: uppercase;
  }

  .identity-name {
    margin: 0;
    color: var(--p-ink);
    font-size: 16px;
    font-weight: 600;
  }

  .identity-email {
    margin: var(--space-1) 0 0;
    color: var(--p-mut);
    font-size: 13px;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    padding-top: var(--space-4);
  }

  @media (max-width: 760px) {
    .settings-body {
      flex-direction: column;
    }

    .settings-nav {
      flex: 0 0 auto;
      flex-direction: row;
      gap: var(--space-1);
      padding: var(--space-2);
      border-right: none;
      border-bottom: 1px solid var(--p-line);
      overflow-x: auto;
      overflow-y: hidden;
    }

    .nav-item {
      width: auto;
      flex: none;
      white-space: nowrap;
      padding: 0 var(--space-3);
    }

    .nav-item.active::before {
      display: none;
    }

    .settings-content {
      padding: var(--space-4);
    }

    .palette-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .row {
      flex-direction: column;
      gap: var(--space-2);
    }

    .row-value,
    .row-value.muted {
      text-align: left;
    }

    .row-control {
      align-items: flex-start;
    }

    .select {
      width: 100%;
      max-width: none;
    }

    .shortcut-row {
      align-items: flex-start;
      flex-direction: column;
      gap: var(--space-1);
    }

    .shortcut-row dd {
      text-align: left;
    }
  }
</style>
