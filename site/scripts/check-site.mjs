// Crawl the built static site: every internal link and anchor resolves, every image exists, one h1 with words in it, a title, a description, a lang.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { siteBase } from './gen-seo.mjs'

const walk = (d) => readdirSync(d).flatMap((n) => { const p = join(d, n); return statSync(p).isDirectory() ? walk(p) : [p] })
const attr = (html, tag, name) => [...html.matchAll(new RegExp(`<${tag}\\b[^>]*\\s${name}="([^"]*)"`, 'gi'))].map((m) => m[1])

const metaContent = (html, key, name) => html.match(new RegExp(`<meta[^>]+${key}="${name}"[^>]+content="([^"]*)"`, 'i'))?.[1] ?? html.match(new RegExp(`<meta[^>]+content="([^"]*)"[^>]+${key}="${name}"`, 'i'))?.[1]

/** What a search engine and a link preview read: a title and description that fit and are not shared, Open Graph and Twitter tags, parseable structured data, a canonical URL when the site address is known. */
function seo(url, html, errors, siteUrl, seen) {
  const { titles, descriptions } = seen
  const title = html.match(/<title>([^<]*)<\/title>/)?.[1]
  const desc = metaContent(html, 'name', 'description')
  if (title) {
    if (title.length > 60) errors.push(`${url}: the title is ${title.length} characters (a result cuts it at about 60)`)
    if (titles.has(title) && titles.get(title) !== url) errors.push(`${url}: the title "${title}" is also on ${titles.get(title)}`)
    titles.set(title, url)
  }
  if (desc) {
    if (desc.length < 70 || desc.length > 160) errors.push(`${url}: the description is ${desc.length} characters (aim for 70-160)`)
    if (descriptions.has(desc) && descriptions.get(desc) !== url) errors.push(`${url}: the description is the same as ${descriptions.get(desc)}`)
    descriptions.set(desc, url)
  }
  for (const [key, name] of [['property', 'og:title'], ['property', 'og:description'], ['property', 'og:type'], ['name', 'twitter:card']]) {
    if (!metaContent(html, key, name)) errors.push(`${url}: no ${name}`)
  }
  if (/<meta[^>]+name="robots"[^>]+noindex/i.test(html)) errors.push(`${url}: asks not to be indexed`)
  for (const m of html.matchAll(/<script[^>]+type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g)) {
    try { JSON.parse(m[1]) } catch { errors.push(`${url}: structured data is not valid JSON`) }
  }
  const canonicals = [...html.matchAll(/<link[^>]+rel="canonical"[^>]+href="([^"]*)"/g)].map((m) => m[1])
  if (siteUrl) {
    const want = siteUrl + (url === '/' ? '/' : url)
    if (canonicals.length !== 1 || canonicals[0] !== want) errors.push(`${url}: canonical is ${JSON.stringify(canonicals)}, want ["${want}"]`)
    const image = metaContent(html, 'property', 'og:image')
    if (!image || !image.startsWith(siteUrl + '/')) errors.push(`${url}: og:image is not an absolute address on the site (${image})`)
  } else if (canonicals.length) errors.push(`${url}: a canonical URL without a known site address`)
}

export function crawl(dir, expectedPages, siteUrl = '') {
  const errors = []
  const seen = { titles: new Map(), descriptions: new Map() }
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

    seo(url, html, errors, siteUrl, seen)

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
  const { errors, pages } = crawl(dir, expected, siteBase(process.env.VITE_SITE_URL))
  if (errors.length) { console.error(errors.join('\n')); process.exit(1) }
  console.log(`crawl ok: ${pages} pages, links, anchors, images, h1, title, description, lang, social tags, structured data, canonical`)
}
