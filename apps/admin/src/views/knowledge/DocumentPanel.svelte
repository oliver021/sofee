<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../../lib/api.js';
  import { formatBytes, formatDateTime, formatInt, messageOf } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { KbDocument, KbText } from '../../lib/types.js';

  interface Props {
    doc: KbDocument;
    onchange: (doc: KbDocument) => void;
    ondelete: () => void;
  }

  let { doc, onchange, ondelete }: Props = $props();

  // Mounted with `{#key doc.id}` by the parent, so these start from the selected document.
  // svelte-ignore state_referenced_locally
  let title = $state(doc.title);
  // svelte-ignore state_referenced_locally
  let tagsText = $state(doc.tags.join(', '));
  let saving = $state(false);
  let error = $state<string | null>(null);
  let preview = $state<KbText | null>(null);
  let previewLoading = $state(true);
  let previewError = $state<string | null>(null);

  async function loadPreview() {
    previewLoading = true;
    previewError = null;
    try {
      preview = await api<KbText>(`/admin/kb/${doc.id}/text`);
    } catch (e) {
      previewError = messageOf(e, 'No se pudo cargar el texto extraído');
    } finally {
      previewLoading = false;
    }
  }

  onMount(loadPreview);

  async function save(event: SubmitEvent) {
    event.preventDefault();
    const nextTitle = title.trim();
    if (!nextTitle) {
      error = 'El título no puede estar vacío.';
      return;
    }
    const tags = tagsText
      .split(',')
      .map((tag) => tag.trim())
      .filter((tag) => tag.length > 0);
    saving = true;
    error = null;
    try {
      const updated = await api<KbDocument>(`/admin/kb/${doc.id}`, {
        method: 'PATCH',
        body: { title: nextTitle, tags },
      });
      ui.notify('Documento actualizado');
      onchange(updated);
    } catch (e) {
      error = messageOf(e, 'No se pudo guardar el documento');
    } finally {
      saving = false;
    }
  }
</script>

<div class="stack">
  <dl class="meta">
    <dt>Archivo</dt>
    <dd class="mono">{doc.source_filename}</dd>
    <dt>Ruta para el agente</dt>
    <dd class="mono">{doc.path}</dd>
    <dt>Tamaño</dt>
    <dd>{formatBytes(doc.size_bytes)}</dd>
    <dt>Subido</dt>
    <dd>{formatDateTime(doc.created_at)}</dd>
    <dt>Última edición</dt>
    <dd>{formatDateTime(doc.updated_at)}</dd>
  </dl>

  <form class="block" onsubmit={save}>
    <h3 class="section-title">Título y etiquetas</h3>
    <label class="field">
      <span class="field-label">Título</span>
      <input class="input" type="text" maxlength="200" bind:value={title} required />
    </label>
    <label class="field">
      <span class="field-label">Etiquetas</span>
      <input class="input" type="text" bind:value={tagsText} placeholder="onboarding, producto" />
      <span class="hint">Separadas por comas.</span>
    </label>
    {#if error}
      <p class="error-text" role="alert">{error}</p>
    {/if}
    <div class="actions">
      <button class="btn primary" type="submit" disabled={saving}>
        {saving ? 'Guardando…' : 'Guardar cambios'}
      </button>
    </div>
  </form>

  <section class="block" aria-labelledby="kb-preview-title">
    <div class="block-head">
      <h3 id="kb-preview-title" class="section-title">Lo que lee el agente</h3>
      <span class="muted small tabular-nums">{formatInt(doc.text_chars)} caracteres extraídos</span>
    </div>

    {#if doc.text_chars === 0}
      <p class="notice" role="status">
        Este archivo no tiene texto extraíble (suele ser un PDF escaneado). El agente no puede
        leerlo ni citarlo.
      </p>
    {/if}

    {#if previewLoading}
      <p class="muted small">Cargando texto…</p>
    {:else if previewError}
      <p class="error-text" role="alert">{previewError}</p>
    {:else if preview && preview.text_chars > 0}
      <pre class="pre">{preview.text}</pre>
      {#if preview.truncated}
        <p class="hint">
          Vista previa recortada. El texto completo sigue disponible para el agente.
        </p>
      {/if}
    {/if}
  </section>

  <div class="actions">
    <button class="btn danger" type="button" onclick={ondelete}>Eliminar documento</button>
  </div>
</div>

<style>
  .stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .meta {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 8px 16px;
    margin: 0;
    font-size: 13.5px;
  }

  .meta dt {
    color: var(--p-mut);
  }

  .meta dd {
    margin: 0;
    overflow-wrap: anywhere;
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
    gap: 12px;
    flex-wrap: wrap;
  }

  .block .section-title {
    margin: 0;
  }

  .hint,
  .small {
    margin: 0;
    color: var(--p-mut);
    font-size: 12.5px;
  }

  .small {
    font-size: 13px;
  }

  .notice {
    margin: 0;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
</style>
