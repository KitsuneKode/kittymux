// Crawl the built static site: every internal link and anchor resolves, every image exists, one h1 with words in it, a title, a description, a lang.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const walk = (d) => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p] })
const attr = (html, tag, name) => [...html.matchAll(new RegExp(`<${tag}\\b[^>]*\\s${name}="([^"]*)"`, 'gi'))].map((m) => m[1])

export function crawl(dir, expectedPages) {
  const errors = []
  const files = walk(dir).filter((f) => f.endsWith('.html'))
  const rel = (f) => '/' + f.slice(dir.length + 1).replace(/\\/g, '/')
  const urlOf = (f) => rel(f).replace(/\/index\.html$/, '').replace(/\.html$/, '') || '/'
  const byUrl = new Map(files.map((f) => [urlOf(f), readFileSync(f, 'utf8')]))
  const idsOf = (html) => new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]))

  if (files.length !== expectedPages) errors.push(`expected ${expectedPages} pages, found ${files.length}`)

  for (const [url, html] of byUrl) {
    if (html.length === 0) { errors.push(`${url}: the file is EMPTY (a prerender race can write one)`); continue }
    const h1 = (html.match(/<h1\b/g) ?? []).length
    if (h1 !== 1) errors.push(`${url}: has ${h1} <h1> (want exactly one)`)
    else if (!/<h1\b[^>]*>(?:\s|<[^>]+>)*[^\s<][\s\S]*?<\/h1>/.test(html)) errors.push(`${url}: the <h1> is empty in the static HTML`)
    if (!/<title>[^<]+<\/title>/.test(html)) errors.push(`${url}: no <title>`)
    if (!/<meta[^>]+name="description"[^>]+content="[^"]+"/.test(html)) errors.push(`${url}: no meta description`)
    if (!/<html[^>]*\slang="[a-zA-Z-]+"/.test(html)) errors.push(`${url}: <html> has no lang`)

    for (const href of attr(html, 'a', 'href')) {
      if (/^(https?:|mailto:|tel:|javascript:)/i.test(href) || href.startsWith('//')) continue
      const [path, hash] = href.split('#')
      const target = path === '' ? url : path.replace(/\/$/, '') || '/'
      const page = byUrl.get(target)
      if (path !== '' && !page && !existsSync(join(dir, target))) { errors.push(`${url}: link to ${href} goes nowhere`); continue }
      if (hash && page && !idsOf(page).has(decodeURIComponent(hash))) errors.push(`${url}: link to ${href}: no element with id "${hash}"`)
    }
    for (const src of [...attr(html, 'img', 'src'), ...attr(html, 'source', 'srcset')]) {
      if (/^(https?:|data:)/i.test(src) || src.startsWith('//')) continue
      if (!existsSync(join(dir, src.split('?')[0].split(' ')[0]))) errors.push(`${url}: image ${src} does not exist`)
    }
  }
  return { errors, pages: files.length }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2]
  const expected = Number(process.argv[3])
  if (!dir || !expected) { console.error('usage: bun scripts/check-site.mjs <build dir> <expected page count>'); process.exit(2) }
  const { errors, pages } = crawl(dir, expected)
  if (errors.length) { console.error(errors.join('\n')); process.exit(1) }
  console.log(`crawl ok: ${pages} pages, links, anchors, images, h1, title, description, lang`)
}
