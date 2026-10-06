<script lang="ts">
  import { onMount } from 'svelte';
  import { IconPlus, IconTrash } from '@sofee/icons';
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { CatalogEntry, PublicProviderModel } from '../../lib/types.js';

  interface Props {
    entry: CatalogEntry;
    onChanged: (entry: CatalogEntry) => void;
  }

  let { entry, onChanged }: Props = $props();

  let candidates = $state<PublicProviderModel[]>([]);
  let candidatesLoaded = $state(false);
  let picking = $state(false);
  let pickValue = $state('');
  let busy = $state(false);

  let boundIds = $derived(new Set(entry.bindings.map((b) => b.provider_model_id)));
  let available = $derived(candidates.filter((c) => !boundIds.has(c.id)));

  async function loadCandidates() {
    try {
      candidates = await api<PublicProviderModel[]>('/providers/models');
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudieron cargar los modelos', 'error');
    } finally {
      candidatesLoaded = true;
    }
  }

  onMount(loadCandidates);

  async function addBinding() {
    if (!pickValue) return;
    busy = true;
    try {
      const updated = await api<CatalogEntry>(`/admin/catalog/${entry.id}/bindings`, {
        method: 'POST',
        body: { provider_model_id: pickValue },
      });
      onChanged(updated);
      pickValue = '';
      picking = false;
      ui.notify('Modelo agregado al catálogo');
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo agregar el binding', 'error');
    } finally {
      busy = false;
    }
  }

  async function toggleBinding(bindingId: string, isEnabled: boolean) {
    try {
      const updated = await api<CatalogEntry>(`/admin/catalog/${entry.id}/bindings/${bindingId}`, {
        method: 'PATCH',
        body: { is_enabled: isEnabled },
      });
      onChanged(updated);
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo actualizar el binding', 'error');
    }
  }

  async function move(bindingId: string, direction: -1 | 1) {
    const index = entry.bindings.findIndex((b) => b.id === bindingId);
    const swapWith = entry.bindings[index + direction];
    const current = entry.bindings[index];
    if (!swapWith || !current) return;
    try {
      await api(`/admin/catalog/${entry.id}/bindings/${current.id}`, {
        method: 'PATCH',
        body: { priority: swapWith.priority },
      });
      const updated = await api<CatalogEntry>(
        `/admin/catalog/${entry.id}/bindings/${swapWith.id}`,
        { method: 'PATCH', body: { priority: current.priority } },
      );
      onChanged(updated);
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo reordenar', 'error');
    }
  }

  async function remove(bindingId: string) {
    try {
      const updated = await api<CatalogEntry>(`/admin/catalog/${entry.id}/bindings/${bindingId}`, {
        method: 'DELETE',
      });
      onChanged(updated);
      ui.notify('Binding eliminado');
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo eliminar', 'error');
    }
  }
</script>

<section class="bindings" aria-label="Modelos atados a {entry.display_name}">
  <div class="head">
    <h3>Modelos ({entry.bindings.length})</h3>
    <button class="btn" type="button" onclick={() => (picking = !picking)}>
      <IconPlus size={15} />
      Agregar
    </button>
  </div>

  {#if picking}
    <div class="picker">
      {#if !candidatesLoaded}
        <p class="muted small">Cargando modelos disponibles…</p>
      {:else if available.length === 0}
        <p class="muted small">No hay más modelos habilitados para atar.</p>
      {:else}
        <select class="input" bind:value={pickValue}>
          <option value="">Elegir modelo…</option>
          {#each available as c (c.id)}
            <option value={c.id}>{c.provider_name} · {c.display_name}</option>
          {/each}
        </select>
        <button
          class="btn primary"
          type="button"
          onclick={addBinding}
          disabled={!pickValue || busy}
        >
          Atar
        </button>
      {/if}
    </div>
  {/if}

  {#if entry.bindings.length === 0}
    <p class="muted small">Sin modelos todavía. La entrada no está disponible para usuarios.</p>
  {:else}
    <ul class="list">
      {#each entry.bindings as binding, i (binding.id)}
        <li class="row {binding.is_enabled ? '' : 'off'}">
          <div class="info">
            <span class="badge {i === 0 ? 'ok' : 'off'}">
              {i === 0 ? 'Primario' : `Fallback #${i}`}
            </span>
            <span class="model-name">{binding.provider_name} · {binding.model_display_name}</span>
            <span class="mono muted small">{binding.model_id}</span>
          </div>
          <div class="row-actions">
            <button
              class="icon-btn"
              type="button"
              disabled={i === 0}
              onclick={() => move(binding.id, -1)}
              aria-label="Subir prioridad"
            >
              ↑
            </button>
            <button
              class="icon-btn"
              type="button"
              disabled={i === entry.bindings.length - 1}
              onclick={() => move(binding.id, 1)}
              aria-label="Bajar prioridad"
            >
              ↓
            </button>
            <Switch
              checked={binding.is_enabled}
              label="Habilitar binding {binding.model_id}"
              onchange={(v) => toggleBinding(binding.id, v)}
            />
            <button
              class="icon-btn"
              type="button"
              onclick={() => remove(binding.id)}
              aria-label="Quitar binding"
            >
              <IconTrash size={16} />
            </button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .bindings {
    margin-top: 24px;
    padding-top: 20px;
    border-top: 1px solid var(--p-line);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .head h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }

  .small {
    font-size: 13px;
  }

  .picker {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }

  .picker .input {
    flex: 1;
  }

  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    border: 1px solid var(--p-line);
    border-radius: 10px;
    overflow: hidden;
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--p-line);
  }

  .row:last-child {
    border-bottom: none;
  }

  .row.off {
    opacity: 0.55;
  }

  .info {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }

  .model-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
