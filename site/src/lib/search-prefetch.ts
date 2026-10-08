let asked = false

/** Warms the browser cache with the search index (a prerendered file) when someone reaches for search, so the first query does not wait for a download. Once per page load. */
export function prefetchSearchIndex() {
  if (asked || typeof fetch === 'undefined') return
  asked = true
  fetch('/api/search', { priority: 'low' } as RequestInit).catch(() => { asked = false })
}
