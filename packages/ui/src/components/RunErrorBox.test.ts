import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import type { RunErrorCode, Translate } from '@sofee/core';
import RunErrorBox from './RunErrorBox.svelte';

const t: Translate = (path, params) =>
  params?.time !== undefined ? `${path}|${String(params.time)}` : path;

function html(props: Record<string, unknown>): string {
  return render(RunErrorBox, { props: { t, ...props } })
    .body.replace(/<!--[\s\S]*?-->/g, '')
    .replace(/ class="svelte-[a-z0-9]+"/g, '')
    .replace(/ svelte-[a-z0-9]+/g, '');
}

const retry = () => undefined;
const changeModel = () => undefined;

describe('RunErrorBox', () => {
  it('offers Change model and Retry when the model is unavailable', () => {
    const out = html({
      code: 'model_unavailable' satisfies RunErrorCode,
      onRetry: retry,
      onChangeModel: changeModel,
    });
    expect(out).toContain('thread.errors.modelUnavailable.title');
    expect(out).toContain('thread.changeModel');
    expect(out).toContain('thread.retry');
  });

  it('retries a provider or timeout error without offering a model change', () => {
    for (const code of ['provider_error', 'rate_limited', 'timeout', 'internal'] as const) {
      const out = html({ code, onRetry: retry, onChangeModel: changeModel });
      expect(out).toContain('thread.retry');
      expect(out).not.toContain('thread.changeModel');
    }
  });

  it('states when a spent quota resets and offers no action', () => {
    const out = html({ code: 'quota_exceeded', resetLabel: '01:00', onRetry: retry });
    expect(out).toContain('thread.errors.quotaExceeded.title');
    expect(out).toContain('thread.errors.quotaExceeded.body|01:00');
    expect(out).not.toContain('thread.retry');
  });

  it('offers no action when the assistant is switched off', () => {
    const out = html({ code: 'agent_disabled', onRetry: retry, onChangeModel: changeModel });
    expect(out).toContain('thread.errors.agentDisabled.title');
    expect(out).not.toContain('<button');
  });

  it('falls back to the generic copy and Retry without a code', () => {
    const out = html({ onRetry: retry });
    expect(out).toContain('thread.errorTitle');
    expect(out).toContain('thread.errorBody');
    expect(out).toContain('thread.retry');
  });
});
