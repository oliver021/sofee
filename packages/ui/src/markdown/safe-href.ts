/**
 * Link destinations that may become `href`s. Model output and citation URLs are untrusted, so
 * only absolute web and mail links pass; `javascript:`, `data:`, relative paths and anything
 * unparseable come back null and render as plain text instead of a link.
 */
const ALLOWED_PROTOCOLS: ReadonlySet<string> = new Set(['http:', 'https:', 'mailto:']);

export function safeHref(href: string | null | undefined): string | null {
  if (!href) return null;
  try {
    const url = new URL(href.trim());
    return ALLOWED_PROTOCOLS.has(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}
