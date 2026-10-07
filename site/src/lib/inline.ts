export type Inline = { t: 'text' | 'bold' | 'code'; v: string } | { t: 'link'; v: string; href: string }

const DOCS_FILE = /^docs\/((?:users|developer)\/[a-z0-9-]+|index)\.mdx$/

/** A markdown link target as a site href, or null: only http(s) and repo-relative docs pages are links. */
function hrefOf(raw: string): string | null {
  if (/^https?:\/\//i.test(raw)) return raw
  const m = DOCS_FILE.exec(raw)
  if (m) return m[1] === 'index' ? '/docs' : `/docs/${m[1]}`
  return null
}

/** The few inline forms the changelog uses: **bold**, `code`, [text](target). Anything unclosed stays literal. */
export function parseInline(src: string): Inline[] {
  const out: Inline[] = []
  let text = ''
  const flush = () => { if (text) { out.push({ t: 'text', v: text }); text = '' } }
  let i = 0
  while (i < src.length) {
    const rest = src.slice(i)
    let m: RegExpExecArray | null
    if ((m = /^\*\*([^*]+)\*\*/.exec(rest))) { flush(); out.push({ t: 'bold', v: m[1] }); i += m[0].length; continue }
    if ((m = /^`([^`]+)`/.exec(rest))) { flush(); out.push({ t: 'code', v: m[1] }); i += m[0].length; continue }
    if ((m = /^\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)/.exec(rest))) {
      const href = hrefOf(m[2])
      if (href) { flush(); out.push({ t: 'link', v: m[1], href }) } else text += m[1]
      i += m[0].length
      continue
    }
    text += src[i]
    i++
  }
  flush()
  return out
}

export type Release = { heading: string; groups: { name: string; items: string[] }[] }

/** CHANGELOG.md (Keep a Changelog) → releases, newest first as written. Wrapped bullet lines are joined with a space. */
export function parseChangelog(md: string): Release[] {
  const releases: Release[] = []
  let group: Release['groups'][number] | null = null
  for (const line of md.split('\n')) {
    let m: RegExpExecArray | null
    if ((m = /^## \[?([^\]\n]+?)\]?(?:\s+-\s+(.+))?$/.exec(line)) && line.startsWith('## ')) {
      releases.push({ heading: m[2] ? `${m[1]} · ${m[2]}` : m[1], groups: [] })
      group = null
    } else if (releases.length && (m = /^### (.+)$/.exec(line))) {
      group = { name: m[1].trim(), items: [] }
      releases[releases.length - 1].groups.push(group)
    } else if (group && (m = /^- (.*)$/.exec(line))) {
      group.items.push(m[1])
    } else if (group && group.items.length && /^\s{2,}\S/.test(line)) {
      group.items[group.items.length - 1] += ' ' + line.trim()
    }
  }
  if (!releases.length) throw new Error('changelog: no "## " release heading found')
  return releases
}
