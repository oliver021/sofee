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
  <path d="M12 3.5 19 7.5v9L12 20.5 5 16.5v-9Z" />
  <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
</svg>
