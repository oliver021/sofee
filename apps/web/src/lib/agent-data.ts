/**
 * The agent's REST surface that is not the run protocol (run-client.ts): the admin's starting
 * questions, the files a thread's agent wrote under /notes/, and the thumbs rating. Mutations go
 * through `api()`, so CSRF and the 401 handling match every other route.
 */
import type { ComposerMode } from '@sofee/core';
import { api } from './api.js';

export interface StarterRow {
  readonly text: string;
}

/** One file from `GET /threads/{id}/files`. `path` is the agent's virtual path, e.g. /notes/a.md. */
export interface AgentFileRow {
  readonly path: string;
  readonly size: number;
  readonly updated_at: string;
}

export interface AgentFileContent {
  readonly path: string;
  readonly content: string;
}

function encode(id: string): string {
  return encodeURIComponent(id);
}

/** The admin's starting questions for a mode. An empty list means the client uses its own copy. */
export function fetchStarters(mode: ComposerMode, locale: string): Promise<StarterRow[]> {
  const query = `mode=${encodeURIComponent(mode)}&locale=${encodeURIComponent(locale)}`;
  return api<StarterRow[]>(`/starters?${query}`);
}

export function listAgentFiles(threadId: string): Promise<AgentFileRow[]> {
  return api<AgentFileRow[]>(`/threads/${encode(threadId)}/files`);
}

export function readAgentFile(threadId: string, path: string): Promise<AgentFileContent> {
  return api<AgentFileContent>(
    `/threads/${encode(threadId)}/files/content?path=${encodeURIComponent(path)}`,
  );
}

/** Rates a reply. `value: null` clears the rating. Only the value is sent (roadmap U15-lite). */
export function putFeedback(
  threadId: string,
  messageId: string,
  value: 'good' | 'bad' | null,
): Promise<void> {
  return api<void>(`/threads/${encode(threadId)}/messages/${encode(messageId)}/feedback`, {
    method: 'PUT',
    body: { value, reason: null, comment: null },
  });
}
