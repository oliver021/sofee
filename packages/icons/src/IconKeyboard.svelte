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
  <rect x="3" y="6.5" width="18" height="12" rx="2" />
  <rect x="6" y="10" width="2" height="2" rx="0.5" fill="currentColor" stroke="none" />
  <rect x="11" y="10" width="2" height="2" rx="0.5" fill="currentColor" stroke="none" />
  <rect x="16" y="10" width="2" height="2" rx="0.5" fill="currentColor" stroke="none" />
  <rect x="7" y="14.5" width="10" height="2" rx="1" fill="currentColor" stroke="none" />
</svg>
