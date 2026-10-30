<script lang="ts">
  import { onMount } from 'svelte';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import { isUuid, messageOf } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { AgentMode, AgentSettings, AgentQuotaLimits, UserRole } from '../../lib/types.js';
  import {
    AGENT_MODES,
    AGENT_MODE_META,
    ROLE_LABELS,
    STARTER_LOCALES,
    USER_ROLES,
  } from './agent-meta.js';

  const STARTERS_MAX = 10;
  const STARTER_MAX_CHARS = 300;
  const REPLAY_MAX = 50;
  const QUOTA_MAX_RUNS = 1_000_000;
  const QUOTA_MAX_TOKENS = 1_000_000_000;

  type Locale = (typeof STARTER_LOCALES)[number]['code'];

  interface ReplayDraft {
    prompt: string;
    run_id: string;
  }

  interface Draft {
    enabled: boolean;
    starters: Record<AgentMode, Record<Locale, string[]>>;
    replay: ReplayDraft[];
    quotas: Record<UserRole, AgentQuotaLimits>;
  }

  function emptyStarters(): Record<AgentMode, Record<Locale, string[]>> {
    return {
      learn: { es: [], en: [] },
      research: { es: [], en: [] },
      explore: { es: [], en: [] },
    };
  }

  function draftFrom(settings: AgentSettings): Draft {
    const starters = emptyStarters();
    for (const mode of AGENT_MODES) {
      for (const { code } of STARTER_LOCALES) {
        starters[mode][code] = [...(settings.starters[mode]?.[code] ?? [])];
      }
    }
    const quotas = {} as Record<UserRole, AgentQuotaLimits>;
    for (const role of USER_ROLES) {
      quotas[role] = {
        runs_per_day: settings.quotas[role]?.runs_per_day ?? null,
        tokens_per_day: settings.quotas[role]?.tokens_per_day ?? null,
      };
    }
    return {
      enabled: settings.enabled,
      starters,
      replay: settings.replay_map.map((entry) => ({ prompt: entry.prompt, run_id: entry.run_id })),
      quotas,
    };
  }

  function buildPayload(d: Draft): AgentSettings {
    const starters: Record<string, Record<string, string[]>> = {};
    for (const mode of AGENT_MODES) {
      starters[mode] = {};
      for (const { code } of STARTER_LOCALES) {
        starters[mode][code] = (d.starters[mode][code] ?? [])
          .map((text) => text.trim())
          .filter((text) => text.length > 0);
      }
    }
    const quotas: Partial<Record<UserRole, AgentQuotaLimits>> = {};
    for (const role of USER_ROLES) {
      const limits = d.quotas[role];
      quotas[role] = { runs_per_day: limits.runs_per_day, tokens_per_day: limits.tokens_per_day };
    }
    return {
      enabled: d.enabled,
      starters,
      replay_map: d.replay
        .map((entry) => ({ prompt: entry.prompt.trim(), run_id: entry.run_id.trim() }))
        .filter((entry) => entry.prompt.length > 0 || entry.run_id.length > 0),
      quotas,
    };
  }

  function validate(d: Draft): string | null {
    for (const mode of AGENT_MODES) {
      for (const { code } of STARTER_LOCALES) {
        const texts = d.starters[mode][code];
        if (texts.length > STARTERS_MAX) {
          return `Como máximo ${STARTERS_MAX} preguntas por modo e idioma.`;
        }
        if (texts.some((text) => text.trim().length > STARTER_MAX_CHARS)) {
          return `Cada pregunta de arranque tiene como máximo ${STARTER_MAX_CHARS} caracteres.`;
        }
      }
    }
    if (d.replay.length > REPLAY_MAX) return `Como máximo ${REPLAY_MAX} entradas en el modo demo.`;
    for (const entry of d.replay) {
      if (entry.prompt.trim().length === 0 || entry.prompt.trim().length > 500) {
        return 'Cada entrada del modo demo necesita una pregunta de hasta 500 caracteres.';
      }
      if (!isUuid(entry.run_id.trim())) {
        return 'El ID de run del modo demo no es válido. Cópialo desde la vista Runs.';
      }
    }
    for (const role of USER_ROLES) {
      const limits = d.quotas[role];
      if (!isValidQuota(limits.runs_per_day, QUOTA_MAX_RUNS)) {
        return `Runs por día (${ROLE_LABELS[role]}): usa un entero entre 0 y ${QUOTA_MAX_RUNS}, o déjalo vacío.`;
      }
      if (!isValidQuota(limits.tokens_per_day, QUOTA_MAX_TOKENS)) {
        return `Tokens por día (${ROLE_LABELS[role]}): usa un entero entre 0 y ${QUOTA_MAX_TOKENS}, o déjalo vacío.`;
      }
    }
    return null;
  }

  function isValidQuota(value: number | null, max: number): boolean {
    return value === null || (Number.isInteger(value) && value >= 0 && value <= max);
  }

  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let ready = $state(false);
  let serverSettings = $state<AgentSettings | null>(null);
  let draft = $state<Draft>({
    enabled: true,
    starters: emptyStarters(),
    replay: [],
    quotas: {
      admin: { runs_per_day: null, tokens_per_day: null },
      regular: { runs_per_day: null, tokens_per_day: null },
    },
  });
  let baseline = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);
  let confirmOff = $state(false);
  let starterMode = $state<AgentMode>('learn');
  let starterLocale = $state<Locale>('es');

  let dirty = $derived(ready && JSON.stringify(draft) !== baseline);
  let previewStarters = $derived(
    draft.starters[starterMode][starterLocale]
      .map((text) => text.trim())
      .filter((text) => text.length > 0),
  );

  function applySettings(data: AgentSettings) {
    const next = draftFrom(data);
    serverSettings = data;
    draft = next;
    baseline = JSON.stringify(next);
    ready = true;
  }

  async function load() {
    loading = true;
    loadError = null;
    try {
      applySettings(await api<AgentSettings>('/admin/agent/settings'));
    } catch (e) {
      loadError = messageOf(e, 'No se pudieron cargar los ajustes del agente');
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function discard() {
    if (serverSettings) applySettings(serverSettings);
    error = null;
  }

  function addStarter() {
    const list = draft.starters[starterMode][starterLocale];
    if (list.length < STARTERS_MAX) list.push('');
  }

  function removeStarter(index: number) {
    draft.starters[starterMode][starterLocale].splice(index, 1);
  }

  function addReplay() {
    if (draft.replay.length < REPLAY_MAX) draft.replay.push({ prompt: '', run_id: '' });
  }

  function removeReplay(index: number) {
    draft.replay.splice(index, 1);
  }

  function requestSave() {
    const problem = validate(draft);
    if (problem) {
      error = problem;
      return;
    }
    error = null;
    // Turning the agent off is the one change that stops every conversation, so it gets a confirm.
    if (serverSettings?.enabled && !draft.enabled) {
      confirmOff = true;
      return;
    }
    void persist();
  }

  async function persist() {
    confirmOff = false;
    busy = true;
    error = null;
    try {
      const data = await api<AgentSettings>('/admin/agent/settings', {
        method: 'PUT',
        body: buildPayload(draft),
      });
      applySettings(data);
      ui.notify('Ajustes del agente guardados');
    } catch (e) {
      error = messageOf(e, 'No se pudieron guardar los ajustes');
    } finally {
      busy = false;
    }
  }
</script>

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if ready}
  <div class="stack">
    <section class="block" aria-labelledby="agent-kill-switch">
      <h3 id="agent-kill-switch" class="section-title">Interruptor general</h3>
      <div class="switch-row">
        <div>
          <span class="strong">{draft.enabled ? 'Agente activado' : 'Mantenimiento'}</span>
          <p class="muted small">
            {draft.enabled
              ? 'Las conversaciones usan el agente.'
              : 'Las peticiones nuevas se rechazan (503). Los runs que ya están en marcha terminan.'}
          </p>
        </div>
        <Switch
          checked={draft.enabled}
          label="Agente activado"
          onchange={(value) => (draft.enabled = value)}
        />
      </div>
      {#if !draft.enabled}
        <p class="notice" role="status">
          El agente está en mantenimiento. Guarda los ajustes para que el cambio llegue a la app.
        </p>
      {/if}
    </section>

    <section class="block" aria-labelledby="agent-starters">
      <div class="block-head">
        <h3 id="agent-starters" class="section-title">Preguntas de arranque</h3>
      </div>
      <p class="muted small">
        Aparecen en la pantalla vacía de cada modo. Si una lista está vacía, la app usa sus
        preguntas por defecto. Recomendado: tres por modo e idioma.
      </p>

      <div class="picker-row">
        <div class="segmented" role="group" aria-label="Modo">
          {#each AGENT_MODES as mode (mode)}
            <button
              type="button"
              class="seg {starterMode === mode ? 'active' : ''}"
              aria-pressed={starterMode === mode}
              onclick={() => (starterMode = mode)}
            >
              {AGENT_MODE_META[mode].label}
            </button>
          {/each}
        </div>
        <div class="segmented" role="group" aria-label="Idioma">
          {#each STARTER_LOCALES as locale (locale.code)}
            <button
              type="button"
              class="seg {starterLocale === locale.code ? 'active' : ''}"
              aria-pressed={starterLocale === locale.code}
              onclick={() => (starterLocale = locale.code)}
            >
              {locale.label}
            </button>
          {/each}
        </div>
      </div>

      <ul class="rows">
        {#each draft.starters[starterMode][starterLocale] as _starter, index (index)}
          <li class="row">
            <input
              class="input"
              type="text"
              maxlength={STARTER_MAX_CHARS}
              aria-label="Pregunta {index + 1}"
              bind:value={draft.starters[starterMode][starterLocale][index]}
            />
            <button class="btn ghost" type="button" onclick={() => removeStarter(index)}
              >Quitar</button
            >
          </li>
        {:else}
          <li class="muted small">Sin preguntas para este modo e idioma.</li>
        {/each}
      </ul>
      <div>
        <button
          class="btn"
          type="button"
          onclick={addStarter}
          disabled={draft.starters[starterMode][starterLocale].length >= STARTERS_MAX}
        >
          Agregar pregunta
        </button>
      </div>

      <div class="preview" aria-label="Vista previa de la pantalla vacía">
        <span class="muted small">
          Vista previa · pantalla vacía de {AGENT_MODE_META[starterMode].label}
        </span>
        {#if previewStarters.length === 0}
          <p class="muted small">
            Sin preguntas: la app mostrará sus preguntas por defecto para este modo e idioma.
          </p>
        {:else}
          <div class="chips">
            {#each previewStarters as text, index (index)}
              <span class="chip">{text}</span>
            {/each}
          </div>
        {/if}
      </div>
    </section>

    <section class="block" aria-labelledby="agent-replay">
      <h3 id="agent-replay" class="section-title">Modo demo: runs grabados</h3>
      <p class="muted small">
        Preguntas que el modo demo responde con un run ya grabado, por si el agente falla en
        directo. Copia el ID de un run desde la vista Runs.
      </p>

      {#if draft.replay.length === 0}
        <p class="muted small">Sin entradas.</p>
      {:else}
        <ul class="rows">
          {#each draft.replay as entry, index (index)}
            <li class="row wide">
              <label class="field grow">
                <span class="field-label">Pregunta</span>
                <input class="input" type="text" maxlength="500" bind:value={entry.prompt} />
              </label>
              <label class="field">
                <span class="field-label">ID del run</span>
                <input
                  class="input mono"
                  type="text"
                  spellcheck="false"
                  placeholder="00000000-0000-0000-0000-000000000000"
                  bind:value={entry.run_id}
                />
              </label>
              <button class="btn ghost" type="button" onclick={() => removeReplay(index)}
                >Quitar</button
              >
            </li>
          {/each}
        </ul>
      {/if}
      <div>
        <button
          class="btn"
          type="button"
          onclick={addReplay}
          disabled={draft.replay.length >= REPLAY_MAX}
        >
          Agregar entrada
        </button>
      </div>
    </section>

    <section class="block" aria-labelledby="agent-quotas">
      <h3 id="agent-quotas" class="section-title">Cuotas por día</h3>
      <p class="muted small">
        Vacío significa sin límite. Las cuotas se reinician a medianoche UTC. Al pasarse, el agente
        responde con quota_exceeded.
      </p>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Rol</th>
              <th>Runs por día</th>
              <th>Tokens por día</th>
            </tr>
          </thead>
          <tbody>
            {#each USER_ROLES as role (role)}
              <tr>
                <td class="strong">{ROLE_LABELS[role]}</td>
                <td>
                  <input
                    class="input quota-input tabular-nums"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="Sin límite"
                    aria-label="Runs por día: {ROLE_LABELS[role]}"
                    bind:value={draft.quotas[role].runs_per_day}
                  />
                </td>
                <td>
                  <input
                    class="input quota-input tabular-nums"
                    type="number"
                    min="0"
                    step="1"
                    placeholder="Sin límite"
                    aria-label="Tokens por día: {ROLE_LABELS[role]}"
                    bind:value={draft.quotas[role].tokens_per_day}
                  />
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    <div class="savebar">
      {#if error}
        <p class="error-text" role="alert">{error}</p>
      {:else if dirty}
        <p class="muted small">Hay cambios sin guardar.</p>
      {/if}
      <button class="btn ghost" type="button" onclick={discard} disabled={!dirty || busy}>
        Descartar cambios
      </button>
      <button class="btn primary" type="button" onclick={requestSave} disabled={!dirty || busy}>
        {busy ? 'Guardando…' : 'Guardar ajustes'}
      </button>
    </div>
  </div>
{/if}

<ConfirmDialog
  open={confirmOff}
  title="Activar mantenimiento"
  confirmLabel="Pasar a mantenimiento"
  danger
  {busy}
  onconfirm={persist}
  oncancel={() => (confirmOff = false)}
>
  Las peticiones nuevas al agente se rechazarán hasta que vuelvas a activarlo. Los runs que ya están
  en marcha terminan.
</ConfirmDialog>

<style>
  .stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .block {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
  }

  .block-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .block .section-title {
    margin: 0;
  }

  .small {
    font-size: 13px;
  }

  .switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }

  .switch-row p {
    margin: 2px 0 0;
  }

  .picker-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }

  .segmented {
    display: inline-flex;
    padding: 3px;
    border: 1px solid var(--p-line);
    border-radius: 10px;
    background: var(--p-surf-2);
  }

  .seg {
    padding: 5px 12px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--p-mut);
    font: inherit;
    font-size: 13.5px;
    cursor: pointer;
  }

  .seg.active {
    background: var(--p-hi);
    color: var(--p-ink);
    font-weight: 600;
  }

  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .row.wide {
    align-items: flex-end;
  }

  .row .input {
    flex: 1;
  }

  .grow {
    flex: 1;
    min-width: 0;
  }

  .preview {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
    border: 1px dashed var(--p-line-2);
    border-radius: 12px;
    background: var(--p-surf-2);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .chip {
    padding: 8px 14px;
    border: 1px solid var(--p-line-2);
    border-radius: 999px;
    background: var(--p-surf);
    font-size: 13.5px;
  }

  .quota-input {
    width: 180px;
  }

  .notice {
    margin: 0;
  }

  .savebar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 8px;
  }

  .savebar .error-text,
  .savebar .small {
    margin-right: auto;
  }
</style>
