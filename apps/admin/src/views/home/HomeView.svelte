<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../../lib/api.js';
  import {
    formatDateTime,
    formatInt,
    formatMs,
    formatPercent,
    messageOf,
  } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type {
    AdminFeedbackPage,
    AdminRunPage,
    CatalogEntry,
    UsageReport,
  } from '../../lib/types.js';

  // Each block loads on its own: one failing endpoint must not hide the rest of the home screen.
  let loading = $state(true);
  let usage = $state<UsageReport | null>(null);
  let usageError = $state<string | null>(null);
  let unreviewed = $state<{ total: number; bad: number; more: boolean } | null>(null);
  let feedbackError = $state<string | null>(null);
  let unavailable = $state<CatalogEntry[]>([]);
  let catalogError = $state<string | null>(null);
  let failedRuns = $state<AdminRunPage['items']>([]);
  let runsError = $state<string | null>(null);

  // Failing bindings: only the ones with at least one failed run today, worst first.
  let failingBindings = $derived(
    (usage?.bindings ?? [])
      .filter((b) => b.failed_runs > 0)
      .sort((a, b) => (b.error_rate ?? 0) - (a.error_rate ?? 0)),
  );

  async function load() {
    loading = true;
    const [usageResult, feedbackResult, catalogResult, runsResult] = await Promise.allSettled([
      api<UsageReport>('/admin/usage?days=1'),
      api<AdminFeedbackPage>('/admin/feedback?reviewed=false&limit=200'),
      api<CatalogEntry[]>('/admin/catalog'),
      api<AdminRunPage>('/admin/runs?status=failed&limit=8'),
    ]);

    if (usageResult.status === 'fulfilled') {
      usage = usageResult.value;
      usageError = null;
    } else {
      usage = null;
      usageError = messageOf(usageResult.reason, 'No se pudo cargar el uso de hoy');
    }

    if (feedbackResult.status === 'fulfilled') {
      const page = feedbackResult.value;
      unreviewed = {
        total: page.items.length,
        bad: page.items.filter((f) => f.value === 'bad').length,
        more: page.next_cursor !== null,
      };
      feedbackError = null;
    } else {
      unreviewed = null;
      feedbackError = messageOf(feedbackResult.reason, 'No se pudieron cargar las valoraciones');
    }

    if (catalogResult.status === 'fulfilled') {
      unavailable = catalogResult.value.filter((entry) => !entry.is_available);
      catalogError = null;
    } else {
      unavailable = [];
      catalogError = messageOf(catalogResult.reason, 'No se pudo cargar el catálogo');
    }

    if (runsResult.status === 'fulfilled') {
      failedRuns = runsResult.value.items;
      runsError = null;
    } else {
      failedRuns = [];
      runsError = messageOf(runsResult.reason, 'No se pudieron cargar los errores');
    }

    loading = false;
  }

  onMount(load);
</script>

<div class="view-head">
  <div>
    <h1>Inicio</h1>
    <p class="muted sub">Hoy (día UTC): lo que necesita atención en el agente.</p>
  </div>
  <button class="btn" type="button" onclick={load} disabled={loading}>Actualizar</button>
</div>

<div class="kpis">
  <div class="kpi">
    <span class="kpi-label">Runs de hoy</span>
    {#if usage}
      <span class="kpi-value tabular-nums">{formatInt(usage.totals.runs)}</span>
      <span class="muted small">
        {formatInt(usage.totals.input_tokens)} entrada · {formatInt(usage.totals.output_tokens)} salida
      </span>
    {:else if usageError}
      <span class="error-text small">{usageError}</span>
    {:else}
      <span class="muted">Cargando…</span>
    {/if}
  </div>

  <div class="kpi">
    <span class="kpi-label">Errores de hoy</span>
    {#if usage}
      <span class="kpi-value tabular-nums {usage.totals.failed_runs > 0 ? 'bad' : ''}">
        {formatInt(usage.totals.failed_runs)}
      </span>
      <span class="muted small">tasa {formatPercent(usage.totals.error_rate)}</span>
    {:else if usageError}
      <span class="error-text small">{usageError}</span>
    {:else}
      <span class="muted">Cargando…</span>
    {/if}
  </div>

  <div class="kpi">
    <span class="kpi-label">Latencia de hoy</span>
    {#if usage}
      <span class="kpi-value tabular-nums">{formatMs(usage.latency.duration_p50_ms)}</span>
      <span class="muted small">
        p50 · p95 {formatMs(usage.latency.duration_p95_ms)} · TTFT p50 {formatMs(
          usage.latency.ttft_p50_ms,
        )}
      </span>
    {:else if usageError}
      <span class="error-text small">{usageError}</span>
    {:else}
      <span class="muted">Cargando…</span>
    {/if}
  </div>

  <button class="kpi kpi-button" type="button" onclick={() => ui.switchTo('feedback')}>
    <span class="kpi-label">Valoraciones sin revisar</span>
    {#if unreviewed}
      <span class="kpi-value tabular-nums {unreviewed.bad > 0 ? 'bad' : ''}">
        {unreviewed.total}{unreviewed.more ? '+' : ''}
      </span>
      <span class="muted small">{unreviewed.bad} con pulgar abajo</span>
    {:else if feedbackError}
      <span class="error-text small">{feedbackError}</span>
    {:else}
      <span class="muted">Cargando…</span>
    {/if}
  </button>
</div>

<div class="columns">
  <section class="panel" aria-labelledby="home-failing">
    <div class="panel-head">
      <h2 id="home-failing" class="section-title">Providers con fallos hoy</h2>
      <button class="btn ghost small-btn" type="button" onclick={() => ui.switchTo('usage')}>
        Ver uso
      </button>
    </div>
    {#if usageError}
      <p class="error-text" role="alert">{usageError}</p>
    {:else if !usage}
      <p class="muted small">Cargando…</p>
    {:else if failingBindings.length === 0}
      <p class="muted small">Ningún binding ha fallado hoy.</p>
    {:else}
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Modelo</th>
              <th>Runs</th>
              <th>Fallos</th>
              <th>Tasa</th>
            </tr>
          </thead>
          <tbody>
            {#each failingBindings as b (b.provider_model_id ?? `${b.provider_name}-${b.model_id}`)}
              <tr>
                <td class="strong">{b.provider_name ?? '—'}</td>
                <td class="mono muted">{b.model_id ?? '—'}</td>
                <td class="tabular-nums muted">{formatInt(b.runs)}</td>
                <td class="tabular-nums">{formatInt(b.failed_runs)}</td>
                <td><span class="badge danger">{formatPercent(b.error_rate)}</span></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  <section class="panel" aria-labelledby="home-unavailable">
    <div class="panel-head">
      <h2 id="home-unavailable" class="section-title">Entradas de catálogo no disponibles</h2>
      <button class="btn ghost small-btn" type="button" onclick={() => ui.switchTo('catalog')}>
        Ir al catálogo
      </button>
    </div>
    {#if catalogError}
      <p class="error-text" role="alert">{catalogError}</p>
    {:else if unavailable.length === 0}
      <p class="muted small">Todas las entradas tienen un binding activo.</p>
    {:else}
      <ul class="plain-list">
        {#each unavailable as entry (entry.id)}
          <li>
            <span class="strong">{entry.display_name}</span>
            <span class="mono muted small">{entry.slug}</span>
            <span class="badge danger">sin binding activo</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
</div>

<section class="panel" aria-labelledby="home-errors">
  <div class="panel-head">
    <h2 id="home-errors" class="section-title">Últimos runs con error</h2>
    <button class="btn ghost small-btn" type="button" onclick={() => ui.switchTo('runs')}>
      Ver runs
    </button>
  </div>
  {#if runsError}
    <p class="error-text" role="alert">{runsError}</p>
  {:else if failedRuns.length === 0}
    <p class="muted small">No hay runs fallidos recientes.</p>
  {:else}
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Usuario</th>
            <th>Modo</th>
            <th>Código</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each failedRuns as run (run.id)}
            <tr>
              <td class="tabular-nums muted">{formatDateTime(run.created_at)}</td>
              <td>{run.user_email ?? '—'}</td>
              <td class="mono muted">{run.mode}</td>
              <td><span class="badge danger">{run.error_code ?? 'error'}</span></td>
              <td>
                <button
                  class="btn ghost small-btn"
                  type="button"
                  onclick={() => ui.openRun(run.id)}
                >
                  Abrir
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  .view-head h1 {
    margin: 0;
  }

  .sub {
    margin: 4px 0 0;
    font-size: 13px;
  }

  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }

  .kpi {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 14px 16px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
    text-align: left;
    font: inherit;
    color: inherit;
  }

  .kpi-button {
    cursor: pointer;
  }

  .kpi-button:hover {
    background: var(--p-hi);
  }

  .kpi-label {
    color: var(--p-mut);
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .kpi-value {
    font-size: 26px;
    font-weight: 700;
  }

  .kpi-value.bad {
    color: var(--sem-critical);
  }

  .small {
    font-size: 13px;
  }

  .columns {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }

  .panel {
    margin-bottom: 16px;
    padding: 16px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
    min-width: 0;
  }

  .columns .panel {
    margin-bottom: 0;
  }

  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }

  .panel-head .section-title {
    margin: 0;
  }

  .small-btn {
    padding: 4px 10px;
    font-size: 13px;
  }

  .plain-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .plain-list li {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
</style>
