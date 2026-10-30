<!--
  A fenced code block: the language as a label, a copy button, and the code itself in its own
  scroll box so a long line never widens the page (the page never scrolls sideways). The code is
  a text node, never HTML, so whatever the model wrote stays exactly as text.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import { IconCopy } from '@sofee/icons';

  interface Props {
    code: string;
    lang: string | null;
    t: Translate;
  }

  let { code, lang, t }: Props = $props();

  const COPIED_FEEDBACK_MS = 1500;
  let copied = $state(false);
  let feedbackTimer: ReturnType<typeof setTimeout> | null = null;

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      // Clipboard permission can be denied; there is no useful fallback in the thread.
      return;
    }
    copied = true;
    if (feedbackTimer !== null) clearTimeout(feedbackTimer);
    feedbackTimer = setTimeout(() => {
      copied = false;
      feedbackTimer = null;
    }, COPIED_FEEDBACK_MS);
  }

  $effect(() => () => {
    if (feedbackTimer !== null) clearTimeout(feedbackTimer);
  });
</script>

<div class="code-block">
  <div class="code-head">
    <span class="code-lang">{lang ?? t('message.codeBlock')}</span>
    <button
      type="button"
      class="copy-btn"
      aria-label={copied ? t('message.copied') : t('message.copy')}
      title={copied ? t('message.copied') : t('message.copy')}
      onclick={copy}
    >
      <IconCopy size={14} />
      <span>{copied ? t('message.copied') : t('message.copy')}</span>
    </button>
  </div>
  <pre class="code-body"><code>{code}</code></pre>
</div>

<style>
  .code-block {
    min-width: 0;
    max-width: 100%;
    margin: 0 0 var(--space-3);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-panel);
    background: var(--p-surf-2);
    overflow: hidden;
  }

  .code-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-3);
    border-bottom: 1px solid var(--p-line);
    color: var(--p-mut);
    font-size: 12px;
  }

  .code-lang {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    letter-spacing: 0.02em;
  }

  .copy-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    min-height: var(--target-min);
    padding: 0 var(--space-2);
    border: 1px solid transparent;
    border-radius: var(--radius-icon-btn);
    background: transparent;
    color: var(--p-mut);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }

  .copy-btn:hover {
    color: var(--p-ink);
    border-color: var(--p-line);
  }

  .copy-btn:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .code-body {
    margin: 0;
    padding: var(--space-3);
    overflow-x: auto;
    color: var(--p-ink);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px;
    line-height: 1.55;
    white-space: pre;
  }
</style>
