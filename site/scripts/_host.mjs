// A static host for a built site, in this process, on a free port: /x -> /x/index.html, gzip for text, a year of caching for hashed assets.
// Every script that opens the site in a browser uses it, so none of them can read another worktree's server by accident (the old scripts used fixed ports).
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join, normalize } from 'node:path'
import { gzipSync } from 'node:zlib'

export function serve(dir, port = 0) {
  if (!dir || !existsSync(dir)) throw new Error('serve: pass the build directory')
  const server = Bun.serve({
    port,
    fetch(req) {
      const url = new URL(req.url)
      const safe = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, '')
      let file = join(dir, safe)
      if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html')
      if (!existsSync(file) && existsSync(file + '.html')) file += '.html'
      if (!existsSync(file)) return new Response('not found', { status: 404 })
      const text = /\.(html|js|css|json|svg|txt|mjs|md|xml)$/.test(file) || !/\.[a-z0-9]+$/i.test(file)
      const headers = new Headers({ 'cache-control': /\/assets\/[^/]+-[A-Za-z0-9_-]{6,}\.[a-z0-9]+$/.test(url.pathname) ? 'public, max-age=31536000, immutable' : 'public, max-age=0, must-revalidate' })
      if (text && (req.headers.get('accept-encoding') ?? '').includes('gzip')) {
        headers.set('content-encoding', 'gzip')
        headers.set('content-type', Bun.file(file).type || 'text/html')
        return new Response(gzipSync(readFileSync(file)), { headers })
      }
      return new Response(Bun.file(file), { headers })
    },
  })
  return { origin: `http://localhost:${server.port}`, stop: () => server.stop(true) }
}
