<script lang="ts">
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import type { Provider } from '../../lib/types.js';

  interface Props {
    mode: 'create' | 'edit' | 'rotate';
    provider: Provider | null;
    onSaved: () => void;
  }

  let { mode, provider, onSaved }: Props = $props();

  // svelte-ignore state_referenced_locally
  let name = $state(provider?.name ?? '');
  // svelte-ignore state_referenced_locally
  let kind = $state<Provider['kind']>(provider?.kind ?? 'openai_compatible');
  // svelte-ignore state_referenced_locally
  let baseUrl = $state(provider?.base_url ?? '');
  // svelte-ignore state_referenced_locally
  let isEnabled = $state(provider?.is_enabled ?? true);
  // svelte-ignore state_referenced_locally
  let headersText = $state(JSON.stringify(provider?.default_headers ?? {}, null, 2));
  let apiKey = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);

  let isCreate = $derived(mode === 'create');
  let isRotate = $derived(mode === 'rotate');

  function parseHeaders(): Record<string, string> | null {
    const trimmed = headersText.trim() === '' ? '{}' : headersText.trim();
    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        error = 'Los encabezados deben ser un objeto JSON';
        return null;
      }
      const headers: Record<string, string> = {};
      for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof value !== 'string') {
          error = 'Los encabezados deben tener valores de texto';
          return null;
        }
        headers[key] = value;
      }
      return headers;
    } catch {
      error = 'JSON de encabezados inválido';
      return null;
    }
  }

  async function save(event: SubmitEvent) {
    event.preventDefault();
    error = null;

    if (isRotate) {
      if (!apiKey.trim()) {
        error = 'Introduce la nueva clave';
        return;
      }
      busy = true;
      try {
        await api(`/admin/providers/${provider?.id ?? ''}/credentials`, {
          method: 'POST',
          body: { api_key: apiKey.trim() },
        });
        onSaved();
      } catch (e) {
        error = e instanceof Error ? e.message : 'No se pudo rotar la credencial';
      } finally {
        busy = false;
      }
      return;
    }

    const headers = parseHeaders();
    if (headers === null) return;

    if (!name.trim()) {
      error = 'El nombre es obligatorio';
      return;
    }

    busy = true;
    try {
      if (isCreate) {
        await api('/admin/providers', {
          method: 'POST',
          body: {
            name: name.trim(),
            kind,
            base_url: baseUrl.trim() || null,
            is_enabled: isEnabled,
            default_headers: headers,
            initial_api_key: apiKey.trim() || null,
          },
        });
      } else {
        await api(`/admin/providers/${provider?.id ?? ''}`, {
          method: 'PATCH',
          body: {
            name: name.trim(),
            base_url: baseUrl.trim() || null,
            is_enabled: isEnabled,
            default_headers: headers,
          },
        });
      }
      onSaved();
    } catch (e) {
      error = e instanceof Error ? e.message : 'No se pudo guardar el proveedor';
    } finally {
      busy = false;
    }
  }
</script>

<form class="form" onsubmit={save}>
  {#if isRotate}
    <label class="field">
      <span class="field-label">
        Nueva clave API
        {#if provider?.credential_last_four}
          (actual termina en {provider.credential_last_four})
        {/if}
      </span>
      <input
        class="input"
        type="password"
        autocomplete="new-password"
        bind:value={apiKey}
        placeholder="sk-…"
        required
      />
    </label>
    <p class="hint">
      La clave actual quedará desactivada; las conversaciones nuevas usarán la nueva.
    </p>
  {:else}
    <label class="field">
      <span class="field-label">Nombre</span>
      <input class="input" type="text" bind:value={name} placeholder="Mi proveedor" required />
    </label>

    {#if isCreate}
      <label class="field">
        <span class="field-label">Tipo</span>
        <select class="input" bind:value={kind}>
          <option value="vercel_gateway">vercel_gateway</option>
          <option value="deepinfra">deepinfra</option>
          <option value="nvidia_nim">nvidia_nim</option>
          <option value="openai_compatible">openai_compatible</option>
        </select>
      </label>
    {/if}

    <label class="field">
      <span class="field-label">
        {kind === 'openai_compatible' ? 'Base URL' : 'Base URL (opcional)'}
      </span>
      <input
        class="input"
        type="url"
        bind:value={baseUrl}
        placeholder="https://api.example.com/v1"
        required={kind === 'openai_compatible'}
      />
    </label>

    <label class="field">
      <span class="field-label">Encabezados por defecto (JSON)</span>
      <textarea class="input code" rows="4" spellcheck="false" bind:value={headersText}></textarea>
    </label>

    {#if isCreate}
      <label class="field">
        <span class="field-label">Clave API inicial (opcional)</span>
        <input
          class="input"
          type="password"
          autocomplete="new-password"
          bind:value={apiKey}
          placeholder="sk-…"
        />
      </label>
    {/if}

    <div class="switch-row">
      <span>Activo</span>
      <Switch checked={isEnabled} label="Proveedor activo" onchange={(v) => (isEnabled = v)} />
    </div>
  {/if}

  {#if error}
    <p class="error-text" role="alert">{error}</p>
  {/if}

  <div class="actions">
    <button class="btn primary" type="submit" disabled={busy}>
      {busy
        ? 'Guardando…'
        : isRotate
          ? 'Rotar credencial'
          : isCreate
            ? 'Crear proveedor'
            : 'Guardar cambios'}
    </button>
  </div>
</form>

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px;
    resize: vertical;
  }

  .switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .hint {
    margin: 0;
    color: var(--p-mut);
    font-size: 13px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 4px;
  }
</style>
