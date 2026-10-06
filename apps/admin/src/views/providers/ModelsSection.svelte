<script lang="ts">
  import { onMount } from 'svelte';
  import { IconRefresh } from '@sofee/icons';
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { Model, ModelSyncResult, Provider } from '../../lib/types.js';

  interface Props {
    provider: Provider;
  }

  let { provider }: Props = $props();

  let models = $state<Model[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let syncing = $state(false);

  async function load() {
    loading = true;
    loadError = null;
    try {
      models = await api<Model[]>(`/admin/providers/${provider.id}/models`);
    } catch (e) {
      loadError = e instanceof Error ? e.message : 'No se pudieron cargar los modelos';
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function toggle(model: Model, isEnabled: boolean) {
    try {
      await api(`/admin/providers/${provider.id}/models/${model.id}`, {
        method: 'PATCH',
        body: { is_enabled: isEnabled },
      });
      model.is_enabled = isEnabled;
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo actualizar el modelo', 'error');
    }
  }

  async function sync() {
    syncing = true;
    try {
      const result: ModelSyncResult = await api(`/admin/providers/${provider.id}/models/sync`, {
        method: 'POST',
      });
      ui.notify(
        `${result.created} nuevos · ${result.already_exists} ya existían · ${result.total} total`,
      );
      await load();
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo sincronizar', 'error');
    } finally {
      syncing = false;
    }
  }
</script>

<section class="models" aria-label="Modelos de {provider.name}">
  <div class="head">
    <h3>Modelos</h3>
    <button class="btn" type="button" onclick={sync} disabled={syncing}>
      <IconRefresh size={15} />
      {syncing ? 'Sincronizando…' : 'Sincronizar'}
    </button>
  </div>

  {#if loading}
    <p class="muted small">Cargando…</p>
  {:else if loadError}
    <p class="error-text" role="alert">{loadError}</p>
  {:else if models.length === 0}
    <p class="muted small">Sin modelos todavía. Usa «Sincronizar» para importarlos.</p>
  {:else}
    <ul class="list">
      {#each models as model (model.id)}
        <li class="row {model.is_enabled ? '' : 'off'}">
          <div class="info">
            <span class="model-id mono">{model.model_id}</span>
            {#if model.display_name !== model.model_id}
              <span class="muted small">{model.display_name}</span>
            {/if}
          </div>
          <Switch
            checked={model.is_enabled}
            label="Habilitar modelo {model.model_id}"
            onchange={(v) => toggle(model, v)}
          />
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .models {
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
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .model-id {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
