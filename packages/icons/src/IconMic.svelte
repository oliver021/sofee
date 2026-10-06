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
  <rect x="9" y="3.5" width="6" height="11" rx="3" />
  <path d="M6 11.5a6 6 0 0 0 12 0" />
  <line x1="12" y1="17.5" x2="12" y2="20.5" />
  <line x1="9" y1="20.5" x2="15" y2="20.5" />
</svg>
