<!--
  roadmap U11: Explore answers with a few directions. Each one is a chip that sends its title as the
  next question, in the same mode. The "why" sits under the title, so the reader sees what each
  direction is for before choosing.
-->
<script lang="ts">
  import type { RunDirection, Translate } from '@sofee/core';

  interface Props {
    directions: readonly RunDirection[];
    t: Translate;
    onPick: (title: string) => void;
  }

  let { directions, t, onPick }: Props = $props();
</script>

<section class="directions" aria-label={t('agent.directions.heading')}>
  <p class="heading">{t('agent.directions.heading')}</p>
  <ul class="chips">
    {#each directions as direction, i (i)}
      <li>
        <button type="button" class="chip" onclick={() => onPick(direction.title)}>
          <span class="chip-title">{direction.title}</span>
          <span class="chip-why">{direction.why}</span>
        </button>
      </li>
    {/each}
  </ul>
</section>

<style>
  .heading {
    margin: 0 0 var(--space-2);
    color: var(--p-mut);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .chip {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    min-height: var(--target-min);
    max-width: 320px;
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-panel);
    border: 1px solid var(--p-line);
    background: var(--p-surf);
    color: var(--p-ink);
    font: inherit;
    text-align: start;
    cursor: pointer;
  }

  .chip:hover {
    border-color: var(--p-acc);
    background: var(--p-surf-2);
  }

  .chip:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .chip-title {
    font-size: 14px;
    font-weight: 600;
    overflow-wrap: anywhere;
  }

  .chip-why {
    color: var(--p-mut);
    font-size: 12px;
    line-height: 1.4;
    overflow-wrap: anywhere;
  }
</style>
