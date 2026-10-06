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
    d="M12 3.5a8.5 8.5 0 1 0 0 17c1 0 1.7-.8 1.7-1.7 0-.45-.17-.86-.46-1.16-.29-.3-.46-.71-.46-1.16 0-.9.76-1.66 1.7-1.66H16a4 4 0 0 0 4-4c0-4.4-3.6-7.32-8-7.32Z"
  />
  <circle cx="7.5" cy="12" r="1.1" fill="currentColor" stroke="none" />
  <circle cx="9.5" cy="8" r="1.1" fill="currentColor" stroke="none" />
  <circle cx="14.5" cy="7.5" r="1.1" fill="currentColor" stroke="none" />
</svg>
