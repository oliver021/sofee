<!--
  ux-foundations.md §5 — "Submit: Enter sends, Shift+Enter inserts a newline. Configurable to
  the inverse." Language and palette live in their own More-menu submenus (design-system.md
  keeps every palette behind one contract and this dialog has no reason to duplicate that
  picker), so this dialog only owns the one thing that is genuinely a composer setting.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import Dialog from './Dialog.svelte';

  interface Props {
    t: Translate;
    triggerEl?: HTMLElement | null;
    invertSendKey: boolean;
    /** Enabled provider models for the model picker (M8). Absent/empty hides the fieldset. */
    modelOptions?: { id: string; label: string }[];
    selectedModelId?: string | null;
    onClose: () => void;
    onChangeInvertSendKey: (value: boolean) => void;
    onChangeModel?: (id: string) => void;
  }

  let {
    t,
    triggerEl = null,
    invertSendKey,
    modelOptions = [],
    selectedModelId = null,
    onClose,
    onChangeInvertSendKey,
    onChangeModel = () => {},
  }: Props = $props();
</script>

<Dialog titleText={t('settings.title')} {triggerEl} {onClose}>
  <fieldset class="field">
    <legend>{t('settings.submitLabel')}</legend>
    <label class="option">
      <input
        type="radio"
        name="submit-key"
        checked={!invertSendKey}
        onchange={() => onChangeInvertSendKey(false)}
      />
      {t('settings.enterSends')}
    </label>
    <label class="option">
      <input
        type="radio"
        name="submit-key"
        checked={invertSendKey}
        onchange={() => onChangeInvertSendKey(true)}
      />
      {t('settings.shiftEnterSends')}
    </label>
  </fieldset>

  {#if modelOptions.length > 0}
    <fieldset class="field">
      <legend>{t('settings.modelLabel')}</legend>
      <label class="option">
        <select
          class="select"
          value={selectedModelId ?? ''}
          onchange={(event) => onChangeModel((event.currentTarget as HTMLSelectElement).value)}
        >
          {#each modelOptions as model (model.id)}
            <option value={model.id}>{model.label}</option>
          {/each}
        </select>
      </label>
    </fieldset>
  {/if}
</Dialog>

<style>
  .field {
    border: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  legend {
    padding: 0 0 var(--space-2);
    color: var(--p-mut);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .option {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--p-ink);
    font-size: 14px;
    min-height: var(--target-min);
  }

  input[type='radio'] {
    accent-color: var(--p-acc);
    width: 16px;
    height: 16px;
  }

  .select {
    font: inherit;
    font-size: 14px;
    color: var(--p-ink);
    background: var(--p-surf);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-icon-btn);
    padding: var(--space-2) var(--space-3);
    min-height: var(--target-min);
    width: 100%;
  }

  .select:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }
</style>
