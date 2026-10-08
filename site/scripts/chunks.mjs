// bun scripts/chunks.mjs <build dir> [path]: every script a first visit to `path` downloads, largest first, in gzip. Use it to find what a page pays for before touching the budget.
import { gzipSync } from 'node:zlib'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import puppeteer from 'puppeteer-core'
const dir = process.argv[2], path = process.argv[3] ?? '/'
const server = Bun.spawn(['bun', 'scripts/serve.mjs', dir, '4178'], { stdout: 'ignore' })
await Bun.sleep(800)
const b = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome-stable', headless: 'new', args: ['--no-sandbox'] })
const p = await b.newPage(); const seen = []
p.on('response', (r) => { const u = new URL(r.url()); if (u.pathname.endsWith('.js')) seen.push([u.pathname, gzipSync(readFileSync(join(dir, u.pathname))).length]) })
await p.goto('http://localhost:4178' + path, { waitUntil: 'networkidle0' })
for (const [n, g] of seen.sort((a, b) => b[1] - a[1])) console.log((g / 1024).toFixed(1).padStart(7), n)
await b.close(); server.kill()
