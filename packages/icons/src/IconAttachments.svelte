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
  <path
    d="M17 7.5 9.5 15a2.5 2.5 0 1 0 3.5 3.5L20 11.5a4.5 4.5 0 1 0-6.5-6.5L6 12.5a1 1 0 0 0 1.4 1.4L15 6.3"
  />
</svg>
