<!--
  ux-foundations.md §8 — "Announce Response started and Response complete through a polite live
  region. Never put the streaming text itself in a live region — it re-announces on every token
  and makes the app unusable with a screen reader." This component only ever receives those two
  short status strings; the streaming message text itself must never be passed in here.
-->
<script lang="ts">
  interface Props {
    message: string;
  }

  let { message }: Props = $props();
</script>

<div class="live-region" role="status" aria-live="polite" aria-atomic="true">{message}</div>

<style>
  .live-region {
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
