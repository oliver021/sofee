/**
 * Where the shared scroll container must be for a thread with no messages. Every thread draws in
 * the same container, so a new chat opened after a long one inherits its scroll offset and the
 * empty state (greeting and starter questions) ends up above the visible area. An empty thread
 * always reads from the top. Returns the offset to apply, or null when nothing needs to move.
 */
export function emptyThreadScrollTop(itemCount: number, currentScrollTop: number): number | null {
  return itemCount === 0 && currentScrollTop !== 0 ? 0 : null;
}
