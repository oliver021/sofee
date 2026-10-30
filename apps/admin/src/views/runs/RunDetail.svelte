<script lang="ts">
  import { onMount } from 'svelte';
  import { IconExternalLink } from '@sofee/icons';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import { api } from '../../lib/api.js';
  import {
    formatCost,
    formatDateTime,
    formatInt,
    formatMs,
    messageOf,
    safeHref,
  } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { AdminRunDetail } from '../../lib/types.js';
  import RunTimeline from './RunTimeline.svelte';
  import {
    ACTIVE_RUN_STATUSES,
    RUN_ERROR_LABELS,
    RUN_MODE_LABELS,
    RUN_STATUS_LABELS,
    RUN_STATUS_TONE,
  } from './run-meta.js';

  interface Props {
    runId: string;
    onchanged: () => void;
  }

  let { runId, onchanged }: Props = $props();

  let run = $state<AdminRunDetail | null>(null);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let confirmCancel = $state(false);
  let cancelBusy = $state(false);

  let isActive = $derived(run !== null && ACTIVE_RUN_STATUSES.includes(run.status));
  let traceHref = $derived(safeHref(run?.trace_url ?? null));

  async function load() {
    loading = true;
    loadError = null;
    try {
      run = await api<AdminRunDetail>(`/admin/runs/${runId}`);
    } catch (e) {
      loadError = messageOf(e, 'No se pudo cargar el run');
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function cancel() {
    confirmCancel = false;
    cancelBusy = true;
    try {
      await api(`/admin/runs/${runId}/cancel`, { method: 'POST' });
      ui.notify('Cancelación pedida. El estado se actualiza en unos segundos.');
      onchanged();
      await load();
    } catch (e) {
      ui.notify(messageOf(e, 'No se pudo cancelar el run'), 'error');
    } finally {
      cancelBusy = false;
    }
  }

  function citationTitle(citation: Record<string, unknown>): string {
    const title = citation.title;
    return typeof title === 'string' && title.length > 0 ? title : 'Sin título';
  }

  function citationUrl(citation: Record<string, unknown>): string | null {
    return typeof citation.url === 'string' ? citation.url : null;
  }

  function citationText(citation: Record<string, unknown>, key: string): string {
    const value = citation[key];
    return typeof value === 'string' ? value : '';
  }
</script>

{#if loading}
  <p class="muted">Cargando run…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if run}
  <div class="stack">
    <header class="head">
      <span class="badge {RUN_STATUS_TONE[run.status]}">{RUN_STATUS_LABELS[run.status]}</span>
      <span class="muted small">{formatDateTime(run.created_at)}</span>
      <span class="muted small">{run.user_email ?? '—'}</span>
    </header>

    <dl class="facts">
      <dt>Modo</dt>
      <dd>{RUN_MODE_LABELS[run.mode] ?? run.mode}</dd>
      <dt>Modelo</dt>
      <dd>{run.model_label ?? run.catalog_slug ?? '—'}</dd>
      <dt>Perfil</dt>
      <dd>
        {run.profile_version !== null ? `versión ${run.profile_version}` : 'defaults de código'}
      </dd>
      <dt>Duración</dt>
      <dd class="tabular-nums">{formatMs(run.duration_ms)} · TTFT {formatMs(run.ttft_ms)}</dd>
      <dt>Tokens</dt>
      <dd class="tabular-nums">
        {formatInt(run.input_tokens)} entrada · {formatInt(run.output_tokens)} salida
      </dd>
      <dt>Coste estimado</dt>
      <dd class="tabular-nums">{formatCost(run.cost_estimate)}</dd>
      <dt>Citas alucinadas</dt>
      <dd class="tabular-nums">{formatInt(run.hallucinated_citations)}</dd>
      {#if run.error_code}
        <dt>Error</dt>
        <dd>
          <span class="badge danger">{run.error_code}</span>
          {RUN_ERROR_LABELS[run.error_code] ?? ''}
        </dd>
      {/if}
    </dl>

    {#if run.error_message}
      <p class="notice error" role="status">{run.error_message}</p>
    {/if}

    <div class="trace">
      {#if traceHref}
        <a class="link" href={traceHref} target="_blank" rel="noopener noreferrer">
          Abrir en LangSmith
          <IconExternalLink size={14} />
        </a>
      {:else}
        <span class="muted small">Sin enlace de trazas para este run.</span>
      {/if}
    </div>

    <section class="block" aria-labelledby="run-question">
      <h3 id="run-question" class="section-title">Pregunta</h3>
      <p class="prose">{run.question ?? '—'}</p>
    </section>

    <section class="block" aria-labelledby="run-answer">
      <h3 id="run-answer" class="section-title">Respuesta</h3>
      {#if run.answer}
        <p class="prose">{run.answer}</p>
      {:else}
        <p class="muted small">Sin texto: el run no llegó a responder.</p>
      {/if}

      {#if run.citations && run.citations.length > 0}
        <h4 class="sub-title">Fuentes citadas</h4>
        <ol class="citations">
          {#each run.citations as citation, index (index)}
            {@const url = safeHref(citationUrl(citation))}
            <li>
              <span class="strong">{citationTitle(citation)}</span>
              <span class="muted small">
                · {citationText(citation, 'kind') || 'fuente'}
              </span>
              {#if url}
                <a class="link small" href={url} target="_blank" rel="noopener noreferrer">{url}</a>
              {:else if citationText(citation, 'ref')}
                <span class="mono muted small">{citationText(citation, 'ref')}</span>
              {/if}
              {#if citationText(citation, 'snippet')}
                <p class="snippet">{citationText(citation, 'snippet')}</p>
              {/if}
            </li>
          {/each}
        </ol>
      {/if}
    </section>

    <section class="block" aria-labelledby="run-timeline">
      <h3 id="run-timeline" class="section-title">Línea de tiempo</h3>
      <RunTimeline events={run.events} />
    </section>

    {#if isActive}
      <div class="actions">
        <button
          class="btn danger"
          type="button"
          onclick={() => (confirmCancel = true)}
          disabled={cancelBusy}
        >
          Cancelar run
        </button>
      </div>
    {/if}
  </div>
{/if}

<ConfirmDialog
  open={confirmCancel}
  title="Cancelar run"
  confirmLabel="Cancelar run"
  danger
  busy={cancelBusy}
  onconfirm={cancel}
  oncancel={() => (confirmCancel = false)}
>
  El run se detiene y queda como cancelado. El texto que ya llegó se conserva y la acción queda
  auditada.
</ConfirmDialog>

<style>
  .stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
  }

  .facts {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 8px 16px;
    margin: 0;
    font-size: 13.5px;
  }

  .facts dt {
    color: var(--p-mut);
  }

  .facts dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .notice {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .notice.error {
    border-color: var(--sem-critical);
    color: var(--sem-critical);
  }

  .trace {
    font-size: 13.5px;
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
  }

  .block .section-title,
  .sub-title {
    margin: 0;
  }

  .sub-title {
    margin-top: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--p-mut);
  }

  .prose {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    font-size: 14px;
    line-height: 1.6;
  }

  .citations {
    margin: 0;
    padding-left: 18px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13.5px;
  }

  .snippet {
    margin: 2px 0 0;
    color: var(--p-mut);
    font-size: 12.5px;
  }

  .small {
    font-size: 13px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
  }
</style>
