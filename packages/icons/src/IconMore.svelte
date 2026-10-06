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
  <circle cx="12" cy="6" r="1.3" fill="currentColor" stroke="none" />
  <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none" />
  <circle cx="12" cy="18" r="1.3" fill="currentColor" stroke="none" />
</svg>
