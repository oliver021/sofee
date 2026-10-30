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
  <path d="M12 4.5v10" />
  <polyline points="7.5 10.5 12 15 16.5 10.5" />
  <path d="M5 18.5h14" />
</svg>
