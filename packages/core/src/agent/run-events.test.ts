import { describe, expect, it } from 'vitest';
import {
  RUN_EVENT_TYPES,
  decodeRunEvent,
  isActiveRunStatus,
  isRunEventType,
  isTerminalRunEvent,
  toRunEvent,
  type RunEvent,
} from './run-events.js';

describe('RUN_EVENT_TYPES', () => {
  it('lists every SSE event name exactly once', () => {
    expect(new Set(RUN_EVENT_TYPES).size).toBe(RUN_EVENT_TYPES.length);
    expect(RUN_EVENT_TYPES).toHaveLength(17);
  });
});

describe('decodeRunEvent', () => {
  it('decodes a known frame into a typed event', () => {
    const event = decodeRunEvent('message.delta', '{"text":"hola "}');
    expect(event).toEqual({ type: 'message.delta', payload: { text: 'hola ' } });
  });

  it('ignores event names this build does not know', () => {
    expect(decodeRunEvent('future.event', '{"x":1}')).toBeNull();
  });

  it('rejects data that is not a JSON object', () => {
    expect(decodeRunEvent('status', 'not json')).toBeNull();
    expect(decodeRunEvent('status', 'null')).toBeNull();
    expect(decodeRunEvent('status', '"text"')).toBeNull();
  });
});

describe('toRunEvent', () => {
  it('pairs a stored event name and payload, as the run listing returns them', () => {
    expect(
      toRunEvent('usage', { input_tokens: 3, output_tokens: 4, context_percent: null }),
    ).toEqual({
      type: 'usage',
      payload: { input_tokens: 3, output_tokens: 4, context_percent: null },
    });
  });

  it('returns null for unknown names and non-object payloads', () => {
    expect(toRunEvent('nope', {})).toBeNull();
    expect(toRunEvent('status', 'x')).toBeNull();
  });
});

describe('terminal and active helpers', () => {
  it('treats completed, failed and cancelled as the only terminal events', () => {
    const terminal: RunEvent[] = [
      { type: 'run.completed', payload: { assistant_message_id: 'm', text: '', citations: [] } },
      { type: 'run.failed', payload: { error_code: 'internal', message: '', retryable: true } },
      { type: 'run.cancelled', payload: { assistant_message_id: 'm', text: '' } },
    ];
    for (const event of terminal) expect(isTerminalRunEvent(event)).toBe(true);
    expect(
      isTerminalRunEvent({
        type: 'interrupt',
        payload: { interrupt_id: 'i', kind: 'plan_review', todos: [] },
      }),
    ).toBe(false);
  });

  it('counts queued, running and interrupted runs as active', () => {
    expect(isActiveRunStatus('queued')).toBe(true);
    expect(isActiveRunStatus('running')).toBe(true);
    expect(isActiveRunStatus('interrupted')).toBe(true);
    expect(isActiveRunStatus('completed')).toBe(false);
    expect(isActiveRunStatus('failed')).toBe(false);
    expect(isActiveRunStatus('cancelled')).toBe(false);
  });

  it('recognises event names', () => {
    expect(isRunEventType('ui.quiz')).toBe(true);
    expect(isRunEventType('ui.unknown')).toBe(false);
  });
});
