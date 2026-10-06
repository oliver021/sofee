<!--
  ux-foundations.md §4.4 — message affordances. Controls appear on hover AND keyboard focus
  (never hover-only). §4.3 — error/stopped states render inline, in the thread, never as a
  toast. §8 — role="article" with an accessible name identifying the speaker.
-->
<script lang="ts">
  import type { Citation, MessageRole, MessageStatus, Translate } from '@sofee/core';
  import { IconCopy, IconEdit, IconRefresh, IconThumbsDown, IconThumbsUp } from '@sofee/icons';
  import CitationRef from './CitationRef.svelte';
  import { formatMessage } from '../format-message.js';

  interface Props {
    id: string;
    role: MessageRole;
    status: MessageStatus;
    text: string;
    citations?: Citation[];
    copied?: boolean;
    t: Translate;
    onCopy: () => void;
    onEdit?: () => void;
    onRegenerate?: () => void;
    onGoodResponse?: () => void;
    onBadResponse?: () => void;
    onRetry?: () => void;
    onContinue?: () => void;
  }

  let {
    id,
    role,
    status,
    text,
    citations = [],
    copied = false,
    t,
    onCopy,
    onEdit,
    onRegenerate,
    onGoodResponse,
    onBadResponse,
    onRetry,
    onContinue,
  }: Props = $props();

  let blocks = $derived(formatMessage(text));
  let speakerLabel = $derived(role === 'user' ? t('message.you') : t('message.assistant'));

  function citationFor(index: number): Citation | undefined {
    return citations.find((c) => c.index === index);
  }
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
    {#each blocks as block, blockIndex (blockIndex)}
      {#if block.type === 'heading'}
        <svelte:element this={block.level === 2 ? 'h3' : 'h4'} class="heading">
          {#each block.segments as segment, i (i)}
            {#if segment.type === 'bold'}<strong>{segment.value}</strong>
            {:else if segment.type === 'citation'}{@const c = citationFor(
                segment.index,
              )}{#if c}<CitationRef citation={c} {t} />{/if}
            {:else}{segment.value}{/if}
          {/each}
        </svelte:element>
      {:else if block.type === 'paragraph'}
        <p>
          {#each block.segments as segment, i (i)}
            {#if segment.type === 'bold'}<strong>{segment.value}</strong>
            {:else if segment.type === 'citation'}{@const c = citationFor(
                segment.index,
              )}{#if c}<CitationRef citation={c} {t} />{/if}
            {:else}{segment.value}{/if}
          {/each}
        </p>
      {:else if block.type === 'bullets'}
        <ul>
          {#each block.items as item, itemIndex (itemIndex)}
            <li>
              {#each item as segment, i (i)}
                {#if segment.type === 'bold'}<strong>{segment.value}</strong>
                {:else if segment.type === 'citation'}{@const c = citationFor(
                    segment.index,
                  )}{#if c}<CitationRef citation={c} {t} />{/if}
                {:else}{segment.value}{/if}
              {/each}
            </li>
          {/each}
        </ul>
      {/if}
    {/each}

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
      <div class="error-box">
        <p class="error-title">{t('thread.errorTitle')}</p>
        <p>{t('thread.errorBody')}</p>
        {#if onRetry}
          <button type="button" class="text-action" onclick={onRetry}>{t('thread.retry')}</button>
        {/if}
      </div>
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
        aria-label={t('message.goodResponse')}
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
        aria-label={t('message.badResponse')}
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

  .body {
    /* Kept in sync with ThinkingIndicator's min-height so the first streamed line does not
       shift layout when it replaces the indicator (§3.3). */
    line-height: 1.6;
    font-size: 15px;
    color: var(--p-ink);
  }

  .body :global(p) {
    margin: 0 0 var(--space-3);
  }
  .body :global(p:last-child) {
    margin-bottom: 0;
  }
  .body :global(.heading) {
    margin: var(--space-4) 0 var(--space-2);
    font-family: var(--p-display);
    color: var(--p-ink);
  }
  .body :global(h3.heading) {
    font-size: 17px;
  }
  .body :global(h4.heading) {
    font-size: 15px;
  }
  .body :global(ul) {
    margin: 0 0 var(--space-3);
    padding-left: 1.3em;
  }
  .body :global(li) {
    margin-bottom: var(--space-1);
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

  .error-box {
    border: 1px solid color-mix(in oklab, var(--sem-critical) 45%, transparent);
    background: color-mix(in oklab, var(--sem-critical) 10%, transparent);
    border-radius: var(--radius-panel);
    padding: var(--space-3) var(--space-4);
  }

  .error-title {
    font-weight: 600;
    color: var(--sem-critical);
  }

  .text-action {
    border: none;
    background: none;
    color: var(--p-acc);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    padding: 0;
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

  .action-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
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

  .action-btn:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }
</style>
