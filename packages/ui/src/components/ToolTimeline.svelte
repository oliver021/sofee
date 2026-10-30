<!--
  roadmap U5: the Tool calls panel as a timeline, grouped by run. Each call shows its name, a short
  preview of its arguments, its status and how long it took. The main agent's calls stay open; each
  subagent's calls fold away under its name, so a long research run stays readable.
-->
<script lang="ts">
  import type { ToolRowView, ToolRunView } from '../types.js';

  interface Props {
    runs: readonly ToolRunView[];
  }

  let { runs }: Props = $props();
</script>

{#snippet rowList(rows: readonly ToolRowView[])}
  <ul class="rows">
    {#each rows as row (row.id)}
      <li class="row {row.status}">
        <span class="row-head">
          <span class="name">{row.name}</span>
          <span class="status">{row.statusLabel}</span>
        </span>
        {#if row.argsPreview}
          <code class="args" title={row.argsPreview}>{row.argsPreview}</code>
        {/if}
        <span class="duration">{row.durationLabel}</span>
      </li>
    {/each}
  </ul>
{/snippet}

<div class="timeline">
  {#each runs as run (run.runId)}
    <section class="run">
      <h3 class="run-title">{run.title}</h3>
      {#each run.groups as group (group.key)}
        {#if group.main}
          <div class="group">
            <p class="group-label">{group.label}</p>
            {@render rowList(group.rows)}
          </div>
        {:else}
          <details class="group subgroup" open>
            <summary>
              <span class="group-label">{group.label}</span>
              <span class="count">{group.rows.length}</span>
            </summary>
            {@render rowList(group.rows)}
          </details>
        {/if}
      {/each}
    </section>
  {/each}
</div>

<style>
  .timeline {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
  }

  .run {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  .run-title {
    margin: 0;
    font-family: var(--p-display);
    font-size: 13px;
    font-weight: 600;
    color: var(--p-ink);
    overflow-wrap: anywhere;
  }

  .group {
    min-width: 0;
  }

  .group-label {
    margin: 0 0 var(--space-1);
    color: var(--p-mut);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    min-height: var(--target-min);
    cursor: pointer;
  }

  summary:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: var(--radius-icon-btn);
  }

  summary .group-label {
    margin: 0;
  }

  .count {
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px;
  }

  .rows {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: 1px solid var(--p-line);
    background: var(--p-surf);
    font-size: 13px;
  }

  .row.error {
    border-color: color-mix(in oklab, var(--sem-critical) 45%, transparent);
  }

  .row-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    min-width: 0;
  }

  .name {
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--p-ink);
  }

  .status,
  .duration {
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px;
  }

  .status {
    flex-shrink: 0;
  }

  .row.success .status {
    color: var(--sem-success);
  }

  .row.error .status {
    color: var(--sem-critical);
  }

  .args {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--p-mut);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
  }
</style>
