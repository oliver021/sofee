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
  <circle cx="12" cy="12" r="8.5" />
  <polyline points="8.5 11 12 14.5 15.5 11" />
  <line x1="12" y1="8" x2="12" y2="14.5" />
</svg>
