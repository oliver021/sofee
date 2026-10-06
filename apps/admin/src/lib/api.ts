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
    // Expired/revoked session → drop the UI back to the login screen. The login endpoint
    // itself returns 401 for bad credentials and must not trigger this reset.
    if (path !== '/auth/login') {
      unauthorizedHandler?.();
    }
    throw new ApiError(401, 'Sesión no válida');
  }

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message =
      typeof detail?.detail === 'string' ? detail.detail : `Error HTTP ${response.status}`;
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
