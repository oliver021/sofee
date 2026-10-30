<!--
  roadmap U10: the files the agent wrote in this thread (under /notes/), listed in the Attachments
  panel. Opening one shows its text rendered as markdown, with copy and a download as .md. The app
  loads the files and the chosen preview; this component only shows them and reports the actions.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import { IconCopy, IconDownload } from '@sofee/icons';
  import IconButton from './IconButton.svelte';
  import Markdown from './Markdown.svelte';
  import type { AgentFilePreview, AgentFileView } from '../types.js';

  interface Props {
    files: readonly AgentFileView[];
    preview: AgentFilePreview | null;
    t: Translate;
    onOpen: (path: string) => void;
    onBack: () => void;
    onCopy: (content: string) => void;
    onDownload: (name: string, content: string) => void;
  }

  let { files, preview, t, onOpen, onBack, onCopy, onDownload }: Props = $props();
</script>

<section class="agent-files" aria-label={t('agent.files.heading')}>
  {#if preview}
    <div class="preview-head">
      <button type="button" class="back" onclick={onBack}>{t('agent.files.back')}</button>
      <p class="preview-name" title={preview.path}>{preview.name}</p>
      <div class="preview-actions">
        {#if preview.content !== null}
          <IconButton
            icon={IconCopy}
            label={t('agent.files.copy')}
            tooltip={t('agent.files.copy')}
            onclick={() => onCopy(preview.content ?? '')}
          />
          <IconButton
            icon={IconDownload}
            label={t('agent.files.download')}
            tooltip={t('agent.files.download')}
            onclick={() => onDownload(preview.name, preview.content ?? '')}
          />
        {/if}
      </div>
    </div>
    {#if preview.loading}
      <p class="status">{t('agent.files.loading')}</p>
    {:else if preview.error}
      <p class="status error">{t('agent.files.error')}</p>
    {:else if preview.content !== null}
      <div class="preview-body">
        <Markdown text={preview.content} {t} />
      </div>
    {/if}
  {:else}
    <h3 class="heading">{t('agent.files.heading')}</h3>
    {#if files.length === 0}
      <p class="status">{t('agent.files.empty')}</p>
    {:else}
      <ul class="file-list">
        {#each files as file (file.path)}
          <li>
            <button type="button" class="file-row" onclick={() => onOpen(file.path)}>
              <span class="file-name">{file.name}</span>
              <span class="file-size">{file.sizeLabel}</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .agent-files {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .heading {
    margin: 0;
    color: var(--p-mut);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .status {
    margin: 0;
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.6;
  }

  .status.error {
    color: var(--sem-critical);
  }

  .file-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .file-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--target-min);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-icon-btn);
    border: 1px solid var(--p-line);
    background: var(--p-surf);
    color: var(--p-ink);
    font: inherit;
    font-size: 13px;
    text-align: start;
    cursor: pointer;
  }

  .file-row:hover {
    border-color: var(--p-line-2);
  }

  .file-row:focus-visible,
  .back:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .file-name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .file-size {
    flex-shrink: 0;
    color: var(--p-mut);
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    font-size: 11px;
  }

  .preview-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }

  .back {
    min-height: var(--target-min);
    padding: 0 var(--space-2);
    border: none;
    background: none;
    color: var(--p-acc);
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }

  .preview-name {
    flex: 1;
    min-width: 0;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
    color: var(--p-ink);
  }

  .preview-actions {
    display: flex;
    gap: 2px;
  }

  .preview-body {
    min-width: 0;
    font-size: 14px;
    line-height: 1.6;
    color: var(--p-ink);
  }
</style>
