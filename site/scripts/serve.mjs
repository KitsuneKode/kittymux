// bun scripts/serve.mjs <dir> [port]: serves a built site the way a static host does (/x -> /x/index.html).
import { existsSync, readFileSync, statSync } from 'node:fs'
import { join, normalize } from 'node:path'
import { gzipSync } from 'node:zlib'

const dir = process.argv[2]
const port = Number(process.argv[3] ?? 4173)
if (!dir || !existsSync(dir)) { console.error('serve: pass the build directory'); process.exit(1) }
Bun.serve({
  port,
  fetch(req) {
    const url = new URL(req.url)
    const safe = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, '')
    let file = join(dir, safe)
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html')
    if (!existsSync(file) && existsSync(file + '.html')) file += '.html'
    if (!existsSync(file)) return new Response('not found', { status: 404 })
    // like a real static host: compress text, and let hashed assets be cached for a year
    const text = /\.(html|js|css|json|svg|txt|mjs)$/.test(file) || !/\.[a-z0-9]+$/i.test(file)
    const headers = new Headers({ 'cache-control': /\/assets\/[^/]+-[A-Za-z0-9_-]{6,}\.[a-z0-9]+$/.test(url.pathname) ? 'public, max-age=31536000, immutable' : 'public, max-age=0, must-revalidate' })
    if (text && (req.headers.get('accept-encoding') ?? '').includes('gzip')) {
      headers.set('content-encoding', 'gzip')
      headers.set('content-type', Bun.file(file).type || 'text/html')
      return new Response(gzipSync(readFileSync(file)), { headers })
    }
    return new Response(Bun.file(file), { headers })
  },
})
console.log(`serving ${dir} on http://localhost:${port}`)
