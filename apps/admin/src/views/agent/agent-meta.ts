// Labels and limits for the agent admin. The limits mirror the API schemas
// (apps/api/app/schemas/agent_admin.py) so the editor can say what is wrong before a save.
import type { AgentMode, AgentToolName, UserRole } from '../../lib/types.js';

export const AGENT_MODES: AgentMode[] = ['learn', 'research', 'explore'];

export const AGENT_MODE_META: Record<AgentMode, { label: string; hint: string }> = {
  learn: {
    label: 'Aprender',
    hint: 'Explica un concepto paso a paso, con ejemplos y una comprobación de comprensión.',
  },
  research: {
    label: 'Investigar',
    hint: 'Planifica, delega búsquedas en subagentes y redacta un informe con citas.',
  },
  explore: {
    label: 'Explorar',
    hint: 'Responde en pocas líneas y propone direcciones para seguir preguntando.',
  },
};

export const AGENT_TOOLS: AgentToolName[] = [
  'search_team_docs',
  'web_search',
  'suggest_directions',
  'check_understanding',
];

export const AGENT_TOOL_META: Record<AgentToolName, string> = {
  search_team_docs: 'Buscar en la base de conocimiento del equipo',
  web_search: 'Buscar en la web (necesita la clave de Tavily)',
  suggest_directions: 'Proponer direcciones para seguir explorando',
  check_understanding: 'Preguntas para comprobar la comprensión',
};

export const PROMPT_MAX_CHARS = 20_000;
export const SUBAGENTS_MAX = 5;
export const SUBAGENT_TOOLS_MAX = 10;
export const SUBAGENT_NAME_PATTERN = /^[a-z][a-z0-9_-]{1,39}$/;
export const SUBAGENT_DESCRIPTION_MAX = 500;

export const LIMIT_FIELDS: {
  key: 'max_steps' | 'max_seconds' | 'max_subagents' | 'max_searches';
  label: string;
  min: number;
  max: number;
  hint: string;
}[] = [
  {
    key: 'max_steps',
    label: 'Pasos máximos',
    min: 1,
    max: 200,
    hint: 'Llamadas al modelo por run.',
  },
  {
    key: 'max_seconds',
    label: 'Segundos máximos',
    min: 10,
    max: 3600,
    hint: 'Tiempo total del run.',
  },
  {
    key: 'max_subagents',
    label: 'Subagentes máximos',
    min: 0,
    max: 5,
    hint: 'Delegaciones por run.',
  },
  {
    key: 'max_searches',
    label: 'Búsquedas máximas',
    min: 0,
    max: 50,
    hint: 'Entre documentos y web.',
  },
];

// Locales the starters are written in (the apps/web i18n ships these two).
export const STARTER_LOCALES = [
  { code: 'es', label: 'Español' },
  { code: 'en', label: 'English' },
] as const;

export const USER_ROLES: UserRole[] = ['admin', 'regular'];

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Administradores',
  regular: 'Usuarios regulares',
};
