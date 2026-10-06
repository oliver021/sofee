<!--
  ux-foundations.md §3.4 — floats above the composer while free and more than one viewport from
  the bottom; carries a count when messages arrived while away.
-->
<script lang="ts">
  import type { Translate } from '@sofee/core';
  import { IconArrowDown } from '@sofee/icons';

  interface Props {
    count: number;
    t: Translate;
    onClick: () => void;
  }

  let { count, t, onClick }: Props = $props();
</script>

<button type="button" class="jump-to-latest" onclick={onClick}>
  <IconArrowDown size={16} />
  <span>{count > 0 ? t('thread.jumpToLatestCount', { count }) : t('thread.jumpToLatest')}</span>
</button>

<style>
  .jump-to-latest {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-capsule);
    border: 1px solid var(--p-line);
    background: var(--p-surf-2);
    color: var(--p-ink);
    box-shadow: var(--p-shadow-menu);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
    animation: jump-in var(--motion-jump-duration) var(--motion-jump-easing);
  }

  .jump-to-latest:hover {
    border-color: var(--p-line-2);
  }

  .jump-to-latest:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  @keyframes jump-in {
    from {
      opacity: 0;
      translate: 0 6px;
    }
    to {
      opacity: 1;
      translate: 0 0;
    }
  }
</style>
