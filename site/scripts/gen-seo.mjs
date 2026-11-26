// bun scripts/gen-seo.mjs <build dir>: writes robots.txt, rss.xml (changelog feed), and — when VITE_SITE_URL is set — sitemap.xml with lastmod and route priorities.
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const walk = (d) => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p] })
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export function siteBase(env) {
  if (!env) return ''
  try {
    const u = new URL(env)
    if (u.protocol !== 'https:' && u.hostname !== 'localhost') return ''
    return u.origin + u.pathname.replace(/\/+$/, '')
  } catch { return '' }
}

/** URL paths of every prerendered HTML page, sorted, without error pages. */
export function pagePaths(dir) {
  return walk(dir)
    .filter((f) => f.endsWith('.html'))
    .map((f) => '/' + f.slice(dir.length + 1).replace(/\\/g, '/').replace(/(^|\/)index\.html$/, '').replace(/\.html$/, ''))
    .map((p) => p.replace(/\/$/, '') || '/')
    .filter((p) => !/^\/(404|500|_)/.test(p))
    .sort()
}

function priorityFor(path) {
  if (path === '/') return '1.0'
  if (path === '/docs' || path === '/keys' || path === '/changelog') return '0.9'
  if (path.startsWith('/docs/users/')) return '0.8'
  return '0.7'
}

function changefreqFor(path) {
  if (path === '/' || path === '/changelog') return 'weekly'
  return 'monthly'
}

export function sitemap(paths, base, lastmod = new Date().toISOString().slice(0, 10)) {
  const loc = (p) => base + (p === '/' ? '/' : p)
  const rows = paths.map((p) =>
    `  <url>\n    <loc>${esc(loc(p))}</loc>\n    <lastmod>${esc(lastmod)}</lastmod>\n    <changefreq>${changefreqFor(p)}</changefreq>\n    <priority>${priorityFor(p)}</priority>\n  </url>`,
  )
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${rows.join('\n')}\n</urlset>\n`
}

/** Parse top changelog bullet items for the RSS 2.0 feed without depending on Vite aliases. */
export function parseChangelogFeed(md, limit = 30) {
  const items = []
  let release = 'Unreleased'
  let group = 'Updates'
  for (const rawLine of md.split(/\r?\n/)) {
    const line = rawLine.trim()
    const h2 = /^##\s+\[?([^\]\n]+?)\]?(?:\s+-\s+(\d{4}-\d{2}-\d{2}))?\s*$/.exec(line)
    if (h2) { release = h2[1].trim(); continue }
    const h3 = /^###\s+(.+)$/.exec(line)
    if (h3) { group = h3[1].trim(); continue }
    const bullet = /^-\s+(.+)$/.exec(line)
    if (bullet) {
      const clean = bullet[1]
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/`([^`]+)`/g, '$1')
        .trim()
      const bold = /^\*\*([^*]+)\*\*/.exec(bullet[1])
      const title = (bold ? bold[1].replace(/[:.]\s*$/, '') : clean.slice(0, 96)).trim()
      items.push({ release, group, title, description: clean })
      if (items.length >= limit) break
    }
  }
  return items
}

export function rss(items, base, pubDate = new Date().toUTCString()) {
  const origin = base || 'https://kittymux.kitsunekode.in'
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
  const entries = items.map((item, idx) => {
    const link = `${origin}/changelog#r-${slug(item.release)}`
    const guid = `kittymux-${slug(item.release)}-${slug(item.title).slice(0, 48)}-${idx}`
    return [
      '    <item>',
      `      <title>${esc(item.title)}</title>`,
      `      <link>${esc(link)}</link>`,
      `      <guid isPermaLink="false">${esc(guid)}</guid>`,
      `      <category>${esc(item.group)}</category>`,
      `      <description>${esc(item.description)}</description>`,
      `      <pubDate>${esc(pubDate)}</pubDate>`,
      '    </item>',
    ].join('\n')
  })
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
    '  <channel>',
    '    <title>kittymux Changelog</title>',
    `    <link>${esc(origin)}/changelog</link>`,
    `    <atom:link href="${esc(origin)}/rss.xml" rel="self" type="application/rss+xml" />`,
    '    <description>Latest upgrades, fixes, and releases for kittymux — the native AI coding agent workspace for kitty.</description>',
    '    <language>en</language>',
    `    <lastBuildDate>${esc(pubDate)}</lastBuildDate>`,
    ...entries,
    '  </channel>',
    '</rss>',
    '',
  ].join('\n')
}

export function robots(base) {
  return `User-agent: *\nAllow: /\n${base ? `\nSitemap: ${base}/sitemap.xml\n` : ''}`
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2]
  if (!dir) { console.error('usage: bun scripts/gen-seo.mjs <build dir>'); process.exit(2) }
  const base = siteBase(process.env.VITE_SITE_URL)
  writeFileSync(join(dir, 'robots.txt'), robots(base))
  const clPath = fileURLToPath(new URL('../src/generated/CHANGELOG.md', import.meta.url))
  const feedItems = existsSync(clPath) ? parseChangelogFeed(readFileSync(clPath, 'utf8')) : []
  writeFileSync(join(dir, 'rss.xml'), rss(feedItems, base))
  if (base) {
    const paths = pagePaths(dir)
    writeFileSync(join(dir, 'sitemap.xml'), sitemap(paths, base))
    console.log(`seo: robots.txt, rss.xml (${feedItems.length} items), sitemap.xml (${paths.length} pages) for ${base}`)
  } else {
    console.log(`seo: robots.txt, rss.xml (${feedItems.length} items) only: set VITE_SITE_URL=https://your.domain at build time for canonical URLs and a sitemap`)
  }
}
