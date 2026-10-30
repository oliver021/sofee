<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../../lib/api.js';
  import { messageOf } from '../../lib/format.js';
  import type { AgentProfile } from '../../lib/types.js';
  import AgentSettings from './AgentSettings.svelte';
  import ProfileEditor from './ProfileEditor.svelte';
  import { AGENT_MODES, AGENT_MODE_META } from './agent-meta.js';

  type Tab = (typeof AGENT_MODES)[number] | 'settings';

  const TABS: { id: Tab; label: string }[] = [
    ...AGENT_MODES.map((mode) => ({ id: mode as Tab, label: AGENT_MODE_META[mode].label })),
    { id: 'settings', label: 'Ajustes' },
  ];

  let tab = $state<Tab>('learn');
  let profiles = $state<AgentProfile[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);

  async function load() {
    loading = true;
    loadError = null;
    try {
      profiles = await api<AgentProfile[]>('/admin/agent/profiles');
    } catch (e) {
      loadError = messageOf(e, 'No se pudieron cargar los perfiles del agente');
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function replaceProfile(updated: AgentProfile) {
    profiles = profiles.map((profile) => (profile.mode === updated.mode ? updated : profile));
  }
</script>

<div class="view-head">
  <div>
    <h1>Agente</h1>
    <p class="muted intro">
      Perfiles por modo y ajustes generales. Cada guardado crea una versión nueva y la deja activa.
    </p>
  </div>
</div>

<div class="tabs" role="tablist" aria-label="Secciones del agente">
  {#each TABS as item (item.id)}
    <button
      type="button"
      role="tab"
      class="tab {tab === item.id ? 'active' : ''}"
      aria-selected={tab === item.id}
      onclick={() => (tab = item.id)}
    >
      {item.label}
    </button>
  {/each}
</div>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else}
  <!-- Each mode editor stays mounted while its tab is hidden, so unsaved edits survive tab switches. -->
  {#each AGENT_MODES as mode (mode)}
    {@const profile = profiles.find((p) => p.mode === mode)}
    <div hidden={tab !== mode} role="tabpanel">
      {#if profile}
        {#key profile.active.version ?? 'default'}
          <ProfileEditor {profile} onchange={replaceProfile} />
        {/key}
      {/if}
    </div>
  {/each}
  <div hidden={tab !== 'settings'} role="tabpanel">
    <AgentSettings />
  </div>
{/if}

<style>
  .view-head h1 {
    margin: 0;
  }

  .intro {
    margin: 4px 0 0;
    font-size: 13.5px;
  }

  .tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 20px;
    border-bottom: 1px solid var(--p-line);
    overflow-x: auto;
  }

  .tab {
    margin-bottom: -1px;
    padding: 8px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    background: transparent;
    color: var(--p-mut);
    font: inherit;
    font-weight: 500;
    cursor: pointer;
    white-space: nowrap;
  }

  .tab:hover {
    color: var(--p-ink);
  }

  .tab.active {
    border-bottom-color: var(--p-acc);
    color: var(--p-acc);
    font-weight: 600;
  }
</style>
