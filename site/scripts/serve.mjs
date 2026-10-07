// bun scripts/serve.mjs <dir> [port]: serves a built site the way a static host does (/x -> /x/index.html).
import { existsSync, statSync } from 'node:fs'
import { join, normalize } from 'node:path'

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
    return existsSync(file) ? new Response(Bun.file(file)) : new Response('not found', { status: 404 })
  },
})
console.log(`serving ${dir} on http://localhost:${port}`)
