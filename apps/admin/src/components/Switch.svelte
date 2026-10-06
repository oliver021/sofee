<script lang="ts">
  interface Props {
    checked: boolean;
    disabled?: boolean;
    label: string;
    onchange: (checked: boolean) => void;
  }

  let { checked, disabled = false, label, onchange }: Props = $props();
</script>

<button
  class="switch {checked ? 'on' : ''}"
  type="button"
  role="switch"
  aria-checked={checked}
  aria-label={label}
  {disabled}
  onclick={() => onchange(!checked)}
>
  <span class="thumb"></span>
</button>

<style>
  .switch {
    position: relative;
    width: 38px;
    height: 22px;
    border: 1px solid var(--p-line-2);
    border-radius: 999px;
    background: var(--p-surf-2);
    cursor: pointer;
    padding: 0;
    flex: none;
  }

  .switch:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .switch.on {
    border-color: var(--p-acc);
    background: var(--p-acc);
  }

  .thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 999px;
    background: var(--p-bg);
    transition: transform 140ms ease;
  }

  .switch.on .thumb {
    transform: translateX(16px);
  }
</style>
