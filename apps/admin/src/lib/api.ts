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
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  // A FormData body (file uploads) goes out as multipart; the browser sets its boundary.
  body?: unknown;
  headers?: Record<string, string>;
}

function buildHeaders(options: ApiOptions): HeadersInit {
  const headers: Record<string, string> = options.headers ?? {};
  if (options.body !== undefined && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }
  if (options.method && options.method !== 'GET' && csrf) {
    headers['X-CSRF-Token'] = csrf;
  }
  return headers;
}

function serializeBody(body: unknown): BodyInit | undefined {
  if (body === undefined) return undefined;
  if (body instanceof FormData) return body;
  return JSON.stringify(body);
}

// FastAPI returns a string `detail` for HTTPException, but a list of {loc, msg} for validation
// errors (422). Flatten the list so the admin shows the reason instead of a bare status code.
function detailMessage(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const parts: string[] = [];
    for (const item of detail) {
      if (typeof item !== 'object' || item === null || !('msg' in item)) continue;
      const msg = typeof item.msg === 'string' ? item.msg : '';
      const loc =
        'loc' in item && Array.isArray(item.loc)
          ? item.loc
              .filter((part: unknown) => typeof part === 'string' && part !== 'body')
              .join('.')
          : '';
      if (msg) parts.push(loc ? `${loc}: ${msg}` : msg);
    }
    if (parts.length > 0) return parts.join(' · ');
  }
  return `Error HTTP ${status}`;
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: options.method ?? 'GET',
    headers: buildHeaders(options),
    body: serializeBody(options.body),
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
    const detail: unknown = await response.json().catch(() => null);
    const message = detailMessage(
      typeof detail === 'object' && detail !== null && 'detail' in detail ? detail.detail : null,
      response.status,
    );
    throw new ApiError(response.status, message);
  }

  // 202 (cancel) and 204 may come with an empty body; only parse when there is one.
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
