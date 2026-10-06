<script lang="ts">
  import { onMount } from 'svelte';
  import { IconTrash } from '@sofee/icons';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import { api } from '../../lib/api.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { Session, User } from '../../lib/types.js';

  interface Props {
    user: User;
  }

  let { user }: Props = $props();

  let sessions = $state<Session[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let revoking = $state<string | null>(null);
  let revokingAll = $state(false);
  let confirmAll = $state(false);

  function formatDate(value: string): string {
    return new Date(value).toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' });
  }

  async function load() {
    loading = true;
    loadError = null;
    try {
      sessions = await api<Session[]>(`/admin/users/${user.id}/sessions`);
    } catch (e) {
      loadError = e instanceof Error ? e.message : 'No se pudieron cargar las sesiones';
    } finally {
      loading = false;
    }
  }

  onMount(load);

  async function revoke(sessionId: string) {
    revoking = sessionId;
    try {
      await api(`/admin/sessions/${sessionId}`, { method: 'DELETE' });
      ui.notify('Sesión revocada');
      await load();
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudo revocar la sesión', 'error');
    } finally {
      revoking = null;
    }
  }

  async function revokeAll() {
    confirmAll = false;
    revokingAll = true;
    try {
      await api(`/admin/users/${user.id}/revoke-sessions`, { method: 'POST' });
      ui.notify(`Todas las sesiones de ${user.email} revocadas`);
      await load();
    } catch (e) {
      ui.notify(e instanceof Error ? e.message : 'No se pudieron revocar las sesiones', 'error');
    } finally {
      revokingAll = false;
    }
  }
</script>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else}
  <div class="session-count">
    {sessions.length === 0
      ? 'No hay sesiones activas.'
      : `${sessions.length} sesión ${sessions.length === 1 ? 'activa' : 'activas'}.`}
  </div>

  {#if sessions.length > 0}
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Creada</th>
            <th>Expira</th>
            <th>Dispositivo</th>
            <th>IP</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each sessions as session (session.id)}
            <tr>
              <td class="tabular-nums muted">{formatDate(session.created_at)}</td>
              <td class="tabular-nums muted">{formatDate(session.expires_at)}</td>
              <td class="muted">{session.user_agent ?? '—'}</td>
              <td class="mono muted">{session.ip_address ?? '—'}</td>
              <td>
                <div class="row-actions">
                  <button
                    class="icon-btn"
                    type="button"
                    onclick={() => revoke(session.id)}
                    disabled={revoking === session.id}
                    aria-label="Revocar esta sesión"
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

    <div class="revoke-all">
      <button
        class="btn danger"
        type="button"
        onclick={() => (confirmAll = true)}
        disabled={revokingAll}
      >
        {revokingAll ? 'Revocando…' : 'Cerrar todas las sesiones'}
      </button>
    </div>

    <ConfirmDialog
      open={confirmAll}
      title="Cerrar todas las sesiones"
      confirmLabel="Cerrar todas"
      danger
      busy={revokingAll}
      onconfirm={revokeAll}
      oncancel={() => (confirmAll = false)}
    >
      Se cerrarán todas las sesiones activas de {user.email}. Esta acción no se puede deshacer.
    </ConfirmDialog>
  {/if}
{/if}

<style>
  .session-count {
    margin-bottom: 12px;
    color: var(--p-mut);
    font-size: 13px;
  }

  .revoke-all {
    margin-top: 16px;
    display: flex;
    justify-content: flex-end;
  }
</style>
