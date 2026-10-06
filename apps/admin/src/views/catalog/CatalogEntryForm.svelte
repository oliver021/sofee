<script lang="ts">
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import type { CatalogEntry } from '../../lib/types.js';

  interface Props {
    mode: 'create' | 'edit';
    entry: CatalogEntry | null;
    onSaved: () => void;
  }

  let { mode, entry, onSaved }: Props = $props();

  const CATEGORIES = ['general', 'rapido', 'balanceado', 'razonamiento', 'vision', 'codigo'];

  // svelte-ignore state_referenced_locally
  let slug = $state(entry?.slug ?? '');
  // svelte-ignore state_referenced_locally
  let displayName = $state(entry?.display_name ?? '');
  // svelte-ignore state_referenced_locally
  let description = $state(entry?.description ?? '');
  // svelte-ignore state_referenced_locally
  let category = $state(entry?.category ?? CATEGORIES[0]);
  // svelte-ignore state_referenced_locally
  let sortOrder = $state(entry?.sort_order ?? 0);
  // svelte-ignore state_referenced_locally
  let isEnabled = $state(entry?.is_enabled ?? true);
  let error = $state<string | null>(null);
  let busy = $state(false);

  let isCreate = $derived(mode === 'create');

  async function save(event: SubmitEvent) {
    event.preventDefault();
    error = null;

    if (!displayName.trim()) {
      error = 'El nombre es obligatorio';
      return;
    }
    if (isCreate && !/^[a-z0-9][a-z0-9-]*$/.test(slug.trim())) {
      error = 'El slug debe ser minúsculas, números y guiones (p. ej. "fast")';
      return;
    }

    busy = true;
    try {
      if (isCreate) {
        await api('/admin/catalog', {
          method: 'POST',
          body: {
            slug: slug.trim(),
            display_name: displayName.trim(),
            description: description.trim() || null,
            category,
            sort_order: sortOrder,
            is_enabled: isEnabled,
          },
        });
      } else {
        await api(`/admin/catalog/${entry?.id ?? ''}`, {
          method: 'PATCH',
          body: {
            display_name: displayName.trim(),
            description: description.trim() || null,
            category,
            sort_order: sortOrder,
            is_enabled: isEnabled,
          },
        });
      }
      onSaved();
    } catch (e) {
      error = e instanceof Error ? e.message : 'No se pudo guardar la entrada';
    } finally {
      busy = false;
    }
  }
</script>

<form class="form" onsubmit={save}>
  {#if isCreate}
    <label class="field">
      <span class="field-label">Slug</span>
      <input class="input mono" type="text" bind:value={slug} placeholder="fast" required />
      <span class="hint">Identificador estable, no cambia aunque se edite el nombre.</span>
    </label>
  {/if}

  <label class="field">
    <span class="field-label">Nombre</span>
    <input class="input" type="text" bind:value={displayName} placeholder="Rápido" required />
  </label>

  <label class="field">
    <span class="field-label">Descripción (opcional)</span>
    <input
      class="input"
      type="text"
      bind:value={description}
      placeholder="Respuestas veloces para tareas simples"
    />
  </label>

  <label class="field">
    <span class="field-label">Categoría</span>
    <select class="input" bind:value={category}>
      {#each CATEGORIES as c (c)}
        <option value={c}>{c}</option>
      {/each}
    </select>
  </label>

  <label class="field">
    <span class="field-label">Orden</span>
    <input class="input" type="number" bind:value={sortOrder} />
  </label>

  <div class="switch-row">
    <span>Visible para usuarios</span>
    <Switch checked={isEnabled} label="Entrada visible" onchange={(v) => (isEnabled = v)} />
  </div>

  {#if error}
    <p class="error-text" role="alert">{error}</p>
  {/if}

  <div class="actions">
    <button class="btn primary" type="submit" disabled={busy}>
      {busy ? 'Guardando…' : isCreate ? 'Crear entrada' : 'Guardar cambios'}
    </button>
  </div>
</form>

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .hint {
    color: var(--p-mut);
    font-size: 12px;
  }

  .switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 4px;
  }
</style>
