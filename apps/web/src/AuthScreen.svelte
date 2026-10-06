<!--
  The sign-in / sign-up gate for apps/web (M8). Presentational in the sense that all the
  network work lives in lib/auth.svelte.ts; this component only owns the form state and maps
  HTTP statuses to translated copy so the backend's English `detail` never reaches the user.
-->
<script lang="ts">
  import { ApiError } from './lib/api.js';
  import { auth } from './lib/auth.svelte.js';
  import { t } from './lib/i18n.svelte.js';

  type Mode = 'signIn' | 'register';

  let mode = $state<Mode>('signIn');
  let email = $state('');
  let password = $state('');
  let displayName = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);

  function messageFor(err: unknown): string {
    if (err instanceof ApiError) {
      if (err.status === 401) return t('auth.errorInvalidCredentials');
      if (err.status === 409) return t('auth.errorEmailTaken');
      if (err.status === 400) return t('auth.errorWeakPassword');
      if (err.status === 429) return t('auth.errorTooMany');
    }
    return t('auth.errorGeneric');
  }

  function switchMode(next: Mode): void {
    mode = next;
    error = null;
  }

  async function onSubmit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (busy) return;
    busy = true;
    error = null;
    try {
      if (mode === 'signIn') {
        await auth.login(email, password);
      } else {
        await auth.register(email, password, displayName);
      }
    } catch (err) {
      error = messageFor(err);
    } finally {
      busy = false;
    }
  }
</script>

<main class="auth">
  <div class="card">
    <p class="wordmark">{t('app.wordmark')}</p>
    <h1 class="title">
      {mode === 'signIn' ? t('auth.signInTitle') : t('auth.registerTitle')}
    </h1>
    <p class="subtitle">
      {mode === 'signIn' ? t('auth.signInSubtitle') : t('auth.registerSubtitle')}
    </p>

    <form class="form" onsubmit={onSubmit}>
      {#if mode === 'register'}
        <label class="field">
          <span class="label">{t('auth.displayNameLabel')}</span>
          <input
            class="input"
            type="text"
            autocomplete="name"
            maxlength="120"
            required
            bind:value={displayName}
          />
        </label>
      {/if}
      <label class="field">
        <span class="label">{t('auth.emailLabel')}</span>
        <input class="input" type="email" autocomplete="email" required bind:value={email} />
      </label>
      <label class="field">
        <span class="label">{t('auth.passwordLabel')}</span>
        <input
          class="input"
          type="password"
          autocomplete={mode === 'signIn' ? 'current-password' : 'new-password'}
          minlength="8"
          required
          bind:value={password}
        />
      </label>
      {#if mode === 'register'}
        <p class="hint">{t('auth.passwordHint')}</p>
      {/if}

      {#if error}
        <p class="error" role="alert">{error}</p>
      {/if}

      <button type="submit" class="submit" disabled={busy}>
        {#if busy}
          {mode === 'signIn' ? t('auth.signingIn') : t('auth.registering')}
        {:else}
          {mode === 'signIn' ? t('auth.signIn') : t('auth.register')}
        {/if}
      </button>
    </form>

    <button
      type="button"
      class="switch"
      onclick={() => switchMode(mode === 'signIn' ? 'register' : 'signIn')}
    >
      {mode === 'signIn' ? t('auth.toRegister') : t('auth.toSignIn')}
    </button>
  </div>
</main>

<style>
  .auth {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-4);
  }

  .card {
    width: min(100%, 380px);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-5);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-panel);
    background: var(--p-surf);
  }

  .wordmark {
    margin: 0;
    font-size: 13px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--p-acc);
  }

  .title {
    margin: 0;
    font-size: 22px;
    font-weight: 600;
    color: var(--p-ink);
  }

  .subtitle {
    margin: 0;
    color: var(--p-mut);
    font-size: 13px;
    line-height: 1.6;
  }

  .form {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin-block-start: var(--space-3);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .label {
    color: var(--p-mut);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
  }

  .input {
    font: inherit;
    font-size: 14px;
    color: var(--p-ink);
    background: var(--p-bg);
    border: 1px solid var(--p-line);
    border-radius: var(--radius-icon-btn);
    padding: var(--space-2) var(--space-3);
    min-height: var(--target-min);
  }

  .input:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .hint {
    margin: 0;
    color: var(--p-mut);
    font-size: 12px;
  }

  .error {
    margin: 0;
    color: var(--sem-critical);
    font-size: 13px;
    line-height: 1.5;
  }

  .submit {
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    color: var(--p-send-ink);
    background: var(--p-acc);
    border: 1px solid var(--p-acc);
    border-radius: var(--radius-icon-btn);
    min-height: var(--target-min);
    cursor: pointer;
  }

  .submit:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .submit:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }

  .switch {
    font: inherit;
    font-size: 13px;
    color: var(--p-mut);
    background: none;
    border: none;
    padding: var(--space-2);
    cursor: pointer;
    text-decoration: underline;
  }

  .switch:focus-visible {
    outline: 2px solid var(--p-acc);
    outline-offset: 2px;
  }
</style>
