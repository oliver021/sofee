import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import type { Citation, RunDirection, RunQuizItem, Translate } from '@sofee/core';
import ContextDivider from './ContextDivider.svelte';
import CitationRef from './CitationRef.svelte';
import DirectionChips from './DirectionChips.svelte';
import PlanBlock from './PlanBlock.svelte';
import PlanReview from './PlanReview.svelte';
import QuizBlock from './QuizBlock.svelte';
import SourceList from './SourceList.svelte';
import ThinkingIndicator from './ThinkingIndicator.svelte';
import ToolTimeline from './ToolTimeline.svelte';
import type { PlanView, SourceView, ToolRunView } from '../types.js';

const t: Translate = (path) => path;

/** Strips the comments and scoping classes Svelte adds, as the other component tests here do. */
function clean(body: string): string {
  return body
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/ class="svelte-[a-z0-9]+"/g, '')
    .replace(/ svelte-[a-z0-9]+/g, '');
}

const plan: PlanView = {
  steps: [
    { content: 'Leer la guía', status: 'completed', statusLabel: 'agent.plan.status.completed' },
    { content: 'Comparar', status: 'in_progress', statusLabel: 'agent.plan.status.inProgress' },
  ],
  running: true,
  headline: 'agent.plan.running',
  summary: '',
  liveSources: 'agent.sources.live',
};

describe('PlanBlock', () => {
  it('shows the live checklist with the current headline while the run works', () => {
    const out = clean(render(PlanBlock, { props: { plan, t } }).body);
    expect(out).toContain('agent.plan.running');
    expect(out).toContain('agent.sources.live');
    expect(out).toContain('Leer la guía');
    expect(out).toContain('agent.plan.status.inProgress');
    expect(out).not.toContain('aria-expanded');
  });

  it('folds into one summary line that starts closed once the run has finished', () => {
    const out = clean(
      render(PlanBlock, {
        props: {
          plan: { ...plan, running: false, headline: 'agent.plan.label', summary: 'Resumen' },
          t,
        },
      }).body,
    );
    expect(out).toContain('Resumen');
    expect(out).toContain('aria-expanded="false"');
    expect(out).not.toContain('<ol');
  });
});

describe('PlanReview', () => {
  const steps = [
    { content: 'Leer', status: 'pending' as const, statusLabel: 'x' },
    { content: 'Comparar', status: 'pending' as const, statusLabel: 'x' },
  ];

  it('offers Approve, Edit, Continue without review and Stop while the plan waits', () => {
    const out = clean(
      render(PlanReview, {
        props: {
          steps,
          t,
          onApprove: () => undefined,
          onEdit: () => undefined,
          onSkipReview: () => undefined,
          onStop: () => undefined,
        },
      }).body,
    );
    expect(out).toContain('agent.review.approve');
    expect(out).toContain('agent.review.edit');
    expect(out).toContain('agent.review.skipForThread');
    expect(out).toContain('agent.review.stop');
    expect(out).toContain('Leer');
    expect(out).not.toContain('<input');
  });
});

describe('SourceList', () => {
  const view = (citation: Citation): SourceView => ({
    index: citation.index,
    title: citation.title,
    meta: 'meta',
    snippet: citation.snippet ?? null,
    citation,
  });

  it('links a web source in a new tab and a team document to a button', () => {
    const out = clean(
      render(SourceList, {
        props: {
          sources: [
            view({ index: 1, title: 'Web', url: 'https://example.com/a' }),
            view({ index: 2, title: 'Interno', url: null, kind: 'kb', ref: 'doc-1' }),
          ],
          t,
          onOpen: () => undefined,
        },
      }).body,
    );
    expect(out).toContain('href="https://example.com/a"');
    expect(out).toContain('target="_blank"');
    expect(out).toContain('<button type="button" class="title as-button"');
  });

  it('keeps a team document as plain text when nothing can open it', () => {
    const out = clean(
      render(SourceList, {
        props: {
          sources: [view({ index: 1, title: 'Interno', url: null, kind: 'kb' })],
          t,
        },
      }).body,
    );
    expect(out).not.toContain('<button');
    expect(out).toContain('Interno');
  });
});

describe('CitationRef', () => {
  it('opens a team document from a button instead of a link', () => {
    const out = clean(
      render(CitationRef, {
        props: {
          citation: { index: 3, title: 'Guía', url: null, kind: 'kb', ref: 'doc-9' },
          t,
          onOpen: () => undefined,
        },
      }).body,
    );
    expect(out).toContain('citation-button');
    expect(out).not.toContain('<a ');
  });

  it('keeps a web citation as a link', () => {
    const out = clean(
      render(CitationRef, {
        props: {
          citation: { index: 1, title: 'Web', url: 'https://example.com/x', kind: 'web' },
          t,
        },
      }).body,
    );
    expect(out).toContain('href="https://example.com/x"');
  });
});

describe('DirectionChips and QuizBlock', () => {
  it('renders every direction as a button with its reason', () => {
    const directions: RunDirection[] = [{ title: 'Ver costes', why: 'Para decidir' }];
    const out = clean(
      render(DirectionChips, { props: { directions, t, onPick: () => undefined } }).body,
    );
    expect(out).toContain('Ver costes');
    expect(out).toContain('Para decidir');
    expect(out).toContain('<button type="button" class="chip"');
  });

  it('hides every answer until it is asked for', () => {
    const items: RunQuizItem[] = [{ question: '¿Qué es un deploy?', answer: 'Una publicación' }];
    const out = clean(render(QuizBlock, { props: { items, t } }).body);
    expect(out).toContain('¿Qué es un deploy?');
    expect(out).not.toContain('Una publicación');
    expect(out).toContain('aria-expanded="false"');
  });
});

describe('ThinkingIndicator', () => {
  it('shows the run status text when there is one, and the generic label otherwise', () => {
    expect(
      clean(render(ThinkingIndicator, { props: { t, statusText: 'Leyendo deploy.md…' } }).body),
    ).toContain('Leyendo deploy.md…');
    expect(clean(render(ThinkingIndicator, { props: { t } }).body)).toContain('thread.thinking');
  });
});

describe('ContextDivider', () => {
  it('shows its label between two rules', () => {
    expect(
      clean(render(ContextDivider, { props: { label: 'Contexto limpiado aquí' } }).body),
    ).toContain('Contexto limpiado aquí');
  });
});

describe('ToolTimeline', () => {
  const runs: ToolRunView[] = [
    {
      runId: 'run-1',
      title: 'Pregunta',
      groups: [
        {
          key: 'main',
          label: 'agent.tools.mainAgent',
          main: true,
          rows: [
            {
              id: 't1',
              name: 'Tarea',
              argsPreview: '{}',
              status: 'success',
              statusLabel: 'Éxito',
              durationLabel: '1.2 s',
            },
          ],
        },
        {
          key: 'investigador',
          label: 'agent.subagents.researcher',
          main: false,
          rows: [
            {
              id: 't2',
              name: 'Búsqueda',
              argsPreview: 'q',
              status: 'running',
              statusLabel: 'En curso',
              durationLabel: 'En curso',
            },
          ],
        },
      ],
    },
  ];

  it('lists the main agent open and each subagent under its own collapsible group', () => {
    const out = clean(render(ToolTimeline, { props: { runs } }).body);
    expect(out).toContain('Pregunta');
    expect(out).toContain('agent.tools.mainAgent');
    expect(out).toContain('<details class="group subgroup" open');
    expect(out).toContain('agent.subagents.researcher');
    expect(out).toContain('1.2 s');
  });
});
