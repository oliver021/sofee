<script lang="ts">
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import { approxTokens, formatDateTime, messageOf } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type {
    AgentLimits,
    AgentProfile,
    AgentProfileVersion,
    AgentSubagentConfig,
    AgentToolName,
  } from '../../lib/types.js';
  import ProfileHistory from './ProfileHistory.svelte';
  import {
    AGENT_MODE_META,
    AGENT_TOOLS,
    AGENT_TOOL_META,
    LIMIT_FIELDS,
    PROMPT_MAX_CHARS,
    SUBAGENTS_MAX,
    SUBAGENT_DESCRIPTION_MAX,
    SUBAGENT_NAME_PATTERN,
    SUBAGENT_TOOLS_MAX,
  } from './agent-meta.js';

  interface Props {
    profile: AgentProfile;
    onchange: (profile: AgentProfile) => void;
  }

  let { profile, onchange }: Props = $props();

  interface Draft {
    prompt: string;
    tools: AgentToolName[];
    planning: boolean;
    planReview: boolean;
    subagents: AgentSubagentConfig[];
    limits: AgentLimits;
  }

  function draftFrom(version: AgentProfileVersion): Draft {
    return {
      prompt: version.system_prompt,
      tools: [...version.config.tools],
      planning: version.config.planning,
      planReview: version.config.plan_review,
      subagents: version.config.subagents.map((sub) => ({ ...sub, tools: [...sub.tools] })),
      limits: { ...version.config.limits },
    };
  }

  // The parent re-creates this editor (`{#key}`) whenever the active version changes, so the
  // draft always starts from what the server has saved.
  // svelte-ignore state_referenced_locally
  let draft = $state<Draft>(draftFrom(profile.active));
  let busy = $state(false);
  let error = $state<string | null>(null);

  let baseline = $derived(JSON.stringify(draftFrom(profile.active)));
  let dirty = $derived(JSON.stringify(draft) !== baseline);
  let problem = $derived(validate(draft));
  let tokens = $derived(approxTokens(draft.prompt));

  let meta = $derived(AGENT_MODE_META[profile.mode]);
  let versionDate = $derived(formatDateTime(profile.active.created_at));

  function validate(d: Draft): string | null {
    const prompt = d.prompt.trim();
    if (prompt.length === 0) return 'El prompt de sistema no puede estar vacío.';
    if (prompt.length > PROMPT_MAX_CHARS) return `El prompt supera ${PROMPT_MAX_CHARS} caracteres.`;
    if (d.subagents.length > SUBAGENTS_MAX) return `Como máximo ${SUBAGENTS_MAX} subagentes.`;

    const names: string[] = [];
    for (const sub of d.subagents) {
      const name = sub.name.trim();
      if (!SUBAGENT_NAME_PATTERN.test(name)) {
        return `El nombre "${name}" debe tener entre 2 y 40 caracteres: minúsculas, números, guiones o guion bajo, y empezar por letra.`;
      }
      if (names.includes(name)) return `El nombre de subagente "${name}" está repetido.`;
      names.push(name);
      if (
        sub.description.trim().length === 0 ||
        sub.description.trim().length > SUBAGENT_DESCRIPTION_MAX
      ) {
        return `La descripción de "${name}" es obligatoria y tiene como máximo ${SUBAGENT_DESCRIPTION_MAX} caracteres.`;
      }
      const subPrompt = sub.system_prompt.trim();
      if (subPrompt.length === 0 || subPrompt.length > PROMPT_MAX_CHARS) {
        return `El prompt de "${name}" es obligatorio y tiene como máximo ${PROMPT_MAX_CHARS} caracteres.`;
      }
      if (sub.tools.length > SUBAGENT_TOOLS_MAX) return `"${name}" tiene demasiadas herramientas.`;
    }

    for (const field of LIMIT_FIELDS) {
      const value = d.limits[field.key];
      if (!Number.isInteger(value) || value < field.min || value > field.max) {
        return `${field.label} debe ser un número entero entre ${field.min} y ${field.max}.`;
      }
    }
    return null;
  }

  function toggle<T>(list: T[], item: T): T[] {
    return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
  }

  function setPlanning(value: boolean) {
    draft.planning = value;
    // The API rejects plan review without planning, so turning planning off clears it.
    if (!value) draft.planReview = false;
  }

  function addSubagent() {
    if (draft.subagents.length >= SUBAGENTS_MAX) return;
    let index = draft.subagents.length + 1;
    const taken = draft.subagents.map((sub) => sub.name);
    while (taken.includes(`subagente-${index}`)) index++;
    draft.subagents.push({
      name: `subagente-${index}`,
      description: '',
      system_prompt: '',
      tools: [],
      planning: false,
    });
  }

  function removeSubagent(index: number) {
    draft.subagents.splice(index, 1);
  }

  function discard() {
    draft = draftFrom(profile.active);
    error = null;
  }

  function buildConfig() {
    return {
      tools: AGENT_TOOLS.filter((tool) => draft.tools.includes(tool)),
      planning: draft.planning,
      plan_review: draft.planning && draft.planReview,
      subagents: draft.subagents.map((sub) => ({
        name: sub.name.trim(),
        description: sub.description.trim(),
        system_prompt: sub.system_prompt.trim(),
        tools: AGENT_TOOLS.filter((tool) => sub.tools.includes(tool)),
        planning: sub.planning,
      })),
      limits: { ...draft.limits },
    };
  }

  async function save() {
    if (problem) {
      error = problem;
      return;
    }
    busy = true;
    error = null;
    try {
      const updated = await api<AgentProfile>(`/admin/agent/profiles/${profile.mode}`, {
        method: 'POST',
        body: { system_prompt: draft.prompt.trim(), config: buildConfig() },
      });
      ui.notify(`Versión ${updated.active.version ?? ''} guardada y activa`);
      onchange(updated);
    } catch (e) {
      error = messageOf(e, 'No se pudo guardar el perfil');
    } finally {
      busy = false;
    }
  }
</script>

<div class="editor">
  <header class="head">
    <div>
      <h2 class="title">{meta.label}</h2>
      <p class="muted">{meta.hint}</p>
    </div>
    <div class="status">
      {#if profile.active.version === null}
        <span class="badge off">Defaults de código</span>
        <span class="muted small">Todavía no hay versiones guardadas.</span>
      {:else}
        <span class="badge ok">Versión {profile.active.version} activa</span>
        <span class="muted small">
          {profile.active.created_by_email ?? '—'} · {versionDate}
        </span>
      {/if}
      {#if dirty}
        <span class="badge warn">Cambios sin guardar</span>
      {/if}
    </div>
  </header>

  <section class="block" aria-label="Prompt de sistema">
    <div class="block-head">
      <h3 class="section-title">Prompt de sistema</h3>
      <span class="muted small tabular-nums">
        ≈ {tokens} tokens · {draft.prompt.length} / {PROMPT_MAX_CHARS} caracteres
      </span>
    </div>
    <label class="field">
      <span class="sr-only">Prompt de sistema de {meta.label}</span>
      <textarea class="input prompt" rows="22" spellcheck="false" bind:value={draft.prompt}
      ></textarea>
    </label>
  </section>

  <section class="block" aria-label="Herramientas y planificación">
    <fieldset class="fieldset">
      <legend class="section-title">Herramientas</legend>
      <div class="checks">
        {#each AGENT_TOOLS as tool (tool)}
          <label class="check">
            <input
              type="checkbox"
              checked={draft.tools.includes(tool)}
              onchange={() => (draft.tools = toggle(draft.tools, tool))}
            />
            <span>
              <span class="mono">{tool}</span>
              <span class="muted small">· {AGENT_TOOL_META[tool]}</span>
            </span>
          </label>
        {/each}
      </div>
    </fieldset>

    <div class="switch-row">
      <div>
        <span class="strong">Planificar antes de actuar</span>
        <p class="muted small">El agente escribe un plan con write_todos antes de investigar.</p>
      </div>
      <Switch checked={draft.planning} label="Planificar" onchange={setPlanning} />
    </div>

    <div class="switch-row">
      <div>
        <span class="strong">Revisión del plan</span>
        <p class="muted small">
          El run se pausa hasta que la persona aprueba, edita o rechaza el plan. Requiere
          planificación.
        </p>
      </div>
      <Switch
        checked={draft.planning && draft.planReview}
        disabled={!draft.planning}
        label="Revisión del plan"
        onchange={(value) => (draft.planReview = value)}
      />
    </div>
  </section>

  <section class="block" aria-label="Subagentes">
    <div class="block-head">
      <h3 class="section-title">Subagentes ({draft.subagents.length}/{SUBAGENTS_MAX})</h3>
      <button
        class="btn"
        type="button"
        onclick={addSubagent}
        disabled={draft.subagents.length >= SUBAGENTS_MAX}
      >
        Agregar subagente
      </button>
    </div>

    {#if draft.subagents.length === 0}
      <p class="muted small">Este modo no delega en subagentes.</p>
    {/if}

    {#each draft.subagents as _sub, index (index)}
      <div class="subagent">
        <div class="sub-head">
          <label class="field grow">
            <span class="field-label">Nombre</span>
            <input
              class="input mono"
              type="text"
              spellcheck="false"
              bind:value={draft.subagents[index]!.name}
            />
          </label>
          <div class="switch-inline">
            <span class="field-label">Planifica</span>
            <Switch
              checked={draft.subagents[index]?.planning ?? false}
              label="Planifica el subagente {draft.subagents[index]?.name ?? ''}"
              onchange={(value) => {
                const sub = draft.subagents[index];
                if (sub) sub.planning = value;
              }}
            />
          </div>
          <button class="btn ghost" type="button" onclick={() => removeSubagent(index)}>
            Quitar
          </button>
        </div>

        <label class="field">
          <span class="field-label">Descripción (la ve el agente principal)</span>
          <input class="input" type="text" bind:value={draft.subagents[index]!.description} />
        </label>

        <label class="field">
          <span class="field-label">
            Prompt de sistema · ≈ {approxTokens(draft.subagents[index]?.system_prompt ?? '')} tokens
          </span>
          <textarea
            class="input prompt small-prompt"
            rows="8"
            spellcheck="false"
            bind:value={draft.subagents[index]!.system_prompt}></textarea>
        </label>

        <fieldset class="fieldset">
          <legend class="field-label">Herramientas del subagente</legend>
          <div class="checks">
            {#each AGENT_TOOLS as tool (tool)}
              <label class="check">
                <input
                  type="checkbox"
                  checked={draft.subagents[index]?.tools.includes(tool) ?? false}
                  onchange={() => {
                    const sub = draft.subagents[index];
                    if (sub) sub.tools = toggle(sub.tools, tool);
                  }}
                />
                <span class="mono small">{tool}</span>
              </label>
            {/each}
          </div>
        </fieldset>
      </div>
    {/each}
    <p class="hint">
      El modelo de cada subagente es el del modo: elegir un modelo por subagente todavía no está
      disponible.
    </p>
  </section>

  <section class="block" aria-label="Límites">
    <h3 class="section-title">Límites</h3>
    <div class="limits">
      {#each LIMIT_FIELDS as field (field.key)}
        <label class="field">
          <span class="field-label">{field.label}</span>
          <input
            class="input tabular-nums"
            type="number"
            min={field.min}
            max={field.max}
            step="1"
            bind:value={draft.limits[field.key]}
          />
          <span class="hint">{field.hint} ({field.min}–{field.max})</span>
        </label>
      {/each}
    </div>
  </section>

  <div class="actions">
    {#if error}
      <p class="error-text" role="alert">{error}</p>
    {:else if dirty && problem}
      <p class="hint">{problem}</p>
    {/if}
    <button class="btn ghost" type="button" onclick={discard} disabled={!dirty || busy}>
      Descartar cambios
    </button>
    <button
      class="btn primary"
      type="button"
      onclick={save}
      disabled={!dirty || busy || problem !== null}
    >
      {busy ? 'Guardando…' : 'Guardar como nueva versión'}
    </button>
  </div>

  <ProfileHistory {profile} {onchange} />
</div>

<style>
  .editor {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }

  .title {
    margin: 0 0 4px;
    font-size: 18px;
    font-weight: 700;
  }

  .head p {
    margin: 0;
    font-size: 13.5px;
  }

  .status {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .block {
    margin: 0;
    padding: 16px;
    border: 1px solid var(--p-line);
    border-radius: 12px;
    background: var(--p-surf);
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .block-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }

  .block-head .section-title,
  .block > .section-title {
    margin: 0;
  }

  .fieldset {
    margin: 0;
    padding: 0;
    border: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .fieldset legend {
    padding: 0;
    margin-bottom: 4px;
  }

  .prompt {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 13px;
    line-height: 1.55;
    resize: vertical;
    min-height: 320px;
  }

  .small-prompt {
    min-height: 160px;
  }

  .checks {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .check {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    font-size: 14px;
    cursor: pointer;
  }

  .check input {
    margin-top: 3px;
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

  .subagent {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 14px;
    border: 1px solid var(--p-line);
    border-radius: 10px;
    background: var(--p-surf-2);
  }

  .sub-head {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    flex-wrap: wrap;
  }

  .grow {
    flex: 1;
    min-width: 200px;
  }

  .switch-inline {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
  }

  .limits {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 14px;
  }

  .hint {
    margin: 0;
    color: var(--p-mut);
    font-size: 12.5px;
  }

  .small {
    font-size: 13px;
  }

  .actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: 8px;
  }

  .actions .hint,
  .actions .error-text {
    margin-right: auto;
  }
</style>
