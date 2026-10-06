<!--
  design-system.md §5 — the Orbit capsule. ux-foundations.md §5 — its behaviour. This is the one
  composer variant (see ux-foundations.md §1: Orbit was chosen because the context cluster now owns
  attachments/tools/MCP, so Console's icon row would duplicate them) — no attach/tools/MCP
  buttons live here, on purpose.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import type { ComposerMode } from '@sofee/core';
  import { IconAttachments, IconChevronDown, IconMic, IconSend, IconStop } from '@sofee/icons';

  interface Props {
    value: string;
    mode: ComposerMode;
    isStreaming: boolean;
    isTemporary: boolean;
    hasAttachment?: boolean;
    invertSendKey?: boolean;
    pinnedSourceCount?: number;
    webAccessOn?: boolean;
    t: Translate;
    onSend: () => void;
    onStop: () => void;
    onModeChange: (mode: ComposerMode) => void;
    onAttach?: () => void;
    onToggleWebAccess?: () => void;
    onLongPaste?: (text: string) => void;
  }

  let {
    value = $bindable(''),
    mode,
    isStreaming,
    isTemporary,
    hasAttachment = false,
    invertSendKey = false,
    pinnedSourceCount = 0,
    webAccessOn = false,
    t,
    onSend,
    onStop,
    onModeChange,
    onAttach,
    onToggleWebAccess,
    onLongPaste,
  }: Props = $props();

  const MODE_ORDER: ComposerMode[] = ['learn', 'research', 'explore'];
  const LONG_PASTE_THRESHOLD = 2000;

  let textareaEl: HTMLTextAreaElement | null = $state(null);
  let canSend = $derived(value.trim().length > 0 || hasAttachment);
  let modeLabel = $derived(t(`composer.mode.${mode}`));

  function cycleMode(): void {
    const next = MODE_ORDER[(MODE_ORDER.indexOf(mode) + 1) % MODE_ORDER.length];
    if (next) onModeChange(next);
  }

  // Takes `_currentValue` only so the caller has an actual dependency to read — a draft
  // restored from outside the textarea (switching threads) needs to trigger a re-measure too;
  // the measurement itself reads the DOM, not this parameter.
  function autoGrow(_currentValue: string): void {
    if (!textareaEl) return;
    textareaEl.style.height = 'auto';
    textareaEl.style.height = `${textareaEl.scrollHeight}px`;
  }

  $effect(() => {
    autoGrow(value);
  });

  function trySend(): void {
    if (!canSend || isStreaming) return;
    onSend();
    queueMicrotask(() => textareaEl?.focus());
  }

  /** ux-foundations.md §5: "The composer holds focus on load and after every send" — plus
   * whenever the app itself needs to return focus here (a starter move, an edit, Esc). */
  export function focus(): void {
    textareaEl?.focus();
  }

  function onKeydown(event: KeyboardEvent): void {
    // ux-foundations.md §5: never send while an IME composition is in progress — Japanese,
    // Chinese and Korean input all use Enter to commit a candidate.
    if (event.isComposing) return;
    const sendKey = invertSendKey
      ? event.shiftKey && event.key === 'Enter'
      : event.key === 'Enter' && !event.shiftKey;
    if (sendKey) {
      event.preventDefault();
      trySend();
    }
  }

  function onPaste(event: ClipboardEvent): void {
    const text = event.clipboardData?.getData('text/plain') ?? '';
    if (text.length > LONG_PASTE_THRESHOLD && onLongPaste) {
      event.preventDefault();
      onLongPaste(text);
    }
  }
</script>

<div class="composer">
  {#if pinnedSourceCount > 0 || onToggleWebAccess}
    <div class="satellites">
      <span class="chip" title={t('satellite.depth.label')}>
        <span class="chip-dot" aria-hidden="true"></span>
        {modeLabel}
      </span>
      {#if pinnedSourceCount > 0}
        <span class="chip">{t('satellite.sources.count', { count: pinnedSourceCount })}</span>
      {/if}
      {#if onToggleWebAccess}
        <button
          type="button"
          class="chip chip-toggle"
          class:on={webAccessOn}
          onclick={onToggleWebAccess}
        >
          {webAccessOn ? t('satellite.web.on') : t('satellite.web.off')}
        </button>
      {/if}
    </div>
  {/if}

  <div class="capsule-shell" class:temporary={isTemporary}>
    <div class="outer-ring"></div>
    <div class="capsule">
      <button
        type="button"
        class="mode-orb"
        aria-label={t('composer.mode.current', { mode: modeLabel })}
        title={t('composer.mode.cycle')}
        onclick={cycleMode}
      >
        <span class="orb-visual" aria-hidden="true"></span>
      </button>

      <textarea
        bind:this={textareaEl}
        bind:value
        rows="1"
        class="composer-input"
        placeholder={t('composer.placeholder')}
        aria-label={t('composer.placeholder')}
        onkeydown={onKeydown}
        onpaste={onPaste}></textarea>

      <div class="trailing-cluster">
        {#if onAttach}
          <button
            type="button"
            class="round-btn"
            aria-label={t('composer.attach')}
            title={t('composer.attach')}
            onclick={onAttach}
          >
            <IconAttachments size={18} />
          </button>
        {/if}
        <button
          type="button"
          class="round-btn mic-btn"
          aria-label={t('composer.dictate')}
          title={t('composer.dictate')}
        >
          <IconMic size={18} />
        </button>
      </div>

      <div class="send-split">
        <button
          type="button"
          class="send-btn"
          disabled={!isStreaming && !canSend}
          aria-label={isStreaming ? t('composer.stop') : t('composer.send')}
          title={isStreaming
            ? t('composer.stop')
            : canSend
              ? t('composer.send')
              : t('composer.empty')}
          onclick={isStreaming ? onStop : trySend}
        >
          {#if isStreaming}
            <IconStop size={18} />
          {:else}
            <IconSend size={18} />
          {/if}
        </button>
        <button
          type="button"
          class="chevron-btn"
          aria-label={t('composer.moreSendOptions')}
          aria-haspopup="menu"
        >
          <IconChevronDown size={14} />
        </button>
      </div>
    </div>
  </div>
</div>

<style>
  .composer {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    width: min(100%, var(--canvas-max-width));
    margin-inline: auto;
  }

  .satellites {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    padding-inline: var(--space-3);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    padding: 4px var(--space-3);
    border-radius: var(--radius-capsule);
    background: color-mix(in oklab, var(--p-surf) 72%, transparent);
    backdrop-filter: blur(8px);
    border: 1px solid var(--p-line);
    color: var(--p-mut);
    font-size: 12px;
    white-space: nowrap;
  }

  .chip-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, var(--p-acc2), var(--p-acc));
  }

  .chip-toggle {
    cursor: pointer;
  }

  .chip-toggle.on {
    color: var(--p-ink);
    border-color: color-mix(in oklab, var(--p-acc) 45%, transparent);
  }

  .capsule-shell {
    position: relative;
    width: 100%;
  }

  .outer-ring {
    position: absolute;
    inset: -8px;
    border-radius: var(--radius-capsule);
    border: 1px dashed var(--p-line-2);
    opacity: 0.55;
    pointer-events: none;
    transition:
      inset var(--motion-focus-duration) var(--motion-focus-easing),
      opacity var(--motion-focus-duration) var(--motion-focus-easing),
      border-color var(--motion-focus-duration) var(--motion-focus-easing);
  }

  .capsule-shell:focus-within .outer-ring {
    inset: -3px;
    border-style: solid;
    border-color: var(--p-acc);
    opacity: 1;
  }

  /* ux-foundations.md §2.3: a temporary chat's composer ring stays dashed even on focus — a
     deliberate, persistent visual reminder that this thread is never saved. */
  .capsule-shell.temporary .outer-ring {
    border-style: dashed !important;
  }

  .capsule {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--composer-height);
    padding: 5px 6px;
    border-radius: var(--radius-capsule);
    background: color-mix(in oklab, var(--p-surf) 84%, transparent);
    backdrop-filter: blur(14px);
    box-shadow:
      inset 0 0 0 1px var(--p-line),
      inset 0 1px 0 var(--p-hi),
      /* The capsule floats over the canvas; without a cast shadow it reads as painted on. */ 0 18px
        40px -24px rgba(0, 0, 0, 0.7);
  }

  .mode-orb {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--target-min);
    height: var(--target-min);
    flex-shrink: 0;
    border: none;
    border-radius: 50%;
    background: transparent;
    cursor: pointer;
  }

  .mode-orb:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .orb-visual {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    /* Off-centre highlight plus a bloom: the orb is the one lit object in the composer. */
    background: radial-gradient(
      70% 70% at 32% 26%,
      color-mix(in oklab, var(--p-acc2) 70%, white 10%),
      var(--p-acc) 72%
    );
    box-shadow:
      0 0 20px -6px var(--p-acc),
      inset 0 1px 0 rgb(255 255 255 / 0.35);
    transition: transform var(--motion-fast, 180ms) ease-out;
  }

  .mode-orb:hover .orb-visual {
    transform: scale(1.06);
  }

  @media (prefers-reduced-motion: reduce) {
    .orb-visual {
      transition: none;
    }
    .mode-orb:hover .orb-visual {
      transform: none;
    }
  }

  .composer-input {
    flex: 1;
    /* A floor, not a fixed width — ux-foundations.md §7.2: "no fixed-width buttons or labels."
       Without it, the row's other controls (all fixed-size, per design-system.md §5/§6) would
       flex-shrink this to near zero on a narrow phone before they gave up any of their own
       space, especially with the longer Spanish placeholder text. */
    min-width: 64px;
    resize: none;
    border: none;
    background: transparent;
    color: var(--p-ink);
    font: inherit;
    font-size: 15px;
    line-height: 1.5;
    padding: var(--space-2) 2px;
    max-height: 40vh;
    overflow-y: auto;
  }

  .composer-input::placeholder {
    color: var(--p-mut);
  }

  .composer-input:focus {
    outline: none;
  }

  .trailing-cluster {
    display: flex;
    align-items: center;
    gap: 2px;
    flex-shrink: 0;
  }

  .round-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--target-min);
    height: var(--target-min);
    flex-shrink: 0;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: var(--p-mut);
    cursor: pointer;
  }

  .round-btn:hover {
    color: var(--p-ink);
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
  }

  .round-btn:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  /* Rails hold their 56px width regardless of viewport (design-system.md §8), which leaves very
     little room either side of a narrow phone's canvas. Dictate is the one composer control
     that is not needed to type or send, so it gives way first, before the text input itself
     gets crushed. */
  @media (max-width: 480px) {
    .mic-btn {
      display: none;
    }
  }

  .send-split {
    display: flex;
    align-items: stretch;
    flex-shrink: 0;
    height: var(--target-min);
    border-radius: var(--radius-capsule);
    overflow: hidden;
    background: linear-gradient(
      150deg,
      var(--p-acc),
      color-mix(in oklab, var(--p-acc2) 62%, var(--p-acc))
    );
    box-shadow:
      0 6px 18px -8px var(--p-acc),
      inset 0 1px 0 rgb(255 255 255 / 0.28);
    transition:
      transform var(--motion-fast, 180ms) ease-out,
      filter var(--motion-fast, 180ms) ease-out;
  }

  .send-split:hover:not(:has(.send-btn:disabled)) {
    transform: translateY(-1px);
    filter: brightness(1.08);
  }

  @media (prefers-reduced-motion: reduce) {
    .send-split {
      transition: none;
    }
    .send-split:hover:not(:has(.send-btn:disabled)) {
      transform: none;
    }
  }

  .send-btn,
  .chevron-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: transparent;
    color: var(--p-send-ink);
    cursor: pointer;
  }

  .send-btn {
    width: var(--target-min);
  }

  .chevron-btn {
    width: 26px;
    background: color-mix(in oklab, var(--p-acc2) 62%, var(--p-acc));
    border-left: 1px solid rgb(0 0 0 / 0.18);
    box-shadow: inset 0 1px 0 rgb(255 255 255 / 0.22);
  }

  .send-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .send-btn:focus-visible,
  .chevron-btn:focus-visible {
    outline: 2px solid var(--p-ink);
    outline-offset: -2px;
  }
</style>
