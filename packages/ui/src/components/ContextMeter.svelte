<!--
  ux-foundations.md §2.2 / design-system.md §1 — a thin vertical fill pinned to the bottom of
  the context cluster. "It changes colour at 75% (warning) and 90% (critical) using semantic tokens,
  never the palette accent" — below that it is a neutral tone, deliberately not `--p-acc`, so it
  never reads as a themed decoration.
-->
<script lang="ts">
  interface Props {
    percent: number;
    label: string;
    valueText: string;
  }

  let { percent, label, valueText }: Props = $props();

  let clamped = $derived(Math.max(0, Math.min(100, percent)));
  let fillColor = $derived(
    clamped >= 90 ? 'var(--sem-critical)' : clamped >= 75 ? 'var(--sem-warning)' : 'var(--p-mut)',
  );
</script>

<div
  class="meter"
  role="meter"
  aria-valuenow={Math.round(clamped)}
  aria-valuemin={0}
  aria-valuemax={100}
  aria-label="{label}: {valueText}"
>
  <div class="track">
    <div class="fill" style:height="{clamped}%" style:background-color={fillColor}></div>
  </div>
</div>

<style>
  .meter {
    display: flex;
    justify-content: center;
    padding-block: var(--space-3);
  }

  .track {
    position: relative;
    width: 6px;
    height: 96px;
    border-radius: var(--radius-capsule);
    background: var(--p-line);
    overflow: hidden;
    display: flex;
    align-items: flex-end;
  }

  .fill {
    width: 100%;
    border-radius: var(--radius-capsule);
    transition: height var(--motion-menu-duration) var(--motion-menu-easing);
  }
</style>
