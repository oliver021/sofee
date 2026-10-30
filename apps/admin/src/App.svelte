<script lang="ts">
  import { onMount } from 'svelte';
  import Toasts from './components/Toasts.svelte';
  import { auth } from './lib/auth.svelte.js';
  import { ui, type ViewId } from './lib/ui.svelte.js';
  import Login from './views/Login.svelte';
  import AgentView from './views/agent/AgentView.svelte';
  import AuditView from './views/audit/AuditView.svelte';
  import CatalogView from './views/catalog/CatalogView.svelte';
  import FeedbackView from './views/feedback/FeedbackView.svelte';
  import HomeView from './views/home/HomeView.svelte';
  import IntegrationsView from './views/integrations/IntegrationsView.svelte';
  import KnowledgeView from './views/knowledge/KnowledgeView.svelte';
  import ProvidersView from './views/providers/ProvidersView.svelte';
  import RunsView from './views/runs/RunsView.svelte';
  import UsageView from './views/usage/UsageView.svelte';
  import UsersView from './views/users/UsersView.svelte';

  // Agent operations first (the screens people open daily), then the platform screens.
  const NAV_GROUPS: { label: string; items: { id: ViewId; label: string }[] }[] = [
    {
      label: 'Agente',
      items: [
        { id: 'home', label: 'Inicio' },
        { id: 'agent', label: 'Agente' },
        { id: 'knowledge', label: 'Conocimiento' },
        { id: 'integrations', label: 'Integraciones' },
        { id: 'runs', label: 'Runs' },
        { id: 'feedback', label: 'Valoraciones' },
        { id: 'usage', label: 'Uso' },
      ],
    },
    {
      label: 'Plataforma',
      items: [
        { id: 'catalog', label: 'Catálogo' },
        { id: 'providers', label: 'Proveedores' },
        { id: 'users', label: 'Usuarios' },
        { id: 'audit', label: 'Auditoría' },
      ],
    },
  ];

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
      {#each NAV_GROUPS as group, groupIndex (group.label)}
        {#if groupIndex > 0}
          <span class="sep" aria-hidden="true"></span>
        {/if}
        {#each group.items as item (item.id)}
          <button
            class="nav-item {ui.view === item.id ? 'active' : ''}"
            type="button"
            aria-current={ui.view === item.id ? 'page' : undefined}
            onclick={() => ui.switchTo(item.id)}
          >
            {item.label}
          </button>
        {/each}
      {/each}
    </nav>
    <div class="user">
      <span class="email">{auth.user.email}</span>
      <button class="nav-item" type="button" onclick={() => auth.logout()}> Cerrar sesión </button>
    </div>
  </header>

  <div class="content">
    {#if ui.view === 'home'}
      <HomeView />
    {:else if ui.view === 'agent'}
      <AgentView />
    {:else if ui.view === 'knowledge'}
      <KnowledgeView />
    {:else if ui.view === 'integrations'}
      <IntegrationsView />
    {:else if ui.view === 'runs'}
      <RunsView />
    {:else if ui.view === 'feedback'}
      <FeedbackView />
    {:else if ui.view === 'usage'}
      <UsageView />
    {:else if ui.view === 'providers'}
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
    align-items: center;
    gap: 4px;
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    scrollbar-width: thin;
  }

  .nav-item {
    white-space: nowrap;
  }

  .sep {
    flex: none;
    width: 1px;
    height: 20px;
    margin: 0 8px;
    background: var(--p-line);
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

  /* Eleven sections do not fit beside the brand and the account at narrow widths: the nav
     moves to its own row instead of scrolling sideways. */
  @media (max-width: 1180px) {
    .topbar {
      flex-wrap: wrap;
      height: auto;
      padding-block: 10px;
      row-gap: 8px;
    }

    .nav {
      order: 3;
      flex-basis: 100%;
    }
  }
</style>
