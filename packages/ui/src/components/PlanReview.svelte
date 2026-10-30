<!--
  roadmap U8 and §3.8. The run pauses before it executes a Research plan. This card shows the
  steps and three answers: Approve, Edit (the steps become editable inline, and Save sends them
  back), and Continue without review, which also turns review off for the thread. Stop stays here
  too, because while the run waits the composer shows the waiting state instead of Stop.

  Editing is a local draft: the steps the server holds are not touched until the user saves.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import { IconClose } from '@sofee/icons';
  import IconButton from './IconButton.svelte';
  import type { PlanStepView } from '../types.js';

  interface Props {
    steps: readonly PlanStepView[];
    t: Translate;
    busy?: boolean;
    onApprove: () => void;
    onEdit: (steps: string[]) => void;
    onSkipReview: () => void;
    onStop: () => void;
  }

  let { steps, t, busy = false, onApprove, onEdit, onSkipReview, onStop }: Props = $props();

  const titleId = `review-title-${Math.random().toString(36).slice(2, 8)}`;
  let editing = $state(false);
  let draft = $state<string[]>([]);
  let hasStep = $derived(draft.some((step) => step.trim().length > 0));

  function startEditing(): void {
    draft = steps.map((step) => step.content);
    editing = true;
  }

  function cancelEditing(): void {
    editing = false;
  }

  function saveEditing(): void {
    if (!hasStep) return;
    onEdit([...draft]);
    editing = false;
  }

  function removeStep(index: number): void {
    draft = draft.filter((_step, i) => i !== index);
  }

  function addStep(): void {
    draft = [...draft, ''];
  }
</script>

<section class="review" aria-labelledby={titleId}>
  <h3 class="title" id={titleId}>{t('agent.review.title')}</h3>
  <p class="body-copy">{t('agent.review.body')}</p>

  {#if editing}
    <ol class="steps">
      {#each draft as _step, i (i)}
        <li class="step-row">
          <input
            type="text"
            class="step-input"
            bind:value={draft[i]}
            aria-label={t('agent.review.stepLabel', { number: i + 1 })}
            disabled={busy}
          />
          <IconButton
            icon={IconClose}
            label={t('agent.review.removeStep')}
            tooltip={t('agent.review.removeStep')}
            onclick={() => removeStep(i)}
          />
        </li>
      {/each}
    </ol>
    <div class="actions">
      <button type="button" class="ghost" onclick={addStep} disabled={busy}>
        {t('agent.review.addStep')}
      </button>
    </div>
    {#if !hasStep}<p class="need-step">{t('agent.review.needStep')}</p>{/if}
    <div class="actions">
      <button type="button" class="primary" onclick={saveEditing} disabled={busy || !hasStep}>
        {t('agent.review.saveEdit')}
      </button>
      <button type="button" class="ghost" onclick={cancelEditing} disabled={busy}>
        {t('agent.review.cancelEdit')}
      </button>
    </div>
  {:else}
    <ol class="steps">
      {#each steps as step, i (i)}
        <li class="step-row static">
          <span class="number" aria-hidden="true">{i + 1}</span>
          <span class="content">{step.content}</span>
        </li>
      {/each}
    </ol>
    <div class="actions">
      <button type="button" class="primary" onclick={onApprove} disabled={busy}>
        {t('agent.review.approve')}
      </button>
      <button type="button" class="ghost" onclick={startEditing} disabled={busy}>
        {t('agent.review.edit')}
      </button>
      <button type="button" class="ghost" onclick={onSkipReview} disabled={busy}>
        {t('agent.review.skipForThread')}
      </button>
      <button type="button" class="text" onclick={onStop} disabled={busy}>
        {t('agent.review.stop')}
      </button>
    </div>
    <p class="hint">{t('agent.review.skipHint')}</p>
  {/if}
</section>

<style>
  .review {
    min-width: 0;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--p-line-2);
    border-radius: var(--radius-panel);
    background: var(--p-surf);
  }

  .title {
    margin: 0;
    font-family: var(--p-display);
    font-size: 15px;
    font-weight: 600;
    color: var(--p-ink);
  }

  .body-copy,
  .hint,
  .need-step {
    margin: var(--space-1) 0 0;
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.5;
  }

  .need-step {
    color: var(--sem-warning);
  }

  .steps {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: var(--space-3) 0 0;
    padding: 0;
    list-style: none;
  }

  .step-row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }

  .number {
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 1px solid var(--p-line-2);
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px;
  }

  .content {
    min-width: 0;
    overflow-wrap: anywhere;
    font-size: 14px;
  }

  .step-input {
    flex: 1;
    min-width: 0;
    min-height: var(--target-min);
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: 1px solid var(--p-line);
    background: var(--p-surf-2);
    color: var(--p-ink);
    font: inherit;
    font-size: 14px;
  }

  .step-input:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }

  button {
    min-height: var(--target-min);
    padding: 0 var(--space-4);
    border-radius: var(--radius-icon-btn);
    font: inherit;
    font-size: 14px;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  button:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .primary {
    border: 1px solid var(--p-acc);
    background: var(--p-acc);
    color: var(--p-bg);
    font-weight: 600;
  }

  .ghost {
    border: 1px solid var(--p-line);
    background: transparent;
    color: var(--p-ink);
  }

  .ghost:hover:not(:disabled) {
    border-color: var(--p-line-2);
    background: var(--p-surf-2);
  }

  .text {
    border: none;
    background: none;
    padding: 0 var(--space-2);
    color: var(--p-mut);
    text-decoration: underline;
    text-underline-offset: 2px;
  }
</style>
