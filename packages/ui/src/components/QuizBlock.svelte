<!--
  roadmap U12: Learn ends with a short quiz, folded away by default. Each answer stays hidden until
  the reader asks for it, so trying the question first is the easy path. Native disclosure for the
  whole quiz, one toggle per question.
-->
<script lang="ts">
  import type { RunQuizItem, Translate } from '@sofee/core';
  import { SvelteSet } from 'svelte/reactivity';

  interface Props {
    items: readonly RunQuizItem[];
    t: Translate;
  }

  let { items, t }: Props = $props();

  const revealed = new SvelteSet<number>();

  function toggle(index: number): void {
    if (revealed.has(index)) revealed.delete(index);
    else revealed.add(index);
  }
</script>

<details class="quiz">
  <summary>{t('agent.quiz.heading')}</summary>
  <ol class="items">
    {#each items as item, i (i)}
      {@const open = revealed.has(i)}
      <li class="item">
        <p class="question">{item.question}</p>
        {#if open}
          <p class="answer">
            <span class="answer-label">{t('agent.quiz.answer')}</span>
            {item.answer}
          </p>
        {/if}
        <button type="button" class="reveal" aria-expanded={open} onclick={() => toggle(i)}>
          {open ? t('agent.quiz.hide') : t('agent.quiz.reveal')}
        </button>
      </li>
    {/each}
  </ol>
</details>

<style>
  .quiz {
    min-width: 0;
    border: 1px solid var(--p-line);
    border-radius: var(--radius-panel);
    background: var(--p-surf);
    padding: 0 var(--space-4);
  }

  summary {
    min-height: var(--target-min);
    display: flex;
    align-items: center;
    font-weight: 600;
    color: var(--p-ink);
    cursor: pointer;
  }

  summary:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: var(--radius-icon-btn);
  }

  .items {
    margin: 0 0 var(--space-3);
    padding: 0 0 0 1.3em;
  }

  .item {
    padding: var(--space-1) 0;
    font-size: 14px;
  }

  .question {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .answer {
    margin: var(--space-1) 0 0;
    color: var(--p-mut);
    overflow-wrap: anywhere;
  }

  .answer-label {
    color: var(--p-ink);
    font-weight: 600;
    margin-inline-end: var(--space-1);
  }

  .reveal {
    min-height: var(--target-min);
    padding: 0 var(--space-2);
    border: none;
    background: none;
    color: var(--p-acc);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }

  .reveal:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: var(--radius-icon-btn);
  }
</style>
