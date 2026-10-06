/**
 * The one place apps/web talks to the backend. Same-origin in every environment: in dev Vite
 * proxies `/api` to the local API (see vite.config.ts), in production FastAPI serves this app
 * from `/` alongside the API (see apps/api/app/main.py), so session cookies are first-party and
 * no CORS dance is needed.
 */
let csrf: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrf = token;
}

export function getCsrfToken(): string | null {
  return csrf;
}

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function onUnauthorized(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface ApiOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
}

function buildHeaders(options: ApiOptions): HeadersInit {
  const headers: Record<string, string> = options.headers ?? {};
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (options.method && options.method !== 'GET' && csrf) {
    headers['X-CSRF-Token'] = csrf;
  }
  return headers;
}

async function parseError(response: Response): Promise<ApiError> {
  const detail = await response.json().catch(() => null);
  const message = typeof detail?.detail === 'string' ? detail.detail : `HTTP ${response.status}`;
  return new ApiError(response.status, message);
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const body =
    options.body === undefined ? undefined : (JSON.stringify(options.body) as BodyInit | undefined);
  const response = await fetch(`/api/v1${path}`, {
    method: options.method ?? 'GET',
    headers: buildHeaders(options),
    body,
    credentials: 'same-origin',
  });

  if (response.status === 401) {
    // Expired/revoked session → drop the UI back to the sign-in screen. The sign-in and sign-up
    // endpoints use 401/others for bad input and must not trigger this reset.
    if (path !== '/auth/login' && path !== '/auth/register') {
      unauthorizedHandler?.();
    }
    throw await parseError(response);
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

interface StorageObject {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

/** Multipart upload to `/storage`; returns the storage object id used to reference the file in
 * a persisted message. Content-Type is deliberately left unset so the browser adds the boundary. */
export async function uploadFile(file: File): Promise<string> {
  const form = new FormData();
  form.append('file', file, file.name);
  const headers: Record<string, string> = {};
  if (csrf) headers['X-CSRF-Token'] = csrf;
  const response = await fetch('/api/v1/storage', {
    method: 'POST',
    headers,
    body: form,
    credentials: 'same-origin',
  });
  if (response.status === 401) {
    unauthorizedHandler?.();
    throw await parseError(response);
  }
  if (!response.ok) {
    throw await parseError(response);
  }
  const object = (await response.json()) as StorageObject;
  return object.id;
}
