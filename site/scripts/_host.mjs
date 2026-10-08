// A static host for a built site, in this process, on a free port: /x -> /x/index.html, gzip for text, a year of caching for hashed assets.
// Every script that opens the site in a browser uses it, so none of them can read another worktree's server by accident (the old scripts used fixed ports).
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join, normalize } from 'node:path'
import { gzipSync } from 'node:zlib'

/** The header rules of the build (.vercel/output/config.json, next to the static folder), as [regex, headers] pairs; empty when there is no config (a plain folder). */
export function routeHeaders(dir) {
  const file = join(dir, '..', 'config.json')
  if (!existsSync(file)) return []
  try {
    return (JSON.parse(readFileSync(file, 'utf8')).routes ?? []).filter((r) => r.src && r.headers).map((r) => [new RegExp(`^${r.src}$`), r.headers])
  } catch { return [] }
}

export function serve(dir, port = 0) {
  if (!dir || !existsSync(dir)) throw new Error('serve: pass the build directory')
  const rules = routeHeaders(dir)
  function respond(req, url) {
    const safe = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, '')
    let file = join(dir, safe)
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html')
    if (!existsSync(file) && existsSync(file + '.html')) file += '.html'
    if (!existsSync(file)) return new Response('not found', { status: 404 })
    const text = /\.(html|js|css|json|svg|txt|mjs|md|xml)$/.test(file) || !/\.[a-z0-9]+$/i.test(file)
    // without a build config: hashed files for a year, everything else revalidated, like a static host
    const headers = new Headers({ 'cache-control': /\/assets\/[^/]+-[A-Za-z0-9_-]{6,}\.[a-z0-9]+$/.test(url.pathname) ? 'public, max-age=31536000, immutable' : 'public, max-age=0, must-revalidate' })
    if (text && (req.headers.get('accept-encoding') ?? '').includes('gzip')) {
      headers.set('content-encoding', 'gzip')
      headers.set('content-type', Bun.file(file).type || 'text/html')
      return new Response(gzipSync(readFileSync(file)), { headers })
    }
    return new Response(Bun.file(file), { headers })
  }
  const server = Bun.serve({
    port,
    fetch(req) {
      const url = new URL(req.url)
      const res = respond(req, url)
      // the build's own header rules (security headers, cache rules) on top, as the platform applies them
      for (const [re, headers] of rules) if (re.test(url.pathname)) for (const [k, v] of Object.entries(headers)) res.headers.set(k, v)
      return res
    },
  })
  return { origin: `http://localhost:${server.port}`, stop: () => server.stop(true) }
}
