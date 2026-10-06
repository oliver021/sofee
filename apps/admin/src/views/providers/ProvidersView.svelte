<script lang="ts">
  import { onMount } from 'svelte';
  import { IconEdit, IconGlobe, IconPlus, IconRefresh, IconTrash } from '@sofee/icons';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import Drawer from '../../components/Drawer.svelte';
  import { api } from '../../lib/api.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { ConnectionTestResult, Provider } from '../../lib/types.js';
  import ModelsSection from './ModelsSection.svelte';
  import ProviderForm from './ProviderForm.svelte';

  type DrawerState = {
    open: boolean;
    mode: 'create' | 'edit' | 'rotate';
    provider: Provider | null;
  };

  let providers = $state<Provider[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let drawer = $state<DrawerState>({ open: false, mode: 'create', provider: null });
  let deleting = $state<Provider | null>(null);
  let deleteBusy = $state(false);
  let testing = $state<string | null>(null);

  let drawerTitle = $derived(
    drawer.mode === 'create'
      ? 'Nuevo proveedor'
      : drawer.mode === 'edit'
        ? 'Editar proveedor'
        : 'Rotar credencial',
  );

  async function load() {
    loading = true;
    loadError = null;
    try {
      providers = await api<Provider[]>('/admin/providers');
    } catch (e) {
      loadError = e instanceof Error ? e.message : 'No se pudieron cargar los proveedores';
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function openCreate() {
    drawer = { open: true, mode: 'create', provider: null };
  }

  function openEdit(provider: Provider) {
    drawer = { open: true, mode: 'edit', provider };
  }

  function openRotate(provider: Provider) {
    drawer = { open: true, mode: 'rotate', provider };
  }

  function closeDrawer() {
    drawer = { open: false, mode: 'create', provider: null };
  }

  async function handleSaved() {
    closeDrawer();
    await load();
    ui.notify('Proveedor guardado');
  }

  async function testConnection(provider: Provider) {
    testing = provider.id;
    try {
      const result = await api<ConnectionTestResult>(`/admin/providers/${provider.id}/test`, {
        method: 'POST',
      });
      if (result.ok) {
        ui.notify(result.message || 'Conexión correcta');
      } else {
        ui.notify(result.message || 'Fallo de conexión', 'error');
      }
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'Error en el test de conexión', 'error');
    } finally {
      testing = null;
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    deleteBusy = true;
    try {
      await api(`/admin/providers/${deleting.id}`, { method: 'DELETE' });
      ui.notify('Proveedor eliminado');
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
  <h1>Proveedores</h1>
  <button class="btn primary" type="button" onclick={openCreate}>
    <IconPlus size={16} />
    Nuevo proveedor
  </button>
</div>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if providers.length === 0}
  <div class="empty">
    <p>No hay proveedores todavía.</p>
    <button class="btn" type="button" onclick={openCreate}>Crear el primero</button>
  </div>
{:else}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Nombre</th>
          <th>Tipo</th>
          <th>Estado</th>
          <th>Base URL</th>
          <th>Clave</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        {#each providers as p (p.id)}
          <tr>
            <td class="strong">{p.name}</td>
            <td class="mono muted">{p.kind}</td>
            <td>
              {#if p.is_enabled}
                <span class="badge ok">activo</span>
              {:else}
                <span class="badge off">inactivo</span>
              {/if}
            </td>
            <td class="mono muted">{p.base_url ?? '—'}</td>
            <td class="tabular-nums muted"
              >{p.credential_last_four ? `…${p.credential_last_four}` : '—'}</td
            >
            <td>
              <div class="row-actions">
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => testConnection(p)}
                  disabled={testing === p.id}
                  aria-label="Probar conexión"
                >
                  <IconRefresh size={16} />
                </button>
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => openEdit(p)}
                  aria-label="Editar"
                >
                  <IconEdit size={16} />
                </button>
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => openRotate(p)}
                  aria-label="Rotar credencial"
                >
                  <IconGlobe size={16} />
                </button>
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => (deleting = p)}
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
    <ProviderForm mode={drawer.mode} provider={drawer.provider} onSaved={handleSaved} />
    {#if drawer.mode === 'edit' && drawer.provider}
      <ModelsSection provider={drawer.provider} />
    {/if}
  {/if}
</Drawer>

<ConfirmDialog
  open={deleting !== null}
  title="Eliminar proveedor"
  confirmLabel="Eliminar"
  danger
  busy={deleteBusy}
  onconfirm={confirmDelete}
  oncancel={() => (deleting = null)}
>
  ¿Eliminar el proveedor "{deleting?.name}"? Esta acción no se puede deshacer.
</ConfirmDialog>
