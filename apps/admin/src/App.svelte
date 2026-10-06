<script lang="ts">
  import { onMount } from 'svelte';
  import Toasts from './components/Toasts.svelte';
  import { auth } from './lib/auth.svelte.js';
  import { ui } from './lib/ui.svelte.js';
  import Login from './views/Login.svelte';
  import AuditView from './views/audit/AuditView.svelte';
  import CatalogView from './views/catalog/CatalogView.svelte';
  import ProvidersView from './views/providers/ProvidersView.svelte';
  import UsersView from './views/users/UsersView.svelte';

  onMount(() => {
    auth.bootstrap();
  });
</script>

{#if auth.bootstrapping}
  <div class="boot">
    <p class="boot-text">Cargando…</p>
  </div>
{:else if !auth.user}
  <Login />
{:else if auth.user.role !== 'admin'}
  <div class="boot">
    <p class="boot-text">
      Tu cuenta no tiene permisos de administrador.
      <button class="nav-item" type="button" onclick={() => auth.logout()}>Cerrar sesión</button>
    </p>
  </div>
{:else}
  <header class="topbar">
    <span class="brand">Sofee Admin</span>
    <nav class="nav" aria-label="Secciones">
      <button
        class="nav-item {ui.view === 'providers' ? 'active' : ''}"
        type="button"
        onclick={() => ui.switchTo('providers')}
      >
        Proveedores
      </button>
      <button
        class="nav-item {ui.view === 'catalog' ? 'active' : ''}"
        type="button"
        onclick={() => ui.switchTo('catalog')}
      >
        Catálogo
      </button>
      <button
        class="nav-item {ui.view === 'users' ? 'active' : ''}"
        type="button"
        onclick={() => ui.switchTo('users')}
      >
        Usuarios
      </button>
      <button
        class="nav-item {ui.view === 'audit' ? 'active' : ''}"
        type="button"
        onclick={() => ui.switchTo('audit')}
      >
        Auditoría
      </button>
    </nav>
    <div class="user">
      <span class="email">{auth.user.email}</span>
      <button class="nav-item" type="button" onclick={() => auth.logout()}> Cerrar sesión </button>
    </div>
  </header>

  <div class="content">
    {#if ui.view === 'providers'}
      <ProvidersView />
    {:else if ui.view === 'catalog'}
      <CatalogView />
    {:else if ui.view === 'users'}
      <UsersView />
    {:else}
      <AuditView />
    {/if}
  </div>

  <Toasts />
{/if}

<style>
  .boot {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .boot-text {
    color: var(--p-mut);
  }

  .topbar {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 0 20px;
    height: 56px;
    flex: none;
    border-bottom: 1px solid var(--p-line);
    background: var(--p-surf);
  }

  .brand {
    font-size: 15px;
    font-weight: 700;
  }

  .nav {
    display: flex;
    gap: 4px;
    flex: 1;
  }

  .nav-item {
    padding: 7px 12px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--p-mut);
    font: inherit;
    font-size: 13.5px;
    font-weight: 500;
    cursor: pointer;
  }

  .nav-item:hover {
    background: var(--p-hi);
    color: var(--p-ink);
  }

  .nav-item.active {
    background: color-mix(in oklab, var(--p-acc) 16%, transparent);
    color: var(--p-acc);
    font-weight: 600;
  }

  .user {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .email {
    color: var(--p-mut);
    font-size: 13px;
  }

  .content {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
  }
</style>
