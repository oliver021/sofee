import { describe, expect, it } from 'vitest';
import type { RunTodo } from './run-events.js';
import {
  contextMarks,
  editedPlan,
  groupByAgent,
  hostnameOf,
  newlyCompletedStep,
  planProgress,
  runSeconds,
} from './run-view.js';

const todo = (content: string, status: RunTodo['status']): RunTodo => ({ content, status });

describe('planProgress', () => {
  it('reports no plan as zero steps', () => {
    expect(planProgress([])).toEqual({ total: 0, completed: 0, current: 0 });
  });

  it('points at the step in progress, not the first open one', () => {
    const plan = [
      todo('a', 'completed'),
      todo('b', 'pending'),
      todo('c', 'in_progress'),
      todo('d', 'pending'),
    ];
    expect(planProgress(plan)).toEqual({ total: 4, completed: 1, current: 3 });
  });

  it('falls back to the first step not completed, then to the total', () => {
    expect(planProgress([todo('a', 'completed'), todo('b', 'pending')]).current).toBe(2);
    expect(planProgress([todo('a', 'completed'), todo('b', 'completed')]).current).toBe(2);
  });
});

describe('newlyCompletedStep', () => {
  it('returns the progress only when the completed count grew', () => {
    const before = [todo('a', 'completed'), todo('b', 'in_progress')];
    const after = [todo('a', 'completed'), todo('b', 'completed')];
    expect(newlyCompletedStep(before, after)).toEqual({ total: 2, completed: 2, current: 2 });
    expect(newlyCompletedStep(after, after)).toBeNull();
  });

  it('treats the first plan as progress when it already has completed steps', () => {
    expect(newlyCompletedStep([], [todo('a', 'completed')])?.completed).toBe(1);
  });
});

describe('groupByAgent', () => {
  it('puts the main agent first and keeps the others in first-seen order', () => {
    const calls = [
      { id: '1', agent: 'investigador' },
      { id: '2', agent: 'main' },
      { id: '3', agent: 'critico' },
      { id: '4', agent: 'investigador' },
      { id: '5', agent: 'main' },
    ];
    const groups = groupByAgent(calls);
    expect(groups.map((group) => group.agent)).toEqual(['main', 'investigador', 'critico']);
    expect(groups[0]?.items.map((call) => call.id)).toEqual(['2', '5']);
    expect(groups[1]?.items.map((call) => call.id)).toEqual(['1', '4']);
  });

  it('gives no groups for no calls, and no main group when the main agent made none', () => {
    expect(groupByAgent([])).toEqual([]);
    expect(groupByAgent([{ agent: 'critico' }]).map((group) => group.agent)).toEqual(['critico']);
  });
});

describe('runSeconds', () => {
  it('rounds the elapsed time to whole seconds', () => {
    expect(runSeconds(1_000, 49_400)).toBe(48);
    expect(runSeconds(1_000, 1_400)).toBe(0);
  });

  it('is unknown until both ends are known', () => {
    expect(runSeconds(null, 5_000)).toBeNull();
    expect(runSeconds(1_000, null)).toBeNull();
  });
});

describe('hostnameOf', () => {
  it('returns the host without a www prefix', () => {
    expect(hostnameOf('https://www.example.com/docs/a?b=1')).toBe('example.com');
    expect(hostnameOf('https://docs.python.org/3/')).toBe('docs.python.org');
  });

  it('returns null for missing or unparseable URLs', () => {
    expect(hostnameOf(null)).toBeNull();
    expect(hostnameOf('')).toBeNull();
    expect(hostnameOf('not a url')).toBeNull();
  });
});

describe('contextMarks', () => {
  const messages = [
    { id: 'm1', seq: 1 },
    { id: 'm2', seq: 2 },
    { id: 'm3', seq: 3 },
    { id: 'm4', seq: 4 },
  ];

  it('places a compaction divider after the last message the summary covers', () => {
    const marks = contextMarks(messages, { summaryThroughSeq: 2 });
    expect(marks['m2']).toEqual({ before: [], after: ['compacted'] });
    expect(marks['m3']).toBeUndefined();
  });

  it('places a clear divider before the first message the model still sees', () => {
    const marks = contextMarks(messages, { contextStartSeq: 3 });
    expect(marks['m3']).toEqual({ before: ['cleared'], after: [] });
  });

  it('places a clear with nothing after it at the end of the thread', () => {
    const marks = contextMarks(messages, { contextStartSeq: 5 });
    expect(marks['m4']).toEqual({ before: [], after: ['cleared'] });
  });

  it('treats a message without a seq as newer than every cut', () => {
    const withNew = [...messages, { id: 'm5' }];
    expect(contextMarks(withNew, { summaryThroughSeq: 4 })['m4']?.after).toEqual(['compacted']);
    expect(contextMarks(withNew, { contextStartSeq: 5 })['m5']?.before).toEqual(['cleared']);
  });

  it('has no marks without cut points', () => {
    expect(contextMarks(messages, {})).toEqual({});
    expect(contextMarks(messages, { summaryThroughSeq: null, contextStartSeq: null })).toEqual({});
  });
});

describe('editedPlan', () => {
  it('trims steps, drops blank ones and marks every step pending', () => {
    expect(editedPlan(['  Leer la guía ', '', '   ', 'Comparar'])).toEqual([
      { content: 'Leer la guía', status: 'pending' },
      { content: 'Comparar', status: 'pending' },
    ]);
  });

  it('returns null when no step is left', () => {
    expect(editedPlan([])).toBeNull();
    expect(editedPlan(['  ', ''])).toBeNull();
  });
});
