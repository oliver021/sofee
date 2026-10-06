<!--
  design-system.md §6: "Badge: top-right, tabular numerals, hidden at zero."
  Purely decorative (the accessible count lives in the button's aria-label via a plural
  message) so it is aria-hidden here.
-->
<script lang="ts">
  interface Props {
    count: number;
  }

  let { count }: Props = $props();
</script>

{#if count > 0}
  <span class="badge" aria-hidden="true">{count > 99 ? '99+' : count}</span>
{/if}

<style>
  .badge {
    position: absolute;
    top: 2px;
    right: 2px;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: var(--radius-capsule);
    background: var(--p-acc);
    color: var(--p-bg);
    font-size: 10px;
    line-height: 16px;
    text-align: center;
    font-variant-numeric: tabular-nums;
    font-family: 'IBM Plex Mono', ui-monospace, monospace;
    pointer-events: none;
  }
</style>
