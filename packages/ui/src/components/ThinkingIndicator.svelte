<!--
  ux-foundations.md §4.3: "Stable height, indefinite (no fake progress bar), cancellable." (Stop
  is available the whole time via the composer's send-becomes-stop slot, §4.1 — no second Stop
  control here.) §3.3: "Reserve space for the thinking indicator so the first token does not
  shift layout. The indicator and the first line of the reply occupy the same height." — the
  `min-height` below matches MessageItem's body line-height exactly for that reason.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';

  interface Props {
    t: Translate;
  }

  let { t }: Props = $props();
</script>

<div class="thinking">
  <span class="dots" aria-hidden="true">
    <span></span><span></span><span></span>
  </span>
  <span class="label">{t('thread.thinking')}</span>
</div>

<style>
  .thinking {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    /* Matches MessageItem's --message-line-height so the first real line lands at the same
       baseline this indicator occupied. */
    min-height: 1.6em;
    color: var(--p-mut);
    font-size: 15px;
  }

  .dots {
    display: inline-flex;
    gap: 4px;
  }

  .dots span {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--p-mut);
    animation: thinking-pulse 1.1s ease-in-out infinite;
  }

  .dots span:nth-child(2) {
    animation-delay: 0.15s;
  }
  .dots span:nth-child(3) {
    animation-delay: 0.3s;
  }

  @keyframes thinking-pulse {
    0%,
    80%,
    100% {
      opacity: 0.3;
    }
    40% {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .dots span {
      animation: none;
      opacity: 0.7;
    }
  }
</style>
