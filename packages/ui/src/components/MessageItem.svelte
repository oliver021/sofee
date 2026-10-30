<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { Citation, MessageRole, MessageStatus, RunErrorCode, Translate } from '@sofee/core';
  import { IconCopy, IconEdit, IconRefresh, IconThumbsDown, IconThumbsUp } from '@sofee/icons';
  import Markdown from './Markdown.svelte';
  import RunErrorBox from './RunErrorBox.svelte';
  import ThinkingIndicator from './ThinkingIndicator.svelte';

  interface Props {
    id: string;
    role: MessageRole;
    status: MessageStatus;
    text: string;
    citations?: readonly Citation[];
    /** Set in the error state: picks the inline copy and actions (roadmap U6). */
    errorCode?: RunErrorCode;
    /** Pre-formatted local time a quota-exceeded send can be retried. */
    errorResetLabel?: string;
    /** The run's latest status text, shown while the reply has not started (roadmap U3). */
    statusText?: string;
    /** Good or bad, when the reader has rated this reply (roadmap U15-lite). */
    feedback?: 'good' | 'bad';
    copied?: boolean;
    t: Translate;
    /** The agent's plan, sub-agents and plan review: shown above the reply text. */
    activity?: Snippet;
    /** The reply's sources, quiz and directions: shown under the reply text. */
    footer?: Snippet;
    onCopy: () => void;
    onEdit?: () => void;
    onRegenerate?: () => void;
    onGoodResponse?: () => void;
    onBadResponse?: () => void;
    onRetry?: () => void;
    onContinue?: () => void;
    onChangeModel?: () => void;
    /** Opens a team document or attachment cited in the reply (roadmap U4). */
    onOpenSource?: (citation: Citation, trigger: HTMLElement) => void;
  }

  let {
    id,
    role,
    status,
    text,
    citations = [],
    errorCode,
    errorResetLabel,
    statusText = '',
    feedback,
    copied = false,
    t,
    activity,
    footer,
    onCopy,
    onEdit,
    onRegenerate,
    onGoodResponse,
    onBadResponse,
    onRetry,
    onContinue,
    onChangeModel,
    onOpenSource,
  }: Props = $props();

  let speakerLabel = $derived(role === 'user' ? t('message.you') : t('message.assistant'));
  // The reply has not started: the indicator holds its height until the first text arrives.
  let waiting = $derived(role === 'assistant' && text.length === 0 && status === 'pending');
</script>

<!-- <article> already carries an implicit role of "article" (HTML-AAM) — ux-foundations.md
     §8's "role=article" requirement is met natively, an explicit role attribute would be
     redundant. -->
<article
  class="message"
  class:user={role === 'user'}
  class:assistant={role === 'assistant'}
  aria-label={speakerLabel}
  data-message-id={id}
  tabindex="-1"
>
  <div class="body">
    {#if activity && role === 'assistant'}
      <div class="message-activity">{@render activity()}</div>
    {/if}

    {#if role === 'user'}
      <p class="user-text">{text}</p>
    {:else if text.length > 0}
      <Markdown {text} {citations} {t} {onOpenSource} />
    {:else if waiting || status === 'streaming'}
      <ThinkingIndicator {t} {statusText} />
    {/if}

    {#if footer && role === 'assistant'}
      <div class="message-footer">{@render footer()}</div>
    {/if}

    {#if status === 'stopped'}
      <p class="inline-status">
        <span class="incomplete-badge">{t('message.incomplete')}</span>
        {t('thread.stoppedByUser')}
        {#if onContinue}
          <button type="button" class="text-action" onclick={onContinue}
            >{t('thread.continue')}</button
          >
        {/if}
      </p>
    {/if}

    {#if status === 'error'}
      <RunErrorBox code={errorCode} resetLabel={errorResetLabel} {t} {onRetry} {onChangeModel} />
    {/if}
  </div>

  <div class="actions">
    <button
      type="button"
      class="action-btn"
      aria-label={t('message.copy')}
      title={copied ? t('message.copied') : t('message.copy')}
      onclick={onCopy}
    >
      <IconCopy size={16} />
    </button>
    {#if role === 'user' && onEdit}
      <button
        type="button"
        class="action-btn"
        aria-label={t('message.edit')}
        title={t('message.edit')}
        onclick={onEdit}
      >
        <IconEdit size={16} />
      </button>
    {/if}
    {#if role === 'assistant' && onRegenerate}
      <button
        type="button"
        class="action-btn"
        aria-label={t('message.regenerate')}
        title={t('message.regenerate')}
        onclick={onRegenerate}
      >
        <IconRefresh size={16} />
      </button>
    {/if}
    {#if role === 'assistant' && onGoodResponse}
      <button
        type="button"
        class="action-btn"
        class:pressed={feedback === 'good'}
        aria-label={t('message.goodResponse')}
        aria-pressed={feedback === 'good'}
        title={t('message.goodResponse')}
        onclick={onGoodResponse}
      >
        <IconThumbsUp size={16} />
      </button>
    {/if}
    {#if role === 'assistant' && onBadResponse}
      <button
        type="button"
        class="action-btn"
        class:pressed={feedback === 'bad'}
        aria-label={t('message.badResponse')}
        aria-pressed={feedback === 'bad'}
        title={t('message.badResponse')}
        onclick={onBadResponse}
      >
        <IconThumbsDown size={16} />
      </button>
    {/if}
  </div>
</article>

<style>
  .message {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-2) 0;
  }

  .message.user .body {
    align-self: flex-end;
    max-width: 85%;
    background: var(--p-surf);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-panel);
    padding: var(--space-3) var(--space-4);
  }

  .message.assistant .body {
    max-width: 100%;
  }

  /* What the user typed is shown as typed: no markdown, but their line breaks are kept. */
  .user-text {
    margin: 0;
    white-space: pre-wrap;
  }

  .body {
    /* min-width stops a wide table or code block from stretching the flex column past the
       viewport. */
    min-width: 0;
    line-height: 1.6;
    font-size: 15px;
    color: var(--p-ink);
  }

  .message-activity,
  .message-footer {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  /* The wrappers always render for a reply, so the spacing only applies once they hold something:
     an empty wrapper must not push the text down. The children come from the parent's snippets,
     which this stylesheet cannot see, hence the :global(). */
  :global(.message-activity:has(> *)) {
    margin-bottom: var(--space-3);
  }

  :global(.message-footer:has(> *)) {
    margin-top: var(--space-4);
  }

  /* ux-foundations.md §6: "Alt + [Up/Down] — Move between messages" moves focus here
     programmatically; this is the only way the article itself is ever focused. */
  .message:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 4px;
    border-radius: var(--radius-swatch);
  }

  .inline-status {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--p-mut);
    font-size: 13px;
  }

  .incomplete-badge {
    padding: 2px var(--space-2);
    border-radius: var(--radius-swatch);
    background: color-mix(in oklab, var(--sem-warning) 20%, transparent);
    color: var(--sem-warning);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .text-action {
    min-height: var(--target-min);
    border: none;
    background: none;
    color: var(--p-acc);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    padding: 0;
  }

  .text-action:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .actions {
    display: flex;
    gap: 2px;
    opacity: 0;
    transition: opacity var(--motion-menu-duration) var(--motion-menu-easing);
  }

  .message.user .actions {
    align-self: flex-end;
  }

  .message:hover .actions,
  .message:focus-within .actions {
    opacity: 1;
  }

  /* ux-foundations.md §8: 44 x 44 px targets for every control, the message actions included. */
  .action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--target-min);
    height: var(--target-min);
    border-radius: var(--radius-icon-btn);
    border: 1px solid transparent;
    background: transparent;
    color: var(--p-mut);
    cursor: pointer;
  }

  .action-btn:hover {
    color: var(--p-ink);
    background: color-mix(in oklab, var(--p-ink) 8%, transparent);
    border-color: var(--p-line);
  }

  .action-btn.pressed {
    color: var(--p-acc);
    border-color: var(--p-line-2);
  }

  .action-btn:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }
</style>
