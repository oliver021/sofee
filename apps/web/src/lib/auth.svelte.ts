/**
 * Session state for apps/web. Mirrors apps/admin's AuthState, but exposes an explicit `status`
 * so the shell can tell "still checking `/me`" apart from "signed out" without flashing the
 * sign-in screen on every reload.
 */
import { api, onUnauthorized, setCsrfToken } from './api.js';

export type AuthStatus = 'bootstrapping' | 'signedOut' | 'signedIn';

export interface AuthUser {
  readonly id: string;
  readonly email: string;
  readonly display_name: string;
  readonly role: 'regular' | 'admin';
}

interface LoginResponse {
  user: AuthUser;
  csrf_token: string;
}

class AuthState {
  status = $state<AuthStatus>('bootstrapping');
  user = $state<AuthUser | null>(null);

  constructor() {
    onUnauthorized(() => this.markSignedOut());
  }

  get isSignedIn(): boolean {
    return this.status === 'signedIn' && this.user !== null;
  }

  markSignedOut(): void {
    this.user = null;
    this.status = 'signedOut';
    setCsrfToken(null);
  }

  async bootstrap(): Promise<void> {
    try {
      const user = await api<AuthUser>('/me');
      const { token } = await api<{ token: string }>('/auth/csrf');
      this.user = user;
      setCsrfToken(token);
      this.status = 'signedIn';
    } catch {
      this.markSignedOut();
    }
  }

  async login(email: string, password: string): Promise<void> {
    const data = await api<LoginResponse>('/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    this.#adopt(data);
  }

  async register(email: string, password: string, displayName: string): Promise<void> {
    const data = await api<LoginResponse>('/auth/register', {
      method: 'POST',
      body: { email, password, display_name: displayName },
    });
    this.#adopt(data);
  }

  async logout(): Promise<void> {
    try {
      await api<void>('/auth/logout', { method: 'POST' });
    } finally {
      this.markSignedOut();
    }
  }

  #adopt(data: LoginResponse): void {
    this.user = data.user;
    setCsrfToken(data.csrf_token);
    this.status = 'signedIn';
  }
}

export const auth = new AuthState();
