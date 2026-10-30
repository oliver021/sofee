<script lang="ts">
  import type { RunEvent } from '../../lib/types.js';
  import { describeEvent } from './timeline.js';

  interface Props {
    events: RunEvent[];
  }

  let { events }: Props = $props();

  let entries = $derived(events.map(describeEvent));
</script>

{#if entries.length === 0}
  <p class="muted small">Este run no tiene eventos registrados.</p>
{:else}
  <ol class="timeline">
    {#each entries as entry (entry.seq)}
      <li class="item {entry.tone}">
        <div class="meta">
          <span class="seq tabular-nums">#{entry.seq}</span>
          <span class="kind">{entry.kind}</span>
        </div>
        <div class="body">
          <p class="title-line">{entry.title}</p>
          {#if entry.detail}
            <p class="detail mono">{entry.detail}</p>
          {/if}
          {#if entry.lines.length > 0}
            <ul class="lines">
              {#each entry.lines as line, index (index)}
                <li>{line}</li>
              {/each}
            </ul>
          {/if}
        </div>
      </li>
    {/each}
  </ol>
{/if}

<style>
  .timeline {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    border-left: 2px solid var(--p-line);
    margin-left: 6px;
  }

  .item {
    position: relative;
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr);
    gap: 12px;
    padding: 4px 0 12px 16px;
  }

  .item::before {
    content: '';
    position: absolute;
    left: -6px;
    top: 8px;
    width: 10px;
    height: 10px;
    border-radius: 999px;
    background: var(--p-line-2);
  }

  .item.ok::before {
    background: var(--sem-success);
  }

  .item.warn::before {
    background: var(--sem-warning);
  }

  .item.error::before {
    background: var(--sem-critical);
  }

  .meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 12px;
  }

  .seq {
    color: var(--p-mut);
  }

  .kind {
    font-weight: 600;
    color: var(--p-mut);
  }

  .body {
    min-width: 0;
  }

  .title-line {
    margin: 0;
    font-size: 14px;
    overflow-wrap: anywhere;
  }

  .item.error .title-line {
    color: var(--sem-critical);
  }

  .detail {
    margin: 2px 0 0;
    font-size: 12.5px;
    color: var(--p-mut);
    overflow-wrap: anywhere;
    white-space: pre-wrap;
  }

  .lines {
    margin: 4px 0 0;
    padding-left: 18px;
    font-size: 13px;
    color: var(--p-mut);
  }

  .small {
    font-size: 13px;
  }
</style>
