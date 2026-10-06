<!--
  Visually-hidden but screen-reader-visible content: the skip link's destination label,
  live-region text, and any "sr-only" caption. Kept as one component so the clipping technique
  lives in exactly one place.
-->
<script lang="ts">
  import type { Snippet } from 'svelte';

  interface Props {
    children: Snippet;
  }

  let { children }: Props = $props();
</script>

<span class="visually-hidden">{@render children()}</span>

<style>
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
</style>
