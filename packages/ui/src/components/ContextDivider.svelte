<!--
  roadmap U16 and ux-foundations.md §4: Compact and Clear leave a thin mark in the thread, so the
  reader can see where the model stopped remembering. The line is decorative; the label carries the
  meaning.
-->
<script lang="ts">
  interface Props {
    label: string;
  }

  let { label }: Props = $props();
</script>

<p class="context-divider">
  <span class="line" aria-hidden="true"></span>
  <span class="label">{label}</span>
  <span class="line" aria-hidden="true"></span>
</p>

<style>
  .context-divider {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin: var(--space-4) 0;
    color: var(--p-mut);
    font-size: 12px;
    letter-spacing: 0.02em;
  }

  .line {
    flex: 1;
    height: 1px;
    background: var(--p-line-2);
  }

  .label {
    flex: none;
    max-width: 100%;
    text-align: center;
  }
</style>
