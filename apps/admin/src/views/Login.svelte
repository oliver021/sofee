<script lang="ts">
  import { auth } from '../lib/auth.svelte.js';

  let email = $state('');
  let password = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      await auth.login(email, password);
    } catch (e) {
      error = e instanceof Error ? e.message : 'No se pudo iniciar sesión';
    } finally {
      busy = false;
    }
  }
</script>

<div class="login">
  <form class="card" onsubmit={submit}>
    <h1 class="brand">Sofee Admin</h1>
    <p class="subtitle">Acceso al panel de administración</p>

    <label class="field">
      <span class="field-label">Correo</span>
      <input
        class="input"
        type="email"
        autocomplete="username"
        autocapitalize="none"
        spellcheck="false"
        bind:value={email}
        required
      />
    </label>

    <label class="field">
      <span class="field-label">Contraseña</span>
      <input
        class="input"
        type="password"
        autocomplete="current-password"
        bind:value={password}
        required
      />
    </label>

    {#if error}
      <p class="error-text" role="alert">{error}</p>
    {/if}

    <button class="btn primary submit" type="submit" disabled={busy}>
      {busy ? 'Entrando…' : 'Entrar'}
    </button>
  </form>
</div>

<style>
  .login {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }

  .card {
    width: min(380px, 100%);
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 28px;
    border: 1px solid var(--p-line);
    border-radius: 14px;
    background: var(--p-surf);
    box-shadow: var(--p-shadow-panel);
  }

  .brand {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
  }

  .subtitle {
    margin: -8px 0 4px;
    color: var(--p-mut);
    font-size: 13px;
  }

  .submit {
    margin-top: 4px;
  }
</style>
