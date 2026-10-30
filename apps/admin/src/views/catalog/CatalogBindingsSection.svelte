<script lang="ts">
  import { onMount } from 'svelte';
  import { IconPlus, IconTrash } from '@sofee/icons';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import { formatInt, formatPrice, messageOf, numberOrNull } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type {
    AgentTestOutcome,
    AgentTestResult,
    CatalogBinding,
    CatalogEntry,
    PublicProviderModel,
    ProbeVerdict,
  } from '../../lib/types.js';

  interface Props {
    entry: CatalogEntry;
    onChanged: (entry: CatalogEntry) => void;
  }

  let { entry, onChanged }: Props = $props();

  const VERDICT_LABELS: Record<
    ProbeVerdict,
    { label: string; tone: 'ok' | 'off' | 'danger' | 'warn' }
  > = {
    supports: { label: 'Usa herramientas', tone: 'ok' },
    no_tool_call: { label: 'No llamó a la herramienta', tone: 'danger' },
    rejected: { label: 'Rechazó las herramientas', tone: 'danger' },
    inconclusive: { label: 'Sin conclusión: vuelve a probar', tone: 'warn' },
    skipped: { label: 'Omitido', tone: 'off' },
  };

  let candidates = $state<PublicProviderModel[]>([]);
  let candidatesLoaded = $state(false);
  let picking = $state(false);
  let pickValue = $state('');
  let busy = $state(false);

  let editingId = $state<string | null>(null);
  let capContext = $state<number | null>(null);
  let capInput = $state<number | null>(null);
  let capOutput = $state<number | null>(null);
  let capError = $state<string | null>(null);
  let capBusy = $state(false);

  let confirmProbe = $state(false);
  let probing = $state(false);
  let probeResults = $state<AgentTestResult[] | null>(null);

  let boundIds = $derived(new Set(entry.bindings.map((b) => b.provider_model_id)));
  let available = $derived(candidates.filter((c) => !boundIds.has(c.id)));

  function toolsLabel(value: boolean | null): { label: string; tone: 'ok' | 'off' | 'danger' } {
    if (value === true) return { label: 'sí', tone: 'ok' };
    if (value === false) return { label: 'no', tone: 'danger' };
    return { label: 'sin probar', tone: 'off' };
  }

  async function loadCandidates() {
    try {
      candidates = await api<PublicProviderModel[]>('/providers/models');
    } catch (e) {
      ui.notify(messageOf(e, 'No se pudieron cargar los modelos'), 'error');
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
      ui.notify(messageOf(e, 'No se pudo agregar el binding'), 'error');
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
      ui.notify(messageOf(e, 'No se pudo actualizar el binding'), 'error');
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
      ui.notify(messageOf(e, 'No se pudo reordenar'), 'error');
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
      ui.notify(messageOf(e, 'No se pudo eliminar'), 'error');
    }
  }

  function startEditCapabilities(binding: CatalogBinding) {
    editingId = binding.id;
    capContext = binding.context_window;
    capInput = binding.input_price_per_mtok;
    capOutput = binding.output_price_per_mtok;
    capError = null;
  }

  function cancelEditCapabilities() {
    editingId = null;
    capError = null;
  }

  // Context window and prices are declared by the admin; `supports_tools` is never set by hand
  // here: only the "Probar como agente" check fills it in.
  async function saveCapabilities(binding: CatalogBinding) {
    const context = numberOrNull(capContext);
    const input = numberOrNull(capInput);
    const output = numberOrNull(capOutput);
    if (context !== null && (!Number.isInteger(context) || context < 1)) {
      capError = 'La ventana de contexto debe ser un entero mayor que cero.';
      return;
    }
    if ((input !== null && input < 0) || (output !== null && output < 0)) {
      capError = 'Los precios no pueden ser negativos.';
      return;
    }
    capBusy = true;
    capError = null;
    try {
      await api(
        `/admin/providers/${binding.provider_id}/models/${binding.provider_model_id}/capabilities`,
        {
          method: 'PATCH',
          body: {
            context_window: context,
            input_price_per_mtok: input,
            output_price_per_mtok: output,
          },
        },
      );
      onChanged(await api<CatalogEntry>(`/admin/catalog/${entry.id}`));
      editingId = null;
      ui.notify('Capacidades guardadas');
    } catch (e) {
      capError = messageOf(e, 'No se pudieron guardar las capacidades');
    } finally {
      capBusy = false;
    }
  }

  async function runProbe() {
    confirmProbe = false;
    probing = true;
    probeResults = null;
    try {
      const outcome = await api<AgentTestOutcome>(`/admin/catalog/${entry.id}/agent-test`, {
        method: 'POST',
      });
      probeResults = outcome.results;
      onChanged(outcome.entry);
      ui.notify(
        outcome.agent_ready ? 'Entrada apta para agentes' : 'Todavía no es apta para agentes',
        outcome.agent_ready ? 'ok' : 'error',
      );
    } catch (e) {
      ui.notify(messageOf(e, 'No se pudo probar la entrada'), 'error');
    } finally {
      probing = false;
    }
  }
</script>

<section class="bindings" aria-label="Modelos atados a {entry.display_name}">
  <div class="head">
    <div class="head-title">
      <h3>Modelos ({entry.bindings.length})</h3>
      {#if entry.agent_ready}
        <span class="badge ok">Apto para agentes</span>
      {:else}
        <span class="badge off">No apto para agentes</span>
      {/if}
    </div>
    <div class="head-actions">
      <button
        class="btn"
        type="button"
        onclick={() => (confirmProbe = true)}
        disabled={probing || entry.bindings.length === 0}
      >
        {probing ? 'Probando…' : 'Probar como agente'}
      </button>
      <button class="btn" type="button" onclick={() => (picking = !picking)}>
        <IconPlus size={15} />
        Agregar
      </button>
    </div>
  </div>

  <p class="muted small hint">
    Apta cuando hay un binding disponible y todos los disponibles usan herramientas. Solo la prueba
    "Probar como agente" confirma esa capacidad: consume tokens reales.
  </p>

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
        {@const tools = toolsLabel(binding.supports_tools)}
        <li class="item {binding.is_enabled ? '' : 'off'}">
          <div class="row">
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
          </div>

          <div class="caps">
            <span class="cap">
              Tools <span class="badge {tools.tone}">{tools.label}</span>
            </span>
            <span class="cap tabular-nums">
              Ventana {binding.context_window === null
                ? '—'
                : `${formatInt(binding.context_window)} tok`}
            </span>
            <span class="cap tabular-nums">
              Entrada {formatPrice(binding.input_price_per_mtok)} · salida
              {formatPrice(binding.output_price_per_mtok)} por Mtok
            </span>
            <button
              class="link-btn"
              type="button"
              onclick={() =>
                editingId === binding.id
                  ? cancelEditCapabilities()
                  : startEditCapabilities(binding)}
            >
              {editingId === binding.id ? 'Cerrar' : 'Editar capacidades'}
            </button>
          </div>

          {#if editingId === binding.id}
            <div class="cap-form">
              <label class="field">
                <span class="field-label">Ventana de contexto (tokens)</span>
                <input
                  class="input tabular-nums"
                  type="number"
                  min="1"
                  step="1"
                  bind:value={capContext}
                />
              </label>
              <label class="field">
                <span class="field-label">Precio de entrada (por Mtok)</span>
                <input
                  class="input tabular-nums"
                  type="number"
                  min="0"
                  step="0.0001"
                  bind:value={capInput}
                />
              </label>
              <label class="field">
                <span class="field-label">Precio de salida (por Mtok)</span>
                <input
                  class="input tabular-nums"
                  type="number"
                  min="0"
                  step="0.0001"
                  bind:value={capOutput}
                />
              </label>
              {#if capError}
                <p class="error-text cap-error" role="alert">{capError}</p>
              {/if}
              <div class="cap-actions">
                <button
                  class="btn ghost"
                  type="button"
                  onclick={cancelEditCapabilities}
                  disabled={capBusy}
                >
                  Cancelar
                </button>
                <button
                  class="btn primary"
                  type="button"
                  onclick={() => saveCapabilities(binding)}
                  disabled={capBusy}
                >
                  {capBusy ? 'Guardando…' : 'Guardar capacidades'}
                </button>
              </div>
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  {#if probeResults}
    <div class="results" aria-label="Resultados de la prueba como agente">
      <h4 class="results-title">Resultado de la prueba</h4>
      <ul class="result-list">
        {#each probeResults as result (result.binding_id)}
          {@const verdict = VERDICT_LABELS[result.verdict]}
          <li class="result">
            <div class="result-head">
              <span class="strong">{result.provider_name} · {result.model_id}</span>
              <span class="badge {verdict.tone}">{verdict.label}</span>
              {#if result.latency_ms !== null}
                <span class="muted small tabular-nums">{formatInt(result.latency_ms)} ms</span>
              {/if}
            </div>
            <p class="muted small">{result.message}</p>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</section>

<ConfirmDialog
  open={confirmProbe}
  title="Probar como agente"
  confirmLabel="Probar"
  busy={probing}
  onconfirm={runProbe}
  oncancel={() => (confirmProbe = false)}
>
  Se hace una llamada real con una herramienta de prueba a cada binding disponible. Consume tokens y
  actualiza si cada modelo usa herramientas.
</ConfirmDialog>

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
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }

  .head-title,
  .head-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .head h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }

  .hint {
    margin: 0 0 12px;
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

  .item {
    padding: 10px 12px;
    border-bottom: 1px solid var(--p-line);
  }

  .item:last-child {
    border-bottom: none;
  }

  .item.off {
    opacity: 0.55;
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
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

  .row-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .row-actions .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--p-mut);
    cursor: pointer;
  }

  .row-actions .icon-btn:hover:not(:disabled) {
    background: var(--p-hi);
    color: var(--p-ink);
  }

  .row-actions .icon-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .caps {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px 14px;
    margin-top: 8px;
    font-size: 12.5px;
    color: var(--p-mut);
  }

  .cap {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .link-btn {
    padding: 0;
    border: none;
    background: none;
    color: var(--p-acc);
    font: inherit;
    font-size: 12.5px;
    cursor: pointer;
  }

  .link-btn:hover {
    text-decoration: underline;
  }

  .cap-form {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 10px;
    margin-top: 10px;
    padding: 12px;
    border: 1px solid var(--p-line);
    border-radius: 10px;
    background: var(--p-surf-2);
  }

  .cap-error {
    grid-column: 1 / -1;
    margin: 0;
  }

  .cap-actions {
    grid-column: 1 / -1;
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .results {
    margin-top: 16px;
  }

  .results-title {
    margin: 0 0 8px;
    font-size: 13px;
    font-weight: 600;
  }

  .result-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .result {
    padding: 10px 12px;
    border: 1px solid var(--p-line);
    border-radius: 10px;
  }

  .result-head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .result p {
    margin: 4px 0 0;
    overflow-wrap: anywhere;
  }
</style>
