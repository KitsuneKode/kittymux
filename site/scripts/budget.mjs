// bun scripts/budget.mjs <build dir>: what a first visit downloads, in gzip, for the landing page and one docs page (JS, CSS, fonts, images).
import { gzipSync } from 'node:zlib'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import puppeteer from 'puppeteer-core'

const dir = process.argv[2]
const CHROME = process.env.CHROME ?? '/usr/bin/google-chrome-stable'
// The first plan aimed at 120 KB on the landing page. MEASURED on 2026-10-08: 504 KB gzip (React 19 + TanStack Start + Fumadocs' shell + Base UI): Lighthouse desktop 98,
// mobile (simulated slow 4G, 4x CPU) 73. These limits are the measured numbers plus a margin: they catch a regression, they do not claim the target was met.
const BUDGET = { '/': { js: 540 * 1024 }, '/docs/users/getting-started': { js: 560 * 1024 } }
const server = Bun.spawn(['bun', new URL('./serve.mjs', import.meta.url).pathname, dir, '4177'], { stdout: 'ignore' })
await Bun.sleep(800)
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
let bad = 0
try {
  for (const [path, limit] of Object.entries(BUDGET)) {
    const page = await browser.newPage()
    const seen = new Map()
    page.on('response', async (res) => {
      const url = new URL(res.url())
      if (url.origin !== 'http://localhost:4177') { seen.set(res.url(), { type: 'EXTERNAL', gz: 0 }); return }
      try {
        const body = readFileSync(join(dir, url.pathname === '/' ? 'index.html' : url.pathname))
        seen.set(url.pathname, { type: (url.pathname.match(/\.(js|css|woff2?|png|svg|json)$/)?.[1] ?? 'html'), gz: gzipSync(body).length })
      } catch { /* a directory index */ }
    })
    await page.setViewport({ width: 1280, height: 900 })
    await page.goto(`http://localhost:4177${path}`, { waitUntil: 'networkidle0' })
    const total = (t) => [...seen.values()].filter((v) => v.type === t).reduce((n, v) => n + v.gz, 0)
    const external = [...seen.values()].filter((v) => v.type === 'EXTERNAL').length
    const kb = (n) => (n / 1024).toFixed(1)
    console.log(`${path}: js ${kb(total('js'))} KB gz, css ${kb(total('css'))} KB, fonts ${kb(total('woff2'))} KB, images ${kb(total('png'))} KB, external requests ${external}`)
    if (total('js') > limit.js) { bad++; console.error(`  over budget: js ${kb(total('js'))} KB > ${kb(limit.js)} KB`) }
    if (external) { bad++; console.error('  a request left the site: ' + [...seen.entries()].filter(([, v]) => v.type === 'EXTERNAL').map(([k]) => k).join(', ')) }
    await page.close()
  }
} finally { await browser.close(); server.kill() }
process.exit(bad ? 1 : 0)
