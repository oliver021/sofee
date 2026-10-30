<script lang="ts">
  import { onMount } from 'svelte';
  import { IconRefresh } from '@sofee/icons';
  import Drawer from '../../components/Drawer.svelte';
  import { api } from '../../lib/api.js';
  import {
    formatCost,
    formatDateTime,
    formatInt,
    formatMs,
    localToIso,
    messageOf,
  } from '../../lib/format.js';
  import { toQuery } from '../../lib/query.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { AdminRun, AdminRunPage } from '../../lib/types.js';
  import RunDetail from './RunDetail.svelte';
  import {
    RUN_ERROR_LABELS,
    RUN_MODE_LABELS,
    RUN_STATUS_LABELS,
    RUN_STATUS_TONE,
  } from './run-meta.js';

  const PAGE_SIZE = 50;
  const STATUSES = [
    'queued',
    'running',
    'interrupted',
    'completed',
    'failed',
    'cancelled',
  ] as const;

  // Filter inputs are kept apart from the applied filters, so typing does not refetch.
  let userInput = $state('');
  let modeInput = $state('');
  let statusInput = $state('');
  let catalogInput = $state('');
  let startInput = $state('');
  let endInput = $state('');

  let applied = $state({
    user: '',
    mode: '',
    status: '',
    catalog: '',
    start: '',
    end: '',
  });

  let runs = $state<AdminRun[]>([]);
  let nextCursor = $state<string | null>(null);
  let loading = $state(true);
  let loadingMore = $state(false);
  let loadError = $state<string | null>(null);
  let selectedRunId = $state<string | null>(null);

  // Other views (feedback, home) ask for a run through ui.openRun; open its drawer on arrival.
  $effect(() => {
    const focus = ui.runFocus;
    if (focus) {
      selectedRunId = focus;
      ui.runFocus = null;
    }
  });

  function buildQuery(cursor: string | null): string {
    return toQuery({
      limit: PAGE_SIZE,
      user: applied.user,
      mode: applied.mode,
      status: applied.status,
      catalog_slug: applied.catalog,
      start: localToIso(applied.start),
      end: localToIso(applied.end),
      cursor,
    });
  }

  async function load(reset: boolean) {
    if (reset) {
      loading = true;
      nextCursor = null;
    } else {
      loadingMore = true;
    }
    loadError = null;
    try {
      const page = await api<AdminRunPage>(`/admin/runs${buildQuery(reset ? null : nextCursor)}`);
      runs = reset ? page.items : [...runs, ...page.items];
      nextCursor = page.next_cursor;
    } catch (e) {
      loadError = messageOf(e, 'No se pudieron cargar los runs');
    } finally {
      loading = false;
      loadingMore = false;
    }
  }

  onMount(() => {
    void load(true);
  });

  function applyFilters() {
    applied = {
      user: userInput.trim(),
      mode: modeInput,
      status: statusInput,
      catalog: catalogInput.trim(),
      start: startInput,
      end: endInput,
    };
    void load(true);
  }

  function clearFilters() {
    userInput = '';
    modeInput = '';
    statusInput = '';
    catalogInput = '';
    startInput = '';
    endInput = '';
    applyFilters();
  }

  function modelLabel(run: AdminRun): string {
    return run.model_label ?? run.catalog_slug ?? '—';
  }

  function tokens(run: AdminRun): string {
    return `${formatInt(run.input_tokens)} / ${formatInt(run.output_tokens)}`;
  }
</script>

<div class="view-head">
  <div>
    <h1>Runs</h1>
    <p class="muted intro">Ejecuciones del agente. Abre un run para ver su línea de tiempo.</p>
  </div>
  <button class="btn" type="button" onclick={() => load(true)} disabled={loading}>
    <IconRefresh size={15} />
    Actualizar
  </button>
</div>

<form
  class="filters"
  onsubmit={(event) => {
    event.preventDefault();
    applyFilters();
  }}
>
  <label class="field">
    <span class="field-label">Usuario</span>
    <input class="input" type="search" placeholder="Correo, nombre o ID" bind:value={userInput} />
  </label>
  <label class="field">
    <span class="field-label">Modo</span>
    <select class="input" bind:value={modeInput}>
      <option value="">Todos</option>
      <option value="learn">Aprender</option>
      <option value="research">Investigar</option>
      <option value="explore">Explorar</option>
    </select>
  </label>
  <label class="field">
    <span class="field-label">Estado</span>
    <select class="input" bind:value={statusInput}>
      <option value="">Todos</option>
      {#each STATUSES as status (status)}
        <option value={status}>{RUN_STATUS_LABELS[status]}</option>
      {/each}
    </select>
  </label>
  <label class="field">
    <span class="field-label">Modelo (slug)</span>
    <input class="input mono" type="text" placeholder="fast" bind:value={catalogInput} />
  </label>
  <label class="field">
    <span class="field-label">Desde</span>
    <input class="input" type="datetime-local" bind:value={startInput} />
  </label>
  <label class="field">
    <span class="field-label">Hasta</span>
    <input class="input" type="datetime-local" bind:value={endInput} />
  </label>
  <div class="filter-actions">
    <button class="btn primary" type="submit" disabled={loading}>Filtrar</button>
    <button class="btn ghost" type="button" onclick={clearFilters}>Limpiar</button>
  </div>
</form>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if runs.length === 0}
  <div class="empty">
    <p>No hay runs que coincidan con los filtros.</p>
  </div>
{:else}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Creado</th>
          <th>Usuario</th>
          <th>Modo</th>
          <th>Modelo</th>
          <th>Estado</th>
          <th>Duración</th>
          <th>Tokens (entrada / salida)</th>
          <th>Coste</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        {#each runs as run (run.id)}
          <tr>
            <td>
              <button
                class="link-btn tabular-nums"
                type="button"
                onclick={() => (selectedRunId = run.id)}
              >
                {formatDateTime(run.created_at)}
              </button>
            </td>
            <td>{run.user_email ?? '—'}</td>
            <td class="mono muted">{RUN_MODE_LABELS[run.mode] ?? run.mode}</td>
            <td class="mono muted">{modelLabel(run)}</td>
            <td>
              <span class="badge {RUN_STATUS_TONE[run.status]}"
                >{RUN_STATUS_LABELS[run.status]}</span
              >
            </td>
            <td class="tabular-nums muted">{formatMs(run.duration_ms)}</td>
            <td class="tabular-nums muted">{tokens(run)}</td>
            <td class="tabular-nums muted">{formatCost(run.cost_estimate)}</td>
            <td>
              {#if run.error_code}
                <span
                  class="badge danger"
                  title={RUN_ERROR_LABELS[run.error_code] ?? run.error_code}
                >
                  {run.error_code}
                </span>
              {:else}
                <span class="muted">—</span>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if nextCursor}
    <div class="pager">
      <button class="btn" type="button" onclick={() => load(false)} disabled={loadingMore}>
        {loadingMore ? 'Cargando…' : 'Cargar más'}
      </button>
    </div>
  {/if}
{/if}

<Drawer
  open={selectedRunId !== null}
  title={selectedRunId ? `Run ${selectedRunId.slice(0, 8)}` : ''}
  onclose={() => (selectedRunId = null)}
>
  {#if selectedRunId}
    {#key selectedRunId}
      <RunDetail runId={selectedRunId} onchanged={() => load(true)} />
    {/key}
  {/if}
</Drawer>

<style>
  .view-head h1 {
    margin: 0;
  }

  .intro {
    margin: 4px 0 0;
    font-size: 13.5px;
  }

  .filters {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    align-items: end;
    margin-bottom: 16px;
    padding: 14px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
  }

  .filter-actions {
    display: flex;
    gap: 8px;
  }

  .link-btn {
    padding: 0;
    border: none;
    background: none;
    color: var(--p-acc);
    font: inherit;
    cursor: pointer;
    text-align: left;
  }

  .link-btn:hover {
    text-decoration: underline;
  }

  .pager {
    display: flex;
    justify-content: center;
    margin-top: 16px;
  }
</style>
