<script lang="ts">
  import { onMount } from 'svelte';
  import { IconEdit, IconPlus, IconTrash } from '@sofee/icons';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import Drawer from '../../components/Drawer.svelte';
  import { api } from '../../lib/api.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { CatalogEntry } from '../../lib/types.js';
  import CatalogBindingsSection from './CatalogBindingsSection.svelte';
  import CatalogEntryForm from './CatalogEntryForm.svelte';

  type DrawerState = {
    open: boolean;
    mode: 'create' | 'edit';
    entry: CatalogEntry | null;
  };

  let entries = $state<CatalogEntry[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let drawer = $state<DrawerState>({ open: false, mode: 'create', entry: null });
  let deleting = $state<CatalogEntry | null>(null);
  let deleteBusy = $state(false);

  let drawerTitle = $derived(drawer.mode === 'create' ? 'Nueva entrada' : 'Editar entrada');

  async function load() {
    loading = true;
    loadError = null;
    try {
      entries = await api<CatalogEntry[]>('/admin/catalog');
    } catch (e) {
      loadError = e instanceof Error ? e.message : 'No se pudo cargar el catálogo';
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function openCreate() {
    drawer = { open: true, mode: 'create', entry: null };
  }

  function openEdit(entry: CatalogEntry) {
    drawer = { open: true, mode: 'edit', entry };
  }

  function closeDrawer() {
    drawer = { open: false, mode: 'create', entry: null };
  }

  async function handleSaved() {
    closeDrawer();
    await load();
    ui.notify('Entrada guardada');
  }

  function handleBindingsChanged(updated: CatalogEntry) {
    drawer = { ...drawer, entry: updated };
    entries = entries.map((e) => (e.id === updated.id ? updated : e));
  }

  async function confirmDelete() {
    if (!deleting) return;
    deleteBusy = true;
    try {
      await api(`/admin/catalog/${deleting.id}`, { method: 'DELETE' });
      ui.notify('Entrada eliminada');
      await load();
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo eliminar', 'error');
    } finally {
      deleteBusy = false;
      deleting = null;
    }
  }
</script>

<div class="view-head">
  <h1>Catálogo</h1>
  <button class="btn primary" type="button" onclick={openCreate}>
    <IconPlus size={16} />
    Nueva entrada
  </button>
</div>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if entries.length === 0}
  <div class="empty">
    <p>Todavía no hay entradas en el catálogo.</p>
    <button class="btn" type="button" onclick={openCreate}>Crear la primera</button>
  </div>
{:else}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Nombre</th>
          <th>Categoría</th>
          <th>Visible</th>
          <th>Disponible</th>
          <th>Modelos</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        {#each entries as e (e.id)}
          <tr>
            <td class="strong">{e.display_name}</td>
            <td class="mono muted">{e.category}</td>
            <td>
              {#if e.is_enabled}
                <span class="badge ok">visible</span>
              {:else}
                <span class="badge off">oculta</span>
              {/if}
            </td>
            <td>
              {#if e.is_available}
                <span class="badge ok">disponible</span>
              {:else}
                <span class="badge danger">sin binding activo</span>
              {/if}
            </td>
            <td class="muted">{e.bindings.length}</td>
            <td>
              <div class="row-actions">
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => openEdit(e)}
                  aria-label="Editar"
                >
                  <IconEdit size={16} />
                </button>
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => (deleting = e)}
                  aria-label="Eliminar"
                >
                  <IconTrash size={16} />
                </button>
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<Drawer open={drawer.open} title={drawerTitle} onclose={closeDrawer}>
  {#if drawer.open}
    <CatalogEntryForm mode={drawer.mode} entry={drawer.entry} onSaved={handleSaved} />
    {#if drawer.mode === 'edit' && drawer.entry}
      <CatalogBindingsSection entry={drawer.entry} onChanged={handleBindingsChanged} />
    {/if}
  {/if}
</Drawer>

<ConfirmDialog
  open={deleting !== null}
  title="Eliminar entrada"
  confirmLabel="Eliminar"
  danger
  busy={deleteBusy}
  onconfirm={confirmDelete}
  oncancel={() => (deleting = null)}
>
  ¿Eliminar la entrada "{deleting?.display_name}"? Esta acción no se puede deshacer.
</ConfirmDialog>
