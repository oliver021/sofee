import { describe, expect, it } from 'vitest';
import { ApiError } from './api.js';
import { failureInfoOf } from './run-client.js';

describe('failureInfoOf', () => {
  it('keeps the codes the backend names', () => {
    expect(failureInfoOf(new ApiError(503, 'agent_disabled'))).toEqual({ code: 'agent_disabled' });
    expect(failureInfoOf(new ApiError(503, 'model_unavailable'))).toEqual({
      code: 'model_unavailable',
    });
    expect(
      failureInfoOf(new ApiError(429, 'quota_exceeded', { reset_at: '2026-11-06T00:00:00Z' })),
    ).toEqual({ code: 'quota_exceeded', resetAt: '2026-11-06T00:00:00Z' });
  });

  it('tells the person a reply is already running instead of a generic failure', () => {
    expect(failureInfoOf(new ApiError(409, 'run_active'))).toEqual({ code: 'busy' });
  });

  it('reports a request that never got an answer as a connection problem', () => {
    expect(failureInfoOf(new TypeError('Failed to fetch'))).toEqual({ code: 'network' });
    expect(failureInfoOf(new ApiError(502, 'upstream_unreachable'))).toEqual({ code: 'network' });
    expect(failureInfoOf(new ApiError(504, 'HTTP 504'))).toEqual({ code: 'network' });
  });

  it('keeps everything else internal', () => {
    expect(failureInfoOf(new ApiError(500, 'HTTP 500'))).toEqual({ code: 'internal' });
    expect(failureInfoOf(new Error('boom'))).toEqual({ code: 'internal' });
  });
});
