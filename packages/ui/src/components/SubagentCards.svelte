<!--
  roadmap U9: one card per subagent, with its name, its task and its status. Its summary sits behind
  a native disclosure, so it is keyboard reachable without any script. The cards only take the
  space the subagents need, and they hold still while the reply below them streams.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import type { SubagentView } from '../types.js';

  interface Props {
    subagents: readonly SubagentView[];
    heading: string;
    t: Translate;
  }

  let { subagents, heading, t }: Props = $props();
</script>

<section class="subagents" aria-label={heading}>
  <p class="heading">{heading}</p>
  <ul class="cards">
    {#each subagents as agent (agent.id)}
      <li class="card {agent.status}">
        <details>
          <summary>
            <span class="name">{agent.name}</span>
            <span class="task">{agent.task}</span>
            <span class="status">{agent.statusLabel}</span>
          </summary>
          <p class="detail">{agent.summary ?? t('agent.subagents.noSummary')}</p>
        </details>
      </li>
    {/each}
  </ul>
</section>

<style>
  .subagents {
    min-width: 0;
  }

  .heading {
    margin: 0 0 var(--space-2);
    color: var(--p-mut);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .cards {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .card {
    min-width: 0;
    border: 1px solid var(--p-line);
    border-radius: var(--radius-icon-btn);
    background: var(--p-surf);
  }

  summary {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-2);
    min-height: var(--target-min);
    padding: var(--space-1) var(--space-3);
    cursor: pointer;
    font-size: 13px;
    list-style-position: inside;
  }

  summary:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
    border-radius: var(--radius-icon-btn);
  }

  .name {
    font-weight: 600;
    color: var(--p-ink);
  }

  .task {
    flex: 1;
    min-width: 0;
    color: var(--p-mut);
    overflow-wrap: anywhere;
  }

  .status {
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px;
    letter-spacing: 0.02em;
  }

  .card.success .status {
    color: var(--sem-success);
  }

  .card.error .status {
    color: var(--sem-critical);
  }

  .detail {
    margin: 0;
    padding: 0 var(--space-3) var(--space-2);
    color: var(--p-ink);
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
</style>
