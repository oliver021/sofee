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
  <path d="M9.5 6.5H6A1.5 1.5 0 0 0 4.5 8v10A1.5 1.5 0 0 0 6 19.5h10a1.5 1.5 0 0 0 1.5-1.5v-3.5" />
  <path d="M13.5 4.5H19.5V10.5" />
  <line x1="10.5" y1="13.5" x2="19" y2="5" />
</svg>
