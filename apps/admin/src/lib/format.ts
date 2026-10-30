// Display helpers shared by the admin views. All copy is Spanish, like the rest of the admin.

const numberFormat = new Intl.NumberFormat('es');

export function formatDateTime(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' });
}

export function formatInt(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : numberFormat.format(value);
}

export function formatMs(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

export function formatPercent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '—';
  return `${(rate * 100).toFixed(1)} %`;
}

// Costs are estimates in the catalog's price unit; four decimals keep small runs visible.
export function formatCost(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(4);
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toFixed(2);
}

// Rough token count from characters, the same rule of thumb the roadmap asks for (chars / 4).
export function approxTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

export function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}

// Only http(s) links leave the admin as anchors: model output and trace URLs are untrusted.
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}

export function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

// Values from an HTML <input type="datetime-local"> to an ISO string the API accepts.
export function localToIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

// Reads a number from a `type="number"` input: an empty field arrives as null or NaN.
export function numberOrNull(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

const UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export function isUuid(value: string): boolean {
  return UUID_PATTERN.test(value);
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
