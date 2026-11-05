import { ApiError } from './api.js';

/** The i18n key to show for a failed sign-in or sign-up, so the backend's English `detail` never
 * reaches the user. A request that never got an answer (`fetch` rejects with a TypeError) is a
 * connection problem, not a bad form. */
export type AuthErrorKey =
  | 'auth.errorInvalidCredentials'
  | 'auth.errorEmailTaken'
  | 'auth.errorWeakPassword'
  | 'auth.errorInvalidInput'
  | 'auth.errorTooMany'
  | 'auth.errorNetwork'
  | 'auth.errorGeneric';

export function authErrorKey(error: unknown): AuthErrorKey {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'auth.errorInvalidCredentials';
    if (error.status === 409) return 'auth.errorEmailTaken';
    if (error.status === 400) return 'auth.errorWeakPassword';
    if (error.status === 422) return 'auth.errorInvalidInput';
    if (error.status === 429) return 'auth.errorTooMany';
    if (error.status === 502 || error.status === 504) return 'auth.errorNetwork';
    return 'auth.errorGeneric';
  }
  if (error instanceof TypeError) return 'auth.errorNetwork';
  return 'auth.errorGeneric';
}
