// Turns persisted run events into timeline rows. The payloads follow the Sofee event contract
// (apps/api/app/agent/events.py); anything unexpected degrades to plain text instead of throwing.
import { formatMs } from '../../lib/format.js';
import type { RunEvent } from '../../lib/types.js';

export type TimelineTone = 'neutral' | 'ok' | 'warn' | 'error';

export interface TimelineEntry {
  seq: number;
  tone: TimelineTone;
  kind: string;
  title: string;
  detail: string | null;
  lines: string[];
}

const TODO_STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente',
  in_progress: 'En curso',
  completed: 'Hecho',
};

const SOURCE_KIND_LABELS: Record<string, string> = {
  web: 'Web',
  kb: 'Base de conocimiento',
  attachment: 'Adjunto',
};

function text(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
}

function count(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function records(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is Record<string, unknown> => typeof item === 'object' && item !== null,
  );
}

function agentName(agent: string): string {
  return agent === '' || agent === 'main' ? 'agente principal' : `subagente ${agent}`;
}

function todoLines(items: Record<string, unknown>[]): string[] {
  return items.map((item) => {
    const status = text(item.status);
    return `${TODO_STATUS_LABELS[status] ?? status}: ${text(item.content)}`;
  });
}

export function describeEvent(event: RunEvent): TimelineEntry {
  const p = event.payload;
  const make = (
    tone: TimelineTone,
    kind: string,
    title: string,
    detail: string | null = null,
    lines: string[] = [],
  ): TimelineEntry => ({ seq: event.seq, tone, kind, title, detail, lines });

  switch (event.type) {
    case 'run.started':
      return make(
        'neutral',
        'Inicio',
        `Run iniciado · modo ${text(p.mode) || '—'}`,
        text(p.model_label) || null,
      );

    case 'status':
      return make('neutral', 'Estado', text(p.text) || 'Actualización de estado');

    case 'message.delta': {
      const chunks = count(p.chunks);
      return make(
        'neutral',
        'Respuesta',
        chunks === null ? 'Texto de la respuesta' : `Texto de la respuesta (${chunks} fragmentos)`,
      );
    }

    case 'todos.updated': {
      const items = records(p.items);
      return make('neutral', 'Plan', `Plan de ${items.length} pasos`, null, todoLines(items));
    }

    case 'tool.started':
      return make(
        'neutral',
        'Herramienta',
        `${text(p.name) || 'herramienta'} · ${agentName(text(p.agent))}`,
        text(p.args_preview) || null,
      );

    case 'tool.finished': {
      const failed = text(p.status) === 'error';
      const duration = count(p.duration_ms);
      const timing = duration === null ? '' : ` · ${formatMs(duration)}`;
      return make(
        failed ? 'error' : 'ok',
        'Herramienta',
        `${text(p.name) || 'herramienta'} · ${failed ? 'con error' : 'correcta'}${timing}`,
        text(p.result_preview) || null,
      );
    }

    case 'subagent.started':
      return make(
        'neutral',
        'Subagente',
        `${text(p.name) || 'subagente'} empieza`,
        text(p.task) || null,
      );

    case 'subagent.finished': {
      const failed = text(p.status) === 'error';
      return make(
        failed ? 'error' : 'ok',
        'Subagente',
        `${text(p.name) || 'subagente'} · ${failed ? 'con error' : 'terminó'}`,
        text(p.summary) || null,
      );
    }

    case 'source.added': {
      const kind = SOURCE_KIND_LABELS[text(p.kind)] ?? text(p.kind);
      const where = text(p.url) || text(p.ref);
      return make(
        'neutral',
        'Fuente',
        `[${text(p.index)}] ${text(p.title) || 'Sin título'}`,
        where ? `${kind} · ${where}` : kind,
      );
    }

    case 'file.written': {
      const size = count(p.size);
      return make(
        'neutral',
        'Archivo',
        `Escrito ${text(p.path) || 'archivo'}`,
        size === null ? null : `${size} bytes`,
      );
    }

    case 'ui.directions': {
      const items = records(p.items);
      return make(
        'neutral',
        'Direcciones',
        `${items.length} direcciones propuestas`,
        null,
        items.map((item) => text(item.title)).filter((title) => title.length > 0),
      );
    }

    case 'ui.quiz': {
      const items = records(p.items);
      return make(
        'neutral',
        'Comprobación',
        `${items.length} preguntas de comprensión`,
        null,
        items.map((item) => text(item.question)).filter((question) => question.length > 0),
      );
    }

    case 'interrupt':
      return make(
        'warn',
        'Revisión',
        'Plan pendiente de revisión',
        'El run espera a que la persona apruebe, edite o rechace el plan.',
        todoLines(records(p.todos)),
      );

    case 'usage': {
      const pct = count(p.context_percent);
      return make(
        'neutral',
        'Consumo',
        `${text(p.input_tokens) || '0'} tokens de entrada · ${text(p.output_tokens) || '0'} de salida`,
        pct === null ? null : `Contexto usado: ${Math.round(pct)} %`,
      );
    }

    case 'run.completed': {
      const citations = Array.isArray(p.citations) ? p.citations.length : 0;
      return make('ok', 'Final', `Completado · ${citations} citas`);
    }

    case 'run.failed': {
      const retry = p.retryable === true ? ' · se puede reintentar' : '';
      return make(
        'error',
        'Error',
        text(p.error_code) || 'error',
        `${text(p.message) || 'Sin detalle'}${retry}`,
      );
    }

    case 'run.cancelled':
      return make('warn', 'Cancelado', 'Run cancelado', 'Se guardó el texto que llegó a verse.');

    default:
      return make('neutral', 'Evento', event.type);
  }
}
