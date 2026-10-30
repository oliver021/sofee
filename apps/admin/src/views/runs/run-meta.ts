import type { AgentRunStatus } from '../../lib/types.js';

export const RUN_STATUS_LABELS: Record<AgentRunStatus, string> = {
  queued: 'En cola',
  running: 'En marcha',
  interrupted: 'Esperando revisión',
  completed: 'Completado',
  failed: 'Fallido',
  cancelled: 'Cancelado',
};

// Badge flavour per status: failures stand out, the rest stay quiet.
export const RUN_STATUS_TONE: Record<AgentRunStatus, 'ok' | 'off' | 'danger' | 'warn'> = {
  queued: 'off',
  running: 'off',
  interrupted: 'warn',
  completed: 'ok',
  failed: 'danger',
  cancelled: 'off',
};

// Runs that still own a task on the server; only these can be cancelled.
export const ACTIVE_RUN_STATUSES: AgentRunStatus[] = ['queued', 'running', 'interrupted'];

export const RUN_MODE_LABELS: Record<string, string> = {
  learn: 'Aprender',
  research: 'Investigar',
  explore: 'Explorar',
};

export const RUN_ERROR_LABELS: Record<string, string> = {
  model_unavailable: 'Ningún modelo disponible',
  provider_error: 'Error del proveedor',
  rate_limited: 'Límite de frecuencia del proveedor',
  quota_exceeded: 'Cuota agotada',
  agent_disabled: 'Agente en mantenimiento',
  timeout: 'Tiempo agotado',
  internal: 'Error interno',
};
