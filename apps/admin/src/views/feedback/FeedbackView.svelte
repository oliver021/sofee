<script lang="ts">
  import { onMount } from 'svelte';
  import Drawer from '../../components/Drawer.svelte';
  import { api } from '../../lib/api.js';
  import { clip, formatDateTime, messageOf } from '../../lib/format.js';
  import { toQuery } from '../../lib/query.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { AdminFeedback, AdminFeedbackPage } from '../../lib/types.js';

  type ReviewFilter = 'pending' | 'reviewed' | 'all';
  type ValueFilter = 'all' | 'bad' | 'good';

  const PAGE_SIZE = 50;

  const VALUE_OPTIONS: { id: ValueFilter; label: string }[] = [
    { id: 'bad', label: 'Pulgar abajo' },
    { id: 'good', label: 'Pulgar arriba' },
    { id: 'all', label: 'Todas' },
  ];

  const REVIEW_OPTIONS: { id: ReviewFilter; label: string }[] = [
    { id: 'pending', label: 'Sin revisar' },
    { id: 'reviewed', label: 'Revisadas' },
    { id: 'all', label: 'Todas' },
  ];

  let reviewFilter = $state<ReviewFilter>('pending');
  let valueFilter = $state<ValueFilter>('bad');
  let items = $state<AdminFeedback[]>([]);
  let nextCursor = $state<string | null>(null);
  let loading = $state(true);
  let loadingMore = $state(false);
  let loadError = $state<string | null>(null);
  let busyId = $state<string | null>(null);
  let selected = $state<AdminFeedback | null>(null);

  function buildQuery(cursor: string | null): string {
    return toQuery({
      limit: PAGE_SIZE,
      value: valueFilter === 'all' ? null : valueFilter,
      reviewed: reviewFilter === 'all' ? null : reviewFilter === 'reviewed',
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
      const page = await api<AdminFeedbackPage>(
        `/admin/feedback${buildQuery(reset ? null : nextCursor)}`,
      );
      items = reset ? page.items : [...items, ...page.items];
      nextCursor = page.next_cursor;
    } catch (e) {
      loadError = messageOf(e, 'No se pudieron cargar las valoraciones');
    } finally {
      loading = false;
      loadingMore = false;
    }
  }

  onMount(() => {
    void load(true);
  });

  async function setReviewed(item: AdminFeedback, reviewed: boolean) {
    busyId = item.id;
    try {
      const updated = await api<AdminFeedback>(`/admin/feedback/${item.id}`, {
        method: 'PATCH',
        body: { reviewed },
      });
      ui.notify(reviewed ? 'Marcada como revisada' : 'Vuelve a la bandeja');
      items = items.map((entry) => (entry.id === updated.id ? updated : entry));
      if (selected?.id === updated.id) selected = updated;
      // The filter may now hide this row; reload so the inbox matches the filter.
      if (reviewFilter !== 'all') await load(true);
    } catch (e) {
      ui.notify(messageOf(e, 'No se pudo actualizar la valoración'), 'error');
    } finally {
      busyId = null;
    }
  }

  function openRun(runId: string) {
    selected = null;
    ui.openRun(runId);
  }
</script>

<div class="view-head">
  <div>
    <h1>Valoraciones</h1>
    <p class="muted intro">
      Respuestas que los usuarios valoraron. Revisa los pulgares abajo con su contexto.
    </p>
  </div>
</div>

<div class="filters" role="group" aria-label="Filtros de valoraciones">
  <div class="segmented" role="group" aria-label="Valoración">
    {#each VALUE_OPTIONS as option (option.id)}
      <button
        type="button"
        class="seg {valueFilter === option.id ? 'active' : ''}"
        aria-pressed={valueFilter === option.id}
        onclick={() => {
          valueFilter = option.id;
          void load(true);
        }}
      >
        {option.label}
      </button>
    {/each}
  </div>
  <div class="segmented" role="group" aria-label="Estado de revisión">
    {#each REVIEW_OPTIONS as option (option.id)}
      <button
        type="button"
        class="seg {reviewFilter === option.id ? 'active' : ''}"
        aria-pressed={reviewFilter === option.id}
        onclick={() => {
          reviewFilter = option.id;
          void load(true);
        }}
      >
        {option.label}
      </button>
    {/each}
  </div>
</div>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if items.length === 0}
  <div class="empty">
    <p>No hay valoraciones con estos filtros.</p>
  </div>
{:else}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Valoración</th>
          <th>Motivo</th>
          <th>Pregunta</th>
          <th>Respuesta</th>
          <th>Usuario</th>
          <th>Estado</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each items as item (item.id)}
          <tr>
            <td class="tabular-nums muted">{formatDateTime(item.created_at)}</td>
            <td>
              {#if item.value === 'bad'}
                <span class="badge danger">pulgar abajo</span>
              {:else}
                <span class="badge ok">pulgar arriba</span>
              {/if}
            </td>
            <td class="wrap muted">{item.reason ?? '—'}</td>
            <td class="wrap">{clip(item.question ?? '—', 140)}</td>
            <td class="wrap muted">{clip(item.answer, 140)}</td>
            <td class="muted">{item.user_email ?? '—'}</td>
            <td>
              {#if item.reviewed}
                <span class="badge off">revisada</span>
              {:else}
                <span class="badge warn">sin revisar</span>
              {/if}
            </td>
            <td>
              <div class="row-actions">
                <button class="btn ghost small-btn" type="button" onclick={() => (selected = item)}>
                  Ver
                </button>
                <button
                  class="btn small-btn"
                  type="button"
                  disabled={busyId === item.id}
                  onclick={() => setReviewed(item, !item.reviewed)}
                >
                  {item.reviewed ? 'Reabrir' : 'Marcar revisada'}
                </button>
              </div>
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

<Drawer open={selected !== null} title="Valoración" onclose={() => (selected = null)}>
  {#if selected}
    {@const item = selected}
    <div class="detail">
      <p class="meta">
        {formatDateTime(item.created_at)} · {item.user_email ?? '—'} ·
        {item.value === 'bad' ? 'pulgar abajo' : 'pulgar arriba'}
      </p>

      <section class="block">
        <h3 class="section-title">Motivo y comentario</h3>
        <p class="prose">{item.reason ?? 'Sin motivo'}</p>
        {#if item.comment}
          <p class="prose">{item.comment}</p>
        {/if}
      </section>

      <section class="block">
        <h3 class="section-title">Pregunta</h3>
        <p class="prose">{item.question ?? '—'}</p>
      </section>

      <section class="block">
        <h3 class="section-title">Respuesta</h3>
        <p class="prose">{item.answer}</p>
      </section>

      <div class="actions">
        {#if item.run_id}
          <button class="btn" type="button" onclick={() => openRun(item.run_id ?? '')}>
            Ver el run
          </button>
        {:else}
          <span class="muted small">Sin run asociado.</span>
        {/if}
        <button
          class="btn primary"
          type="button"
          disabled={busyId === item.id}
          onclick={() => setReviewed(item, !item.reviewed)}
        >
          {item.reviewed ? 'Reabrir' : 'Marcar revisada'}
        </button>
      </div>
    </div>
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
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 16px;
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

  .row-actions {
    display: inline-flex;
    gap: 6px;
  }

  .small-btn {
    padding: 4px 10px;
    font-size: 13px;
  }

  .pager {
    display: flex;
    justify-content: center;
    margin-top: 16px;
  }

  .detail {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .meta {
    margin: 0;
    color: var(--p-mut);
    font-size: 13px;
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
  }

  .block .section-title {
    margin: 0;
  }

  .prose {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    font-size: 14px;
    line-height: 1.6;
  }

  .actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
  }

  .small {
    font-size: 13px;
  }
</style>
