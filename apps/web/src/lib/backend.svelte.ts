/**
 * Conversation persistence against `/threads` and `/threads/{id}/messages`.
 *
 * Two design points worth stating:
 *  - The client id IS the backend key. The frontend never remaps ids after a save, so a thread
 *    or message created offline keeps its identity once it reaches the server.
 *  - Writes are fire-and-forget and serialised per thread through a promise chain: sending a
 *    message must never block the optimistic UI, but a message must not race the thread's own
 *    creation either. Failures are swallowed — the app stays usable offline and the next write
 *    to that thread simply carries the current state again (every call is an upsert).
 */
import { api } from './api.js';
import type { ChatMessage, Citation, ComposerMode, MessageStatus, Thread } from '@sofee/core';

interface ThreadDto {
  id: string;
  title: string | null;
  mode: ComposerMode;
  message_count: number;
  created_at: string;
  updated_at: string;
  /** Context cut points (roadmap §3.10): Compact's and Clear's sequence numbers. */
  summary_through_seq?: number | null;
  context_start_seq?: number | null;
}

interface MessageDto {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  status: MessageStatus;
  citations: Citation[] | null;
  attachment_ids: string[] | null;
  seq: number;
  created_at: string;
}

interface ThreadDetailDto extends ThreadDto {
  messages: MessageDto[];
}

let active = false;

export function setConversationSync(enabled: boolean): void {
  active = enabled;
}

function titleFor(thread: Thread): string | null {
  if (thread.title) return thread.title;
  const firstUser = thread.messages.find((message) => message.role === 'user');
  return firstUser ? firstUser.text.slice(0, 60) : null;
}

interface ThreadSnapshot {
  id: string;
  title: string | null;
  mode: ComposerMode;
}

function snapshotThread(thread: Thread): ThreadSnapshot {
  return { id: thread.id, title: titleFor(thread), mode: thread.mode };
}

function messageBody(message: ChatMessage) {
  return {
    client_id: message.id,
    role: message.role,
    text: message.text,
    status: message.status,
    citations: message.citations ?? null,
    attachment_ids: message.attachmentIds ?? null,
  };
}

const chains: Record<string, Promise<unknown>> = {};

function enqueue(threadId: string, task: () => Promise<unknown>): void {
  const previous = chains[threadId] ?? Promise.resolve();
  const next = previous.then(task, task).catch(() => undefined);
  chains[threadId] = next;
}

async function putThread(snapshot: ThreadSnapshot): Promise<void> {
  await api('/threads', {
    method: 'POST',
    body: { client_id: snapshot.id, title: snapshot.title, mode: snapshot.mode },
  });
}

function encode(id: string): string {
  return encodeURIComponent(id);
}

export function syncThread(thread: Thread): void {
  if (!active || thread.isTemporary) return;
  const snapshot = snapshotThread(thread);
  enqueue(thread.id, () => putThread(snapshot));
}

export function syncMessage(thread: Thread, message: ChatMessage): void {
  if (!active || thread.isTemporary) return;
  const snapshot = snapshotThread(thread);
  const body = messageBody(message);
  enqueue(thread.id, async () => {
    await putThread(snapshot);
    await api(`/threads/${encode(thread.id)}/messages`, { method: 'POST', body });
  });
}

/** Resolves once every write already queued for the thread has reached the server. An agent run
 * needs its thread to exist there first, so the send waits on this rather than racing the upsert. */
export function threadSettled(threadId: string): Promise<void> {
  return (chains[threadId] ?? Promise.resolve()).then(() => undefined);
}

export function syncMessageRemoved(threadId: string, messageId: string): void {
  if (!active) return;
  enqueue(threadId, () =>
    api(`/threads/${encode(threadId)}/messages/${encode(messageId)}`, { method: 'DELETE' }),
  );
}

export function deleteThreadRemote(threadId: string): void {
  if (!active) return;
  enqueue(threadId, () => api(`/threads/${encode(threadId)}`, { method: 'DELETE' }));
}

function toMessage(dto: MessageDto): ChatMessage {
  return {
    id: dto.id,
    role: dto.role,
    status: dto.status,
    text: dto.text,
    createdAt: Date.parse(dto.created_at) || Date.now(),
    citations: dto.citations ?? undefined,
    attachmentIds: dto.attachment_ids ?? undefined,
    seq: dto.seq,
  };
}

export async function loadConversations(): Promise<Thread[]> {
  const threads = await api<ThreadDto[]>('/threads');
  const details = await Promise.all(
    threads.map((thread) => api<ThreadDetailDto>(`/threads/${encode(thread.id)}`)),
  );
  return details.map((detail) => ({
    id: detail.id,
    title: detail.title ?? '',
    isTemporary: false,
    createdAt: Date.parse(detail.created_at) || Date.now(),
    mode: detail.mode,
    messages: detail.messages.map(toMessage),
    summaryThroughSeq: detail.summary_through_seq ?? null,
    contextStartSeq: detail.context_start_seq ?? null,
  }));
}

/** What the server knows about a thread's sequence numbers right now: each message's seq by its
 * client id, and the two context cut points. Context dividers need these after Compact or Clear,
 * because runs write their replies on the server and the client does not learn their seq otherwise. */
export interface ThreadCutState {
  readonly seqs: Record<string, number>;
  readonly summaryThroughSeq: number | null;
  readonly contextStartSeq: number | null;
}

export async function loadThreadCutState(threadId: string): Promise<ThreadCutState> {
  const detail = await api<ThreadDetailDto>(`/threads/${encode(threadId)}`);
  const seqs: Record<string, number> = {};
  for (const message of detail.messages) seqs[message.id] = message.seq;
  return {
    seqs,
    summaryThroughSeq: detail.summary_through_seq ?? null,
    contextStartSeq: detail.context_start_seq ?? null,
  };
}
