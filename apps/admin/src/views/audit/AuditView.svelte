<script lang="ts">
  import { onMount } from 'svelte';
  import { IconRefresh } from '@sofee/icons';
  import { api } from '../../lib/api.js';
  import type { AuditEntry, AuditPage } from '../../lib/types.js';

  const ACTIONS = [
    'user.login_failed',
    'session.revoked',
    'user.role_changed',
    'user.deactivated',
    'user.activated',
    'user.sessions_revoked',
    'provider.created',
    'provider.updated',
    'provider.deleted',
    'provider.credential_rotated',
    'provider.model_toggled',
    'provider.models_synced',
    'provider.model_capabilities_updated',
    'catalog.entry_created',
    'catalog.entry_updated',
    'catalog.entry_deleted',
    'catalog.binding_added',
    'catalog.binding_updated',
    'catalog.binding_removed',
    'catalog.agent_tested',
    'agent.profile_version_created',
    'agent.profile_version_activated',
    'agent.settings_updated',
    'agent.run_cancelled',
    'agent.feedback_reviewed',
    'kb.document_uploaded',
    'kb.document_updated',
    'kb.document_deleted',
    'integration.tavily_key_set',
    'integration.tavily_tested',
    'storage.object_uploaded',
    'storage.object_deleted',
  ];

  const RESOURCE_TYPES = [
    'provider',
    'user',
    'session',
    'storage_object',
    'catalog_entry',
    'agent_profile',
    'agent_settings',
    'agent_run',
    'message_feedback',
    'kb_document',
    'integration',
  ];

  let entries = $state<AuditEntry[]>([]);
  let loading = $state(true);
  let loadingMore = $state(false);
  let loadError = $state<string | null>(null);
  let action = $state('');
  let resourceType = $state('');
  let nextCursor = $state<string | null>(null);

  function formatDate(value: string): string {
    return new Date(value).toLocaleString('es', {
      dateStyle: 'short',
      timeStyle: 'medium',
    });
  }

  function metadataText(entry: AuditEntry): string {
    return entry.metadata ? JSON.stringify(entry.metadata) : '—';
  }

  async function load(reset = true) {
    if (reset) {
      loading = true;
    } else {
      loadingMore = true;
    }
    loadError = null;

    const params: string[] = [];
    if (action) params.push(`action=${encodeURIComponent(action)}`);
    if (resourceType) params.push(`resource_type=${encodeURIComponent(resourceType)}`);
    if (!reset && nextCursor) params.push(`cursor=${encodeURIComponent(nextCursor)}`);
    const qs = params.length > 0 ? `?${params.join('&')}` : '';

    try {
      const page = await api<AuditPage>(`/admin/audit${qs}`);
      entries = reset ? page.items : [...entries, ...page.items];
      nextCursor = page.next_cursor;
    } catch (e) {
      loadError = e instanceof Error ? e.message : 'No se pudo cargar la auditoría';
    } finally {
      loading = false;
      loadingMore = false;
    }
  }

  onMount(() => {
    void load();
  });
</script>

<div class="view-head">
  <h1>Auditoría</h1>
  <div class="filters">
    <select class="input" bind:value={action} aria-label="Filtrar por acción">
      <option value="">Todas las acciones</option>
      {#each ACTIONS as a (a)}
        <option value={a}>{a}</option>
      {/each}
    </select>
    <select class="input" bind:value={resourceType} aria-label="Filtrar por tipo de recurso">
      <option value="">Todos los recursos</option>
      {#each RESOURCE_TYPES as rt (rt)}
        <option value={rt}>{rt}</option>
      {/each}
    </select>
    <button class="btn" type="button" onclick={() => load(true)}>
      <IconRefresh size={15} />
      Filtrar
    </button>
  </div>
</div>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if entries.length === 0}
  <div class="empty">
    <p>No hay eventos que coincidan con los filtros.</p>
  </div>
{:else}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Fecha</th>
          <th>Actor</th>
          <th>Acción</th>
          <th>Recurso</th>
          <th>IP</th>
          <th>Detalles</th>
        </tr>
      </thead>
      <tbody>
        {#each entries as entry (entry.id)}
          <tr>
            <td class="tabular-nums muted">{formatDate(entry.created_at)}</td>
            <td>{entry.actor_email ?? '—'}</td>
            <td class="mono strong">{entry.action}</td>
            <td class="mono muted">
              {entry.resource_type ?? '—'}
              {#if entry.resource_id}
                · {entry.resource_id}
              {/if}
            </td>
            <td class="mono muted">{entry.ip_address ?? '—'}</td>
            <td class="mono muted detail" title={metadataText(entry)}>
              {metadataText(entry)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if nextCursor}
    <div class="pager">
      <button class="btn" type="button" onclick={() => void load(false)} disabled={loadingMore}>
        {loadingMore ? 'Cargando…' : 'Cargar más'}
      </button>
    </div>
  {/if}
{/if}

<style>
  .filters {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }

  .filters .input {
    width: auto;
  }

  .detail {
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .pager {
    display: flex;
    justify-content: center;
    margin-top: 16px;
  }
</style>
