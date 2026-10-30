<!--
  roadmap U2 and ux-foundations.md §3.3. While the run works, the plan is a live checklist above
  the reply: "Trabajando · paso 2 de 5", with each step pending, in progress or done. When the run
  ends it folds into one line ("5 pasos · 12 fuentes · 48 s") that expands on demand. The headline
  row holds its height, and the list only changes when the plan itself does, so the reply below it
  does not move while it streams.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import { IconCheck, IconChevronDown } from '@sofee/icons';
  import VisuallyHidden from './VisuallyHidden.svelte';
  import type { PlanView } from '../types.js';

  interface Props {
    plan: PlanView;
    t: Translate;
  }

  let { plan, t }: Props = $props();

  let expanded = $state(false);
  const listId = `plan-steps-${Math.random().toString(36).slice(2, 8)}`;
</script>

{#if plan.running}
  <section class="plan running" aria-label={t('agent.plan.label')}>
    <p class="head">
      <span class="pulse" aria-hidden="true"></span>
      <span class="headline">{plan.headline}</span>
      {#if plan.liveSources}<span class="meta">{plan.liveSources}</span>{/if}
    </p>
    <ol class="steps">
      {#each plan.steps as step, i (i)}
        <li class="step {step.status}">
          <span class="glyph" aria-hidden="true">
            {#if step.status === 'completed'}<IconCheck size={14} />{/if}
          </span>
          <span class="content">{step.content}</span>
          <VisuallyHidden>{step.statusLabel}</VisuallyHidden>
        </li>
      {/each}
    </ol>
  </section>
{:else if plan.steps.length > 0}
  <section class="plan finished" aria-label={t('agent.plan.label')}>
    <button
      type="button"
      class="toggle"
      aria-expanded={expanded}
      aria-controls={listId}
      title={expanded ? t('agent.plan.collapse') : t('agent.plan.expand')}
      onclick={() => (expanded = !expanded)}
    >
      <span class="check" aria-hidden="true"><IconCheck size={14} /></span>
      <span class="summary">{plan.summary}</span>
      <span class="chevron" class:open={expanded} aria-hidden="true">
        <IconChevronDown size={14} />
      </span>
    </button>
    {#if expanded}
      <ol class="steps" id={listId}>
        {#each plan.steps as step, i (i)}
          <li class="step {step.status}">
            <span class="glyph" aria-hidden="true">
              {#if step.status === 'completed'}<IconCheck size={14} />{/if}
            </span>
            <span class="content">{step.content}</span>
            <VisuallyHidden>{step.statusLabel}</VisuallyHidden>
          </li>
        {/each}
      </ol>
    {/if}
  </section>
{/if}

<style>
  .plan {
    min-width: 0;
    font-size: 14px;
    color: var(--p-mut);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-panel);
    background: var(--p-surf);
    padding: var(--space-2) var(--space-3);
  }

  /* The headline row has a fixed minimum, so the text below it keeps its place while the first
     status arrives. */
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    min-height: 1.6em;
    margin: 0;
    color: var(--p-ink);
  }

  .headline {
    font-weight: 600;
  }

  .meta {
    color: var(--p-mut);
    font-size: 12px;
  }

  .pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--p-acc);
    animation: plan-pulse 1.4s ease-in-out infinite;
  }

  @keyframes plan-pulse {
    0%,
    100% {
      opacity: 0.35;
    }
    50% {
      opacity: 1;
    }
  }

  .steps {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin: var(--space-2) 0 0;
    padding: 0;
    list-style: none;
  }

  .step {
    display: flex;
    align-items: flex-start;
    gap: var(--space-2);
    min-width: 0;
  }

  .glyph {
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    margin-top: 2px;
    border-radius: 50%;
    border: 1px solid var(--p-line-2);
    color: var(--p-ink);
  }

  .step.in_progress .glyph {
    border-color: var(--p-acc);
    box-shadow: inset 0 0 0 4px var(--p-surf);
    background: var(--p-acc);
  }

  .step.completed .glyph {
    border-color: var(--sem-success);
    color: var(--sem-success);
  }

  .step.completed .content {
    color: var(--p-mut);
  }

  .step.in_progress .content {
    color: var(--p-ink);
    font-weight: 600;
  }

  .content {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--target-min);
    padding: 0;
    border: none;
    background: none;
    color: var(--p-mut);
    font: inherit;
    text-align: start;
    cursor: pointer;
  }

  .toggle:hover .summary {
    color: var(--p-ink);
  }

  .toggle:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: var(--radius-icon-btn);
  }

  .check {
    display: inline-flex;
    color: var(--sem-success);
  }

  .summary {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .chevron {
    display: inline-flex;
    transition: rotate var(--motion-menu-duration) var(--motion-menu-easing);
  }

  .chevron.open {
    rotate: 180deg;
  }

  @media (prefers-reduced-motion: reduce) {
    .pulse {
      animation: none;
      opacity: 1;
    }

    .chevron {
      transition: none;
    }
  }
</style>
