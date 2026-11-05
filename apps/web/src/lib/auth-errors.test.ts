import { describe, expect, it } from 'vitest';
import { ApiError } from './api.js';
import { authErrorKey } from './auth-errors.js';

describe('authErrorKey', () => {
  it.each([
    [401, 'auth.errorInvalidCredentials'],
    [409, 'auth.errorEmailTaken'],
    [400, 'auth.errorWeakPassword'],
    [422, 'auth.errorInvalidInput'],
    [429, 'auth.errorTooMany'],
    [502, 'auth.errorNetwork'],
    [504, 'auth.errorNetwork'],
    [500, 'auth.errorGeneric'],
  ])('maps HTTP %i to %s', (status, key) => {
    expect(authErrorKey(new ApiError(status, `HTTP ${status}`))).toBe(key);
  });

  it('says the server cannot be reached when the request never got an answer', () => {
    expect(authErrorKey(new TypeError('Failed to fetch'))).toBe('auth.errorNetwork');
  });

  it('falls back to the generic copy for anything else', () => {
    expect(authErrorKey(new Error('boom'))).toBe('auth.errorGeneric');
  });
});
