<!--
  ux-foundations.md §4.3 — "Error: Inline, in the thread, states what failed and what to do, with
  Retry." Each run error code gets its own sentence and its own action (roadmap U6): a model that
  is gone offers "Change model", a spent daily quota says when it resets, a provider hiccup offers
  Retry. Without a code (the mock assistant, or an older record) the generic copy applies.
-->
<script lang="ts">
  import type { RunErrorCode, Translate } from '@sofee/core';

  interface Props {
    code?: RunErrorCode;
    /** Pre-formatted local time a quota resets at, for `quota_exceeded`. */
    resetLabel?: string;
    t: Translate;
    onRetry?: () => void;
    onChangeModel?: () => void;
  }

  let { code, resetLabel = '', t, onRetry, onChangeModel }: Props = $props();

  let text = $derived.by(() => {
    switch (code) {
      case 'model_unavailable':
        return {
          title: t('thread.errors.modelUnavailable.title'),
          body: t('thread.errors.modelUnavailable.body'),
        };
      case 'provider_error':
        return {
          title: t('thread.errors.providerError.title'),
          body: t('thread.errors.providerError.body'),
        };
      case 'rate_limited':
        return {
          title: t('thread.errors.rateLimited.title'),
          body: t('thread.errors.rateLimited.body'),
        };
      case 'quota_exceeded':
        return {
          title: t('thread.errors.quotaExceeded.title'),
          body: t('thread.errors.quotaExceeded.body', { time: resetLabel }),
        };
      case 'agent_disabled':
        return {
          title: t('thread.errors.agentDisabled.title'),
          body: t('thread.errors.agentDisabled.body'),
        };
      case 'timeout':
        return { title: t('thread.errors.timeout.title'), body: t('thread.errors.timeout.body') };
      case 'internal':
        return { title: t('thread.errors.internal.title'), body: t('thread.errors.internal.body') };
      case 'network':
        return { title: t('thread.errors.network.title'), body: t('thread.errors.network.body') };
      case 'busy':
        return { title: t('thread.errors.busy.title'), body: t('thread.errors.busy.body') };
      case undefined:
        return { title: t('thread.errorTitle'), body: t('thread.errorBody') };
    }
  });

  // Quota and a disabled assistant clear themselves (or need an administrator), so they offer no
  // action; a missing model is fixed by picking another one, which Retry then sends with.
  let showRetry = $derived(
    onRetry !== undefined && code !== 'quota_exceeded' && code !== 'agent_disabled',
  );
  let showChangeModel = $derived(code === 'model_unavailable' && onChangeModel !== undefined);
</script>

<div class="error-box">
  <p class="error-title">{text.title}</p>
  <p class="error-body">{text.body}</p>
  {#if showChangeModel || showRetry}
    <div class="error-actions">
      {#if showChangeModel}
        <button type="button" class="text-action" onclick={onChangeModel}
          >{t('thread.changeModel')}</button
        >
      {/if}
      {#if showRetry}
        <button type="button" class="text-action" onclick={onRetry}>{t('thread.retry')}</button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .error-box {
    border: 1px solid color-mix(in oklab, var(--sem-critical) 45%, transparent);
    background: color-mix(in oklab, var(--sem-critical) 10%, transparent);
    border-radius: var(--radius-panel);
    padding: var(--space-3) var(--space-4);
    margin-top: var(--space-2);
  }

  .error-title {
    margin: 0;
    font-weight: 600;
    color: var(--sem-critical);
  }

  .error-body {
    margin: var(--space-1) 0 0;
  }

  .error-actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    margin-top: var(--space-2);
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
</style>
