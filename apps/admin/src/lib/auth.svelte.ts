import { api, onUnauthorized, setCsrfToken } from './api';
import type { LoginResponse, User } from './types';

class AuthState {
  user = $state<User | null>(null);
  bootstrapping = $state(true);

  constructor() {
    onUnauthorized(() => {
      this.user = null;
      setCsrfToken(null);
    });
  }

  async bootstrap(): Promise<void> {
    try {
      const user = await api<User>('/me');
      this.user = user;
      const { token } = await api<{ token: string }>('/auth/csrf');
      setCsrfToken(token);
    } catch {
      this.user = null;
      setCsrfToken(null);
    } finally {
      this.bootstrapping = false;
    }
  }

  async login(email: string, password: string): Promise<void> {
    const data = await api<LoginResponse>('/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    this.user = data.user;
    setCsrfToken(data.csrf_token);
  }

  async logout(): Promise<void> {
    try {
      await api<void>('/auth/logout', { method: 'POST' });
    } finally {
      this.user = null;
      setCsrfToken(null);
    }
  }
}

export const auth = new AuthState();
