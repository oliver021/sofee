// Builds a query string for the admin API. Empty values are skipped, so callers can pass
// optional filters straight through.
export function toQuery(
  params: Record<string, string | number | boolean | null | undefined>,
): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  }
  return parts.length > 0 ? `?${parts.join('&')}` : '';
}
