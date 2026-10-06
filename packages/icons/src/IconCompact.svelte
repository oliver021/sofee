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
  <polyline points="4 9 9 9 9 4" />
  <polyline points="20 9 15 9 15 4" />
  <polyline points="4 15 9 15 9 20" />
  <polyline points="20 15 15 15 15 20" />
</svg>
