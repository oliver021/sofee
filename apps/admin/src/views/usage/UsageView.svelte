<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../../lib/api.js';
  import { formatCost, formatInt, formatMs, formatPercent, messageOf } from '../../lib/format.js';
  import type { UsageDayRow, UsageReport } from '../../lib/types.js';

  const RANGES = [
    { days: 1, label: 'Hoy' },
    { days: 7, label: '7 días' },
    { days: 30, label: '30 días' },
    { days: 90, label: '90 días' },
  ];

  // A binding above this error rate is flagged in the table.
  const ERROR_RATE_WARN = 0.1;

  interface DayTotal {
    day: string;
    runs: number;
    input: number;
    output: number;
    cost: number;
  }

  let days = $state(7);
  let report = $state<UsageReport | null>(null);
  let loading = $state(true);
  let loadError = $state<string | null>(null);

  // Per-model rows are split by model; the daily table wants one row per day.
  let dailyTotals = $derived(aggregateDaily(report?.daily ?? []));
  let maxDailyRuns = $derived(Math.max(1, ...dailyTotals.map((row) => row.runs)));
  let totalRuns = $derived(report?.totals.runs ?? 0);

  function aggregateDaily(rows: UsageDayRow[]): DayTotal[] {
    const byDay: Record<string, DayTotal> = {};
    for (const row of rows) {
      const current = byDay[row.day] ?? { day: row.day, runs: 0, input: 0, output: 0, cost: 0 };
      current.runs += row.runs;
      current.input += row.input_tokens;
      current.output += row.output_tokens;
      current.cost += row.cost_estimate;
      byDay[row.day] = current;
    }
    return Object.values(byDay).sort((a, b) => a.day.localeCompare(b.day));
  }

  function formatDay(day: string): string {
    return new Date(`${day}T00:00:00Z`).toLocaleDateString('es', {
      day: '2-digit',
      month: 'short',
      timeZone: 'UTC',
    });
  }

  function share(part: number, whole: number): number {
    return whole === 0 ? 0 : Math.round((part / whole) * 100);
  }

  async function load() {
    loading = true;
    loadError = null;
    try {
      report = await api<UsageReport>(`/admin/usage?days=${days}`);
    } catch (e) {
      loadError = messageOf(e, 'No se pudo cargar el uso');
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function selectRange(value: number) {
    days = value;
    void load();
  }
</script>

<div class="view-head">
  <div>
    <h1>Uso</h1>
    <p class="muted intro">Runs, tokens, coste y latencia del agente. Los días son UTC.</p>
  </div>
  <div class="segmented" role="group" aria-label="Periodo">
    {#each RANGES as range (range.days)}
      <button
        type="button"
        class="seg {days === range.days ? 'active' : ''}"
        aria-pressed={days === range.days}
        onclick={() => selectRange(range.days)}
      >
        {range.label}
      </button>
    {/each}
  </div>
</div>

{#if loading && !report}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if report}
  <div class="kpis">
    <div class="kpi">
      <span class="kpi-label">Runs</span>
      <span class="kpi-value tabular-nums">{formatInt(report.totals.runs)}</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">Tokens de entrada</span>
      <span class="kpi-value tabular-nums">{formatInt(report.totals.input_tokens)}</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">Tokens de salida</span>
      <span class="kpi-value tabular-nums">{formatInt(report.totals.output_tokens)}</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">Coste estimado</span>
      <span class="kpi-value tabular-nums">{formatCost(report.totals.cost_estimate)}</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">Tasa de error</span>
      <span
        class="kpi-value tabular-nums {(report.totals.error_rate ?? 0) >= ERROR_RATE_WARN
          ? 'bad'
          : ''}"
      >
        {formatPercent(report.totals.error_rate)}
      </span>
      <span class="muted small">{formatInt(report.totals.failed_runs)} fallidos</span>
    </div>
    <div class="kpi">
      <span class="kpi-label">Citas alucinadas</span>
      <span class="kpi-value tabular-nums">{formatInt(report.totals.hallucinated_citations)}</span>
    </div>
  </div>

  <div class="latency">
    <span class="muted small">Duración p50 / p95</span>
    <span class="tabular-nums strong">
      {formatMs(report.latency.duration_p50_ms)} / {formatMs(report.latency.duration_p95_ms)}
    </span>
    <span class="muted small">TTFT p50 / p95</span>
    <span class="tabular-nums strong">
      {formatMs(report.latency.ttft_p50_ms)} / {formatMs(report.latency.ttft_p95_ms)}
    </span>
  </div>

  <section class="section" aria-labelledby="usage-daily">
    <h2 id="usage-daily" class="section-title">Por día</h2>
    {#if dailyTotals.length === 0}
      <p class="muted small">No hay runs en este periodo.</p>
    {:else}
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Día</th>
              <th>Runs</th>
              <th>Entrada</th>
              <th>Salida</th>
              <th>Coste</th>
            </tr>
          </thead>
          <tbody>
            {#each dailyTotals as row (row.day)}
              <tr>
                <td class="tabular-nums">{formatDay(row.day)}</td>
                <td>
                  <div class="bar-cell">
                    <span class="bar" aria-hidden="true">
                      <span class="fill" style:width="{(row.runs / maxDailyRuns) * 100}%"></span>
                    </span>
                    <span class="tabular-nums">{formatInt(row.runs)}</span>
                  </div>
                </td>
                <td class="tabular-nums muted">{formatInt(row.input)}</td>
                <td class="tabular-nums muted">{formatInt(row.output)}</td>
                <td class="tabular-nums muted">{formatCost(row.cost)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  <section class="section" aria-labelledby="usage-models">
    <h2 id="usage-models" class="section-title">Por modelo</h2>
    {#if report.by_model.length === 0}
      <p class="muted small">Sin datos por modelo.</p>
    {:else}
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Modelo</th>
              <th>Runs</th>
              <th>Entrada</th>
              <th>Salida</th>
              <th>Coste</th>
            </tr>
          </thead>
          <tbody>
            {#each report.by_model as row, index (index)}
              <tr>
                <td>
                  <span class="strong">{row.catalog_slug ?? '—'}</span>
                  <span class="mono muted small">{row.model_label ?? ''}</span>
                </td>
                <td>
                  <div class="bar-cell">
                    <span class="bar" aria-hidden="true">
                      <span class="fill" style:width="{share(row.runs, totalRuns)}%"></span>
                    </span>
                    <span class="tabular-nums">
                      {formatInt(row.runs)}
                      <span class="muted small">({share(row.runs, totalRuns)} %)</span>
                    </span>
                  </div>
                </td>
                <td class="tabular-nums muted">{formatInt(row.input_tokens)}</td>
                <td class="tabular-nums muted">{formatInt(row.output_tokens)}</td>
                <td class="tabular-nums muted">{formatCost(row.cost_estimate)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>

  <section class="section" aria-labelledby="usage-bindings">
    <h2 id="usage-bindings" class="section-title">Por binding (proveedor y modelo)</h2>
    {#if report.bindings.length === 0}
      <p class="muted small">Sin runs con binding en este periodo.</p>
    {:else}
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Modelo</th>
              <th>Runs</th>
              <th>Fallos</th>
              <th>Tasa de error</th>
              <th>Duración p50 / p95</th>
              <th>TTFT p50</th>
            </tr>
          </thead>
          <tbody>
            {#each report.bindings as row, index (index)}
              <tr>
                <td class="strong">{row.provider_name ?? '—'}</td>
                <td class="mono muted">{row.model_id ?? '—'}</td>
                <td class="tabular-nums">{formatInt(row.runs)}</td>
                <td class="tabular-nums">{formatInt(row.failed_runs)}</td>
                <td>
                  {#if row.error_rate !== null && row.error_rate >= ERROR_RATE_WARN}
                    <span class="badge danger">{formatPercent(row.error_rate)}</span>
                  {:else}
                    <span class="tabular-nums muted">{formatPercent(row.error_rate)}</span>
                  {/if}
                </td>
                <td class="tabular-nums muted">
                  {formatMs(row.latency.duration_p50_ms)} / {formatMs(row.latency.duration_p95_ms)}
                </td>
                <td class="tabular-nums muted">{formatMs(row.latency.ttft_p50_ms)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
{/if}

<style>
  .view-head {
    flex-wrap: wrap;
  }

  .view-head h1 {
    margin: 0;
  }

  .intro {
    margin: 4px 0 0;
    font-size: 13.5px;
  }

  .segmented {
    display: inline-flex;
    padding: 3px;
    border: 1px solid var(--p-line);
    border-radius: 10px;
    background: var(--p-surf-2);
  }

  .seg {
    padding: 5px 12px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--p-mut);
    font: inherit;
    font-size: 13.5px;
    cursor: pointer;
  }

  .seg.active {
    background: var(--p-hi);
    color: var(--p-ink);
    font-weight: 600;
  }

  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }

  .kpi {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 14px 16px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
  }

  .kpi-label {
    color: var(--p-mut);
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .kpi-value {
    font-size: 22px;
    font-weight: 700;
  }

  .kpi-value.bad {
    color: var(--sem-critical);
  }

  .latency {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 14px;
    margin-bottom: 24px;
    font-size: 13.5px;
  }

  .section {
    margin-bottom: 24px;
  }

  .section-title {
    margin: 0 0 10px;
    font-size: 14px;
    font-weight: 600;
  }

  .small {
    font-size: 12.5px;
  }

  .bar-cell {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 180px;
  }

  .bar {
    flex: 1;
    height: 8px;
    max-width: 220px;
    border-radius: 999px;
    background: var(--p-surf-2);
    overflow: hidden;
  }

  .fill {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--p-acc);
  }
</style>
