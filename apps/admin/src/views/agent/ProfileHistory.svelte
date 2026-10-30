<script lang="ts">
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import { api } from '../../lib/api.js';
  import { sideBySide, type DiffCell } from '../../lib/diff.js';
  import { formatDateTime, messageOf } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { AgentProfile, AgentProfileConfig, AgentProfileVersion } from '../../lib/types.js';

  interface Props {
    profile: AgentProfile;
    onchange: (profile: AgentProfile) => void;
  }

  let { profile, onchange }: Props = $props();

  const CONFIG_SECTIONS: { key: keyof AgentProfileConfig; label: string }[] = [
    { key: 'tools', label: 'Herramientas' },
    { key: 'planning', label: 'Planificación' },
    { key: 'plan_review', label: 'Revisión del plan' },
    { key: 'subagents', label: 'Subagentes' },
    { key: 'limits', label: 'Límites' },
  ];

  let compareVersion = $state<number | null>(null);
  let rollbackTarget = $state<AgentProfileVersion | null>(null);
  let rollbackBusy = $state(false);

  let compared = $derived(
    profile.history.find((version) => version.version === compareVersion) ?? null,
  );

  let comparison = $derived(compared ? buildComparison(compared, profile.active) : null);

  function buildComparison(left: AgentProfileVersion, right: AgentProfileVersion) {
    const promptRows = sideBySide(left.system_prompt, right.system_prompt);
    const sections = CONFIG_SECTIONS.filter(
      (section) =>
        JSON.stringify(left.config[section.key]) !== JSON.stringify(right.config[section.key]),
    ).map((section) => ({
      label: section.label,
      rows: sideBySide(
        JSON.stringify(left.config[section.key], null, 2),
        JSON.stringify(right.config[section.key], null, 2),
      ),
    }));
    return {
      promptChanged: left.system_prompt !== right.system_prompt,
      promptRows,
      sections,
    };
  }

  function toggleCompare(version: number | null) {
    compareVersion = compareVersion === version ? null : version;
  }

  async function rollback() {
    const target = rollbackTarget;
    if (!target || target.version === null) return;
    rollbackBusy = true;
    try {
      const updated = await api<AgentProfile>(
        `/admin/agent/profiles/${profile.mode}/activate/${target.version}`,
        { method: 'POST' },
      );
      ui.notify(`Versión ${target.version} activa de nuevo`);
      compareVersion = null;
      onchange(updated);
    } catch (e) {
      ui.notify(messageOf(e, 'No se pudo restaurar la versión'), 'error');
    } finally {
      rollbackBusy = false;
      rollbackTarget = null;
    }
  }

  function cellClass(cell: DiffCell | null): string {
    return cell ? cell.kind : 'empty';
  }
</script>

<section class="history" aria-label="Versiones del perfil">
  <h3 class="section-title">Versiones</h3>

  {#if profile.history.length === 0}
    <p class="muted small">
      Todavía no hay versiones guardadas. El modo usa los defaults de código hasta que guardes una.
    </p>
  {:else}
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th>Versión</th>
            <th>Autor</th>
            <th>Fecha</th>
            <th>Estado</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each profile.history as version (version.version)}
            <tr class={compareVersion === version.version ? 'selected' : ''}>
              <td class="mono strong">v{version.version}</td>
              <td class="muted">{version.created_by_email ?? '—'}</td>
              <td class="tabular-nums muted">{formatDateTime(version.created_at)}</td>
              <td>
                {#if version.is_active}
                  <span class="badge ok">activa</span>
                {:else}
                  <span class="badge off">anterior</span>
                {/if}
              </td>
              <td>
                {#if !version.is_active}
                  <div class="row-actions">
                    <button
                      class="btn ghost small-btn"
                      type="button"
                      onclick={() => toggleCompare(version.version)}
                    >
                      {compareVersion === version.version ? 'Ocultar diff' : 'Comparar con activa'}
                    </button>
                    <button
                      class="btn small-btn"
                      type="button"
                      onclick={() => (rollbackTarget = version)}
                    >
                      Restaurar
                    </button>
                  </div>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  {#if compared && comparison}
    <div class="diff" aria-label="Diferencias con la versión activa">
      <h4 class="diff-title">v{compared.version} → v{profile.active.version} (activa)</h4>

      <h5 class="diff-sub">Prompt de sistema</h5>
      {#if !comparison.promptChanged}
        <p class="muted small">Sin cambios en el prompt.</p>
      {:else}
        <div class="side" role="table">
          <div class="side-head" role="row">
            <span role="columnheader">v{compared.version}</span>
            <span role="columnheader">v{profile.active.version}</span>
          </div>
          {#each comparison.promptRows as row, index (index)}
            <div class="side-row" role="row">
              <div class="cell {cellClass(row.left)}" role="cell">
                <code>{row.left?.text ?? ''}</code>
              </div>
              <div class="cell {cellClass(row.right)}" role="cell">
                <code>{row.right?.text ?? ''}</code>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <h5 class="diff-sub">Configuración</h5>
      {#if comparison.sections.length === 0}
        <p class="muted small">
          Sin cambios en herramientas, planificación, subagentes ni límites.
        </p>
      {:else}
        {#each comparison.sections as section (section.label)}
          <p class="muted small section-label">{section.label}</p>
          <div class="side" role="table">
            {#each section.rows as row, index (index)}
              <div class="side-row" role="row">
                <div class="cell {cellClass(row.left)}" role="cell">
                  <code>{row.left?.text ?? ''}</code>
                </div>
                <div class="cell {cellClass(row.right)}" role="cell">
                  <code>{row.right?.text ?? ''}</code>
                </div>
              </div>
            {/each}
          </div>
        {/each}
      {/if}
    </div>
  {/if}
</section>

<ConfirmDialog
  open={rollbackTarget !== null}
  title="Restaurar versión"
  confirmLabel="Restaurar"
  busy={rollbackBusy}
  onconfirm={rollback}
  oncancel={() => (rollbackTarget = null)}
>
  Se activará la versión v{rollbackTarget?.version}. Los runs nuevos usarán esa versión; los runs
  anteriores conservan la que usaron.
</ConfirmDialog>

<style>
  .history {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
  }

  .history > .section-title {
    margin: 0;
  }

  .small {
    font-size: 13px;
  }

  .small-btn {
    padding: 4px 10px;
    font-size: 13px;
  }

  .row-actions {
    display: inline-flex;
    gap: 6px;
  }

  .table tr.selected td {
    background: color-mix(in oklab, var(--p-acc) 10%, transparent);
  }

  .diff {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-top: 12px;
    border-top: 1px solid var(--p-line);
  }

  .diff-title {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
  }

  .diff-sub {
    margin: 6px 0 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--p-mut);
  }

  .section-label {
    margin: 4px 0 0;
    font-weight: 600;
  }

  .side {
    display: flex;
    flex-direction: column;
    max-height: 420px;
    overflow: auto;
    border: 1px solid var(--p-line);
    border-radius: 10px;
    background: var(--p-surf-2);
  }

  .side-head,
  .side-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .side-head {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--p-surf-2);
    border-bottom: 1px solid var(--p-line);
    font-size: 12px;
    font-weight: 600;
    color: var(--p-mut);
  }

  .side-head span {
    padding: 6px 10px;
  }

  .cell {
    padding: 0 10px;
    min-height: 20px;
    border-right: 1px solid var(--p-line);
  }

  .cell:last-child {
    border-right: none;
  }

  .cell code {
    display: block;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12.5px;
    line-height: 1.55;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .cell.add {
    background: color-mix(in oklab, var(--sem-success) 16%, transparent);
  }

  .cell.del {
    background: color-mix(in oklab, var(--sem-critical) 16%, transparent);
  }

  .cell.empty {
    background: color-mix(in oklab, var(--p-mut) 6%, transparent);
  }
</style>
