// bun scripts/gen-seo.mjs <build dir>: writes robots.txt and, when the public address is known, sitemap.xml into the built site (runs after `vite build`).
// The address comes from VITE_SITE_URL (https only). Without it there is no sitemap: a sitemap of made-up addresses is worse than none.
import { readdirSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const walk = (d) => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p] })

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

export function sitemap(paths, base) {
  const loc = (p) => base + (p === '/' ? '/' : p)
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${paths.map((p) => `  <url><loc>${esc(loc(p))}</loc></url>`).join('\n')}\n</urlset>\n`
}

export function robots(base) {
  // everything is public; the search index and the llms files are for readers and tools too
  return `User-agent: *\nAllow: /\n${base ? `\nSitemap: ${base}/sitemap.xml\n` : ''}`
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2]
  if (!dir) { console.error('usage: bun scripts/gen-seo.mjs <build dir>'); process.exit(2) }
  const base = siteBase(process.env.VITE_SITE_URL)
  writeFileSync(join(dir, 'robots.txt'), robots(base))
  if (base) {
    const paths = pagePaths(dir)
    writeFileSync(join(dir, 'sitemap.xml'), sitemap(paths, base))
    console.log(`seo: robots.txt, sitemap.xml (${paths.length} pages) for ${base}`)
  } else {
    console.log('seo: robots.txt only: set VITE_SITE_URL=https://your.domain at build time for canonical URLs and a sitemap')
  }
}
