<script lang="ts">
  import { onMount } from 'svelte';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import { api } from '../../lib/api.js';
  import { formatDateTime, messageOf } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { TavilyStatus, TavilyTestResult } from '../../lib/types.js';

  let status = $state<TavilyStatus | null>(null);
  let loading = $state(true);
  let loadError = $state<string | null>(null);

  let apiKey = $state('');
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let testing = $state(false);
  let testResult = $state<TavilyTestResult | null>(null);
  let confirmTest = $state(false);

  async function load() {
    loading = true;
    loadError = null;
    try {
      status = await api<TavilyStatus>('/admin/integrations/tavily');
    } catch (e) {
      loadError = messageOf(e, 'No se pudo cargar la integración');
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function save(event: SubmitEvent) {
    event.preventDefault();
    const key = apiKey.trim();
    if (!key) {
      saveError = 'Introduce la clave de Tavily.';
      return;
    }
    saving = true;
    saveError = null;
    try {
      status = await api<TavilyStatus>('/admin/integrations/tavily', {
        method: 'PUT',
        body: { api_key: key },
      });
      apiKey = '';
      testResult = null;
      ui.notify('Clave de Tavily guardada');
    } catch (e) {
      saveError = messageOf(e, 'No se pudo guardar la clave');
    } finally {
      saving = false;
    }
  }

  async function runTest() {
    confirmTest = false;
    testing = true;
    testResult = null;
    try {
      testResult = await api<TavilyTestResult>('/admin/integrations/tavily/test', {
        method: 'POST',
      });
    } catch (e) {
      testResult = { ok: false, message: messageOf(e, 'No se pudo probar la conexión') };
    } finally {
      testing = false;
    }
  }
</script>

<div class="view-head">
  <div>
    <h1>Integraciones</h1>
    <p class="muted intro">Servicios externos que usa el agente.</p>
  </div>
</div>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if status}
  <section class="card" aria-labelledby="tavily-title">
    <div class="card-head">
      <div>
        <h2 id="tavily-title" class="title">Tavily · búsqueda web</h2>
        <p class="muted small">
          Permite al agente buscar en la web con citas. Sin clave activa, la herramienta no se
          ofrece al agente.
        </p>
      </div>
      {#if status.configured}
        <span class="badge ok">Configurada</span>
      {:else}
        <span class="badge off">Sin clave</span>
      {/if}
    </div>

    <dl class="facts">
      <dt>Clave</dt>
      <dd class="mono">
        {#if status.configured && status.last_four}
          ••••{status.last_four}
        {:else}
          —
        {/if}
      </dd>
      <dt>Última actualización</dt>
      <dd>{formatDateTime(status.updated_at)}</dd>
    </dl>

    <form class="form" onsubmit={save}>
      <label class="field">
        <span class="field-label">{status.configured ? 'Reemplazar clave' : 'Clave de API'}</span>
        <input
          class="input mono"
          type="password"
          autocomplete="new-password"
          spellcheck="false"
          placeholder="tvly-…"
          bind:value={apiKey}
        />
        <span class="hint">
          Se guarda cifrada. La clave anterior queda desactivada y se conserva para auditoría.
        </span>
      </label>
      {#if saveError}
        <p class="error-text" role="alert">{saveError}</p>
      {/if}
      <div class="actions">
        <button
          class="btn"
          type="button"
          onclick={() => (confirmTest = true)}
          disabled={!status.configured || testing}
        >
          {testing ? 'Probando…' : 'Probar conexión'}
        </button>
        <button class="btn primary" type="submit" disabled={saving || apiKey.trim() === ''}>
          {saving ? 'Guardando…' : 'Guardar clave'}
        </button>
      </div>
    </form>

    {#if testResult}
      <p class="result {testResult.ok ? 'ok' : 'fail'}" role="status">
        {testResult.ok ? 'Correcto' : 'Falló'} · {testResult.message}
      </p>
    {/if}
  </section>
{/if}

<ConfirmDialog
  open={confirmTest}
  title="Probar conexión con Tavily"
  confirmLabel="Probar"
  busy={testing}
  onconfirm={runTest}
  oncancel={() => (confirmTest = false)}
>
  Hace una búsqueda real y consume cuota de Tavily. El resultado queda en la auditoría.
</ConfirmDialog>

<style>
  .view-head h1 {
    margin: 0;
  }

  .intro {
    margin: 4px 0 0;
    font-size: 13.5px;
  }

  .card {
    max-width: 680px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px;
    border: 1px solid var(--p-line);
    border-radius: 14px;
    background: var(--p-surf);
  }

  .card-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
  }

  .title {
    margin: 0 0 4px;
    font-size: 16px;
    font-weight: 600;
  }

  .card-head p {
    margin: 0;
  }

  .small {
    font-size: 13px;
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
  }

  .form {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .hint {
    color: var(--p-mut);
    font-size: 12px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .result {
    margin: 0;
    padding: 10px 12px;
    border-radius: 10px;
    font-size: 13.5px;
    border: 1px solid var(--p-line);
  }

  .result.ok {
    border-color: var(--sem-success);
  }

  .result.fail {
    border-color: var(--sem-critical);
    color: var(--sem-critical);
  }
</style>
