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
    d="M14.5 6.5a3.5 3.5 0 0 0-4.7 4.2L5 15.5V19h3.5l4.8-4.8a3.5 3.5 0 0 0 4.2-4.7l-2.6 2.6-2-2Z"
  />
</svg>
