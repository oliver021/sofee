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
  <path d="M7 11v9" />
  <path
    d="M7 11l3-6a2 2 0 0 1 2 2v3h4.5a2 2 0 0 1 1.9 2.7l-1.6 4.6a2 2 0 0 1-1.9 1.3H9a2 2 0 0 1-2-2Z"
  />
</svg>
