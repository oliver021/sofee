<script lang="ts">
  import { onMount } from 'svelte';
  import { IconSearch, IconSettings } from '@sofee/icons';
  import Drawer from '../../components/Drawer.svelte';
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import { auth } from '../../lib/auth.svelte.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { User } from '../../lib/types.js';
  import SessionsPanel from './SessionsPanel.svelte';

  let users = $state<User[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let search = $state('');
  let busy = $state<string | null>(null);
  let searchTimeout = 0;
  let sessionsUser = $state<User | null>(null);

  function formatDate(value: string | null): string {
    if (!value) return '—';
    return new Date(value).toLocaleString('es', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  }

  async function load() {
    loading = true;
    loadError = null;
    try {
      const query = search.trim() ? `?q=${encodeURIComponent(search.trim())}` : '';
      users = await api<User[]>(`/admin/users${query}`);
    } catch (e) {
      loadError = e instanceof Error ? e.message : 'No se pudieron cargar los usuarios';
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function onSearchInput() {
    window.clearTimeout(searchTimeout);
    searchTimeout = window.setTimeout(load, 300);
  }

  async function changeRole(user: User, role: User['role']) {
    if (role === user.role) return;
    const previous = user.role;
    user.role = role;
    busy = user.id;
    try {
      await api(`/admin/users/${user.id}`, { method: 'PATCH', body: { role } });
      ui.notify(`Rol de ${user.email} actualizado`);
    } catch (e) {
      user.role = previous;
      ui.notify(e instanceof Error ? e.message : 'No se pudo cambiar el rol', 'error');
    } finally {
      busy = null;
    }
  }

  async function toggleActive(user: User, isActive: boolean) {
    const previous = user.is_active;
    user.is_active = isActive;
    busy = user.id;
    try {
      await api(`/admin/users/${user.id}`, { method: 'PATCH', body: { is_active: isActive } });
      ui.notify(isActive ? `${user.email} reactivado` : `${user.email} desactivado`);
    } catch (e) {
      user.is_active = previous;
      ui.notify(e instanceof Error ? e.message : 'No se pudo actualizar el estado', 'error');
    } finally {
      busy = null;
    }
  }
</script>

<div class="view-head">
  <h1>Usuarios</h1>
  <div class="search">
    <IconSearch size={15} />
    <input
      class="input"
      type="search"
      placeholder="Buscar por correo o nombre…"
      bind:value={search}
      oninput={onSearchInput}
      aria-label="Buscar usuarios"
    />
  </div>
</div>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if users.length === 0}
  <div class="empty">
    <p>{search.trim() ? 'Sin resultados para esa búsqueda.' : 'No hay usuarios todavía.'}</p>
  </div>
{:else}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Correo</th>
          <th>Nombre</th>
          <th>Rol</th>
          <th>Estado</th>
          <th>Última sesión</th>
          <th>Registro</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each users as user (user.id)}
          {@const isSelf = auth.user?.id === user.id}
          <tr class={user.is_active ? '' : 'row-off'}>
            <td class="strong">{user.email}</td>
            <td>{user.display_name}</td>
            <td>
              {#if isSelf}
                <span class="badge ok">{user.role}</span>
              {:else}
                <select
                  class="input role-select"
                  value={user.role}
                  disabled={busy === user.id}
                  onchange={(e) => changeRole(user, e.currentTarget.value as User['role'])}
                  aria-label="Rol de {user.email}"
                >
                  <option value="admin">admin</option>
                  <option value="regular">regular</option>
                </select>
              {/if}
            </td>
            <td>
              <Switch
                checked={user.is_active}
                disabled={busy === user.id || isSelf}
                label="{user.is_active ? 'Desactivar' : 'Activar'} a {user.email}"
                onchange={(v) => toggleActive(user, v)}
              />
            </td>
            <td class="muted tabular-nums">{formatDate(user.last_login_at)}</td>
            <td class="muted tabular-nums">{formatDate(user.created_at)}</td>
            <td>
              <div class="row-actions">
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => (sessionsUser = user)}
                  aria-label="Gestionar sesiones de {user.email}"
                >
                  <IconSettings size={16} />
                </button>
              </div>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<Drawer
  open={sessionsUser !== null}
  title={sessionsUser ? `Sesiones de ${sessionsUser.email}` : ''}
  onclose={() => (sessionsUser = null)}
>
  {#if sessionsUser}
    <SessionsPanel user={sessionsUser} />
  {/if}
</Drawer>

<style>
  .search {
    position: relative;
    width: min(320px, 100%);
    display: flex;
    align-items: center;
    color: var(--p-mut);
  }

  .search > :global(svg) {
    position: absolute;
    left: 10px;
    pointer-events: none;
  }

  .search .input {
    padding-left: 32px;
  }

  .role-select {
    width: auto;
    padding: 5px 8px;
    font-size: 13px;
  }

  .row-off {
    opacity: 0.55;
  }
</style>
