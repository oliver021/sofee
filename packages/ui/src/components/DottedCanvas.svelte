<!--
  design-system.md §3 — the two-layer dotted field. Both layers are `position: absolute; inset:
  0`, below content, `pointer-events: none`. Meant to be the first child of a `position:
  relative` canvas container, with real content stacked above it (elevation 0, per §7).

  Every value comes from `--p-*` custom properties generated per palette (design-system.md §1:
  "A literal colour anywhere in a component is a bug") — this component renders identically
  regardless of which palette is active; it just paints whatever that palette's tokens say.
-->
<script lang="ts">
  // No props — purely decorative, driven entirely by the active palette's CSS custom
  // properties. The empty script block is still needed for svelte-check to emit a proper
  // module declaration for this component.
</script>

<div class="dotted-canvas" aria-hidden="true">
  <div class="dots-layer"></div>
  <div class="gradient-layer"></div>
  <div class="scanline-layer"></div>
</div>

<style>
  .dotted-canvas {
    position: absolute;
    inset: 0;
    z-index: 0;
    overflow: hidden;
    pointer-events: none;
  }

  .dots-layer,
  .gradient-layer,
  .scanline-layer {
    position: absolute;
    inset: 0;
  }

  .dots-layer {
    background-image: var(--p-dot);
    background-size: var(--p-dot-size) var(--p-dot-size);
    -webkit-mask-image: var(--p-dot-mask);
    mask-image: var(--p-dot-mask);
  }

  .gradient-layer {
    background-image: var(--p-grad);
    mix-blend-mode: var(--p-blend, normal);
  }

  .scanline-layer {
    background-image: var(--p-scanline, none);
  }
</style>
