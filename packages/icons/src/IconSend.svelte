<script lang="ts">
  import type { IconProps } from './types.js';

  let { size = 20 }: IconProps = $props();
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="1.6"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
  focusable="false"
>
  <line x1="12" y1="19" x2="12" y2="6" />
  <polyline points="6 11 12 5 18 11" />
</svg>
