type Item = { type: string; content: unknown }

const text = (c: unknown) => (typeof c === 'string' ? c.replace(/<[^>]*>/g, '') : '').trim().toLowerCase()

/**
 * The index ranks pages by how well any paragraph matches, so a typed “keys” can put a guide that mentions keys above the page called Keys.
 * Results come as groups (a page, then its matching headings and paragraphs): this moves the groups whose PAGE TITLE is the query, or contains it, to the front.
 * Everything else keeps the order the index gave, and a group is never split.
 */
export function promoteTitles<T extends Item>(items: T[], query: string): T[] {
  const q = query.trim().toLowerCase()
  if (!q) return items
  const groups: T[][] = []
  for (const it of items) {
    if (it.type === 'page' || groups.length === 0) groups.push([it])
    else groups[groups.length - 1].push(it)
  }
  const rank = (g: T[]) => {
    if (g[0].type !== 'page') return 2
    const t = text(g[0].content)
    return t === q ? 0 : t.includes(q) ? 1 : 2
  }
  return groups.map((g, i) => ({ g, i, r: rank(g) })).sort((a, b) => a.r - b.r || a.i - b.i).flatMap((x) => x.g)
}
