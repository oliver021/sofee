<script lang="ts">
  import { onMount } from 'svelte';
  import { IconSearch, IconTrash } from '@sofee/icons';
  import ConfirmDialog from '../../components/ConfirmDialog.svelte';
  import Drawer from '../../components/Drawer.svelte';
  import Switch from '../../components/Switch.svelte';
  import { api } from '../../lib/api.js';
  import { formatBytes, formatInt, messageOf } from '../../lib/format.js';
  import { ui } from '../../lib/ui.svelte.js';
  import type { KbDocument, KbRejectedFile, KbUploadResult } from '../../lib/types.js';
  import DocumentPanel from './DocumentPanel.svelte';

  // Same list the backend accepts (SUPPORTED_EXTENSIONS in services/extraction.py).
  const ACCEPT = '.md,.txt,.pdf';

  const REJECT_LABELS: Record<string, string> = {
    unsupported_type: 'Tipo de archivo no admitido (usa md, txt o pdf)',
    too_large: 'Supera el tamaño máximo por archivo',
    extraction_failed: 'No se pudo leer el texto del archivo',
  };

  let documents = $state<KbDocument[]>([]);
  let loading = $state(true);
  let loadError = $state<string | null>(null);
  let query = $state('');
  let searchTimeout = 0;
  let uploading = $state(false);
  let dragOver = $state(false);
  let rejected = $state<KbRejectedFile[]>([]);
  let busyId = $state<string | null>(null);
  let selected = $state<KbDocument | null>(null);
  let deleting = $state<KbDocument | null>(null);
  let deleteBusy = $state(false);

  async function load() {
    loading = true;
    loadError = null;
    try {
      const params = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
      documents = await api<KbDocument[]>(`/admin/kb${params}`);
    } catch (e) {
      loadError = messageOf(e, 'No se pudo cargar la base de conocimiento');
    } finally {
      loading = false;
    }
  }

  onMount(load);

  function onSearchInput() {
    window.clearTimeout(searchTimeout);
    searchTimeout = window.setTimeout(load, 300);
  }

  async function upload(files: File[]) {
    if (files.length === 0) return;
    uploading = true;
    rejected = [];
    try {
      const form = new FormData();
      for (const file of files) form.append('files', file);
      const result = await api<KbUploadResult>('/admin/kb', { method: 'POST', body: form });
      rejected = result.rejected;
      const added = result.documents.length;
      if (added > 0) {
        ui.notify(added === 1 ? '1 documento agregado' : `${added} documentos agregados`);
      }
      if (result.rejected.length > 0) {
        ui.notify(`${result.rejected.length} archivo(s) no se agregaron`, 'error');
      }
      await load();
    } catch (e) {
      ui.notify(messageOf(e, 'No se pudieron subir los archivos'), 'error');
    } finally {
      uploading = false;
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    dragOver = false;
    const files = event.dataTransfer?.files;
    if (files) void upload(Array.from(files));
  }

  function onPick(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const files = input.files ? Array.from(input.files) : [];
    // Clearing the input lets the same file be picked again after a fix.
    input.value = '';
    void upload(files);
  }

  async function toggleEnabled(doc: KbDocument, isEnabled: boolean) {
    const previous = doc.is_enabled;
    doc.is_enabled = isEnabled;
    busyId = doc.id;
    try {
      await api(`/admin/kb/${doc.id}`, { method: 'PATCH', body: { is_enabled: isEnabled } });
      ui.notify(isEnabled ? `${doc.title} activo para el agente` : `${doc.title} retirado`);
    } catch (e) {
      doc.is_enabled = previous;
      ui.notify(messageOf(e, 'No se pudo cambiar el estado'), 'error');
    } finally {
      busyId = null;
    }
  }

  function handleChanged(updated: KbDocument) {
    selected = updated;
    documents = documents.map((doc) => (doc.id === updated.id ? { ...doc, ...updated } : doc));
  }

  async function confirmDelete() {
    if (!deleting) return;
    deleteBusy = true;
    try {
      await api(`/admin/kb/${deleting.id}`, { method: 'DELETE' });
      ui.notify('Documento eliminado');
      if (selected?.id === deleting.id) selected = null;
      await load();
    } catch (e) {
      ui.notify(messageOf(e, 'No se pudo eliminar el documento'), 'error');
    } finally {
      deleteBusy = false;
      deleting = null;
    }
  }
</script>

<div class="view-head">
  <div>
    <h1>Conocimiento</h1>
    <p class="muted intro">
      Documentos del equipo que el agente puede leer y citar. Lo que ves en "Lo que lee el agente"
      es exactamente el texto que usa.
    </p>
  </div>
  <div class="search">
    <IconSearch size={15} />
    <input
      class="input"
      type="search"
      placeholder="Buscar por título…"
      bind:value={query}
      oninput={onSearchInput}
      aria-label="Buscar documentos"
    />
  </div>
</div>

<div
  class="dropzone {dragOver ? 'over' : ''}"
  role="region"
  aria-label="Subir documentos"
  ondragover={(event) => {
    event.preventDefault();
    dragOver = true;
  }}
  ondragleave={() => (dragOver = false)}
  ondrop={onDrop}
>
  <div>
    <p class="strong">Arrastra aquí los documentos del equipo</p>
    <p class="muted small">
      Markdown, texto o PDF con texto (no escaneados). Varios archivos a la vez. Hasta 25 MB por
      archivo.
    </p>
  </div>
  <label class="btn primary pick">
    {uploading ? 'Subiendo…' : 'Elegir archivos'}
    <input
      class="sr-only"
      type="file"
      multiple
      accept={ACCEPT}
      disabled={uploading}
      onchange={onPick}
    />
  </label>
</div>

{#if rejected.length > 0}
  <div class="notice box" role="status">
    <div class="box-head">
      <p class="strong">Estos archivos no se agregaron</p>
      <button class="btn ghost small-btn" type="button" onclick={() => (rejected = [])}
        >Cerrar</button
      >
    </div>
    <ul class="reject-list">
      {#each rejected as item, index (index)}
        <li>
          <span class="mono">{item.filename}</span> · {REJECT_LABELS[item.reason] ?? item.reason}
        </li>
      {/each}
    </ul>
  </div>
{/if}

{#if loading}
  <p class="muted">Cargando…</p>
{:else if loadError}
  <p class="error-text" role="alert">{loadError}</p>
{:else if documents.length === 0}
  <div class="empty">
    <p>
      {query.trim()
        ? 'Sin resultados para esa búsqueda.'
        : 'Todavía no hay documentos en la base de conocimiento.'}
    </p>
  </div>
{:else}
  <div class="table-wrap">
    <table class="table">
      <thead>
        <tr>
          <th>Título</th>
          <th>Archivo</th>
          <th>Tamaño</th>
          <th>Extracción</th>
          <th>Etiquetas</th>
          <th>Estado</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each documents as doc (doc.id)}
          <tr class={doc.is_enabled ? '' : 'row-off'}>
            <td>
              <button class="title-btn" type="button" onclick={() => (selected = doc)}>
                {doc.title}
              </button>
            </td>
            <td class="mono muted">{doc.source_filename}</td>
            <td class="tabular-nums muted">{formatBytes(doc.size_bytes)}</td>
            <td>
              {#if doc.text_chars > 0}
                <span class="badge ok tabular-nums">{formatInt(doc.text_chars)} caracteres</span>
              {:else}
                <span class="badge warn">Sin texto</span>
              {/if}
            </td>
            <td>
              {#if doc.tags.length === 0}
                <span class="muted small">—</span>
              {:else}
                {#each doc.tags as tag (tag)}
                  <span class="tag">{tag}</span>
                {/each}
              {/if}
            </td>
            <td>
              <div class="status-cell">
                <Switch
                  checked={doc.is_enabled}
                  disabled={busyId === doc.id}
                  label="{doc.is_enabled ? 'Retirar' : 'Activar'} {doc.title}"
                  onchange={(value) => toggleEnabled(doc, value)}
                />
                <span class="muted small">{doc.is_enabled ? 'Activo' : 'Retirado'}</span>
              </div>
            </td>
            <td>
              <div class="row-actions">
                <button
                  class="icon-btn"
                  type="button"
                  onclick={() => (deleting = doc)}
                  aria-label="Eliminar {doc.title}"
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
{/if}

<Drawer open={selected !== null} title={selected?.title ?? ''} onclose={() => (selected = null)}>
  {#if selected}
    {#key selected.id}
      <DocumentPanel
        doc={selected}
        onchange={handleChanged}
        ondelete={() => (deleting = selected)}
      />
    {/key}
  {/if}
</Drawer>

<ConfirmDialog
  open={deleting !== null}
  title="Eliminar documento"
  confirmLabel="Eliminar"
  danger
  busy={deleteBusy}
  onconfirm={confirmDelete}
  oncancel={() => (deleting = null)}
>
  ¿Eliminar "{deleting?.title}"? Se borra el documento y su copia del agente. Esta acción no se
  puede deshacer.
</ConfirmDialog>

<style>
  .view-head h1 {
    margin: 0;
  }

  .intro {
    margin: 4px 0 0;
    font-size: 13.5px;
    max-width: 640px;
  }

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

  .dropzone {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 16px;
    padding: 18px 20px;
    border: 1.5px dashed var(--p-line-2);
    border-radius: 12px;
    background: var(--p-surf);
  }

  .dropzone.over {
    border-color: var(--p-acc);
    background: color-mix(in oklab, var(--p-acc) 8%, var(--p-surf));
  }

  .dropzone p {
    margin: 0;
  }

  .small {
    font-size: 13px;
  }

  .pick {
    cursor: pointer;
  }

  .box {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
  }

  .box-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .box p {
    margin: 0;
  }

  .small-btn {
    padding: 4px 10px;
    font-size: 13px;
  }

  .reject-list {
    margin: 0;
    padding-left: 18px;
    font-size: 13.5px;
  }

  .title-btn {
    padding: 0;
    border: none;
    background: none;
    color: var(--p-ink);
    font: inherit;
    font-weight: 600;
    text-align: left;
    cursor: pointer;
  }

  .title-btn:hover {
    color: var(--p-acc);
    text-decoration: underline;
  }

  .tag {
    display: inline-block;
    margin: 0 4px 2px 0;
    padding: 1px 8px;
    border: 1px solid var(--p-line-2);
    border-radius: 999px;
    font-size: 12px;
    color: var(--p-mut);
  }

  .status-cell {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .row-off {
    opacity: 0.6;
  }

  .row-actions .icon-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--p-mut);
    cursor: pointer;
  }

  .row-actions .icon-btn:hover {
    background: var(--p-hi);
    color: var(--p-ink);
  }
</style>
