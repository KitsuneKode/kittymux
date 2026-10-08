// bun scripts/budget.mjs <build dir>: what a first visit downloads, in gzip, for the landing page and one docs page (JS, CSS, fonts, images),
// and that nothing leaves the site. The numbers are read from what the browser was actually sent; a page that downloaded no JavaScript at all is a failure, not a pass.
import { gzipSync } from 'node:zlib'
import puppeteer from 'puppeteer-core'
import { serve } from './_host.mjs'

const dir = process.argv[2]
const CHROME = process.env.CHROME ?? '/usr/bin/google-chrome-stable'
// The first plan aimed at 120 KB of JavaScript on the landing page. MEASURED 2026-10-08, gzip: 150 KB for the landing page (React 19 + TanStack Start's router and hydration are most of it:
// `bun scripts/chunks.mjs <dir> /` lists every script), 363 KB for a docs page (the Fumadocs shell, Base UI, the MDX runtime). These limits are the measured numbers plus a margin:
// they catch a regression, they do not claim the 120 KB target was met.
const BUDGET = { '/': { js: 165 * 1024 }, '/docs/users/getting-started': { js: 385 * 1024 } }
const host = serve(dir)
let browser
let bad = 0
try {
  browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  for (const [path, limit] of Object.entries(BUDGET)) {
    const page = await browser.newPage()
    const seen = new Map()
    const pending = []
    page.on('response', (res) => {
      const url = new URL(res.url())
      if (url.origin !== host.origin) { seen.set(res.url(), { type: 'EXTERNAL', gz: 0 }); return }
      const type = url.pathname.match(/\.(js|css|woff2?|png|svg|json)$/)?.[1] ?? 'html'
      pending.push(res.buffer().then((body) => seen.set(url.pathname, { type, gz: gzipSync(body).length }), () => seen.set(url.pathname, { type: 'UNREADABLE', gz: 0 })))
    })
    await page.setViewport({ width: 1280, height: 900 })
    await page.goto(`${host.origin}${path}`, { waitUntil: 'networkidle0' })
    await Promise.all(pending)
    const total = (t) => [...seen.values()].filter((v) => v.type === t).reduce((n, v) => n + v.gz, 0)
    const count = (t) => [...seen.values()].filter((v) => v.type === t).length
    const external = count('EXTERNAL')
    const kb = (n) => (n / 1024).toFixed(1)
    console.log(`${path}: js ${kb(total('js'))} KB gz, css ${kb(total('css'))} KB, fonts ${kb(total('woff2'))} KB, images ${kb(total('png'))} KB, external requests ${external}`)
    if (count('js') === 0 || total('js') === 0) { bad++; console.error('  measured no JavaScript at all: the page did not load, so the budget says nothing') }
    if (count('UNREADABLE')) { bad++; console.error(`  ${count('UNREADABLE')} response(s) could not be read`) }
    if (total('js') > limit.js) { bad++; console.error(`  over budget: js ${kb(total('js'))} KB > ${kb(limit.js)} KB`) }
    if (external) { bad++; console.error('  a request left the site: ' + [...seen.entries()].filter(([, v]) => v.type === 'EXTERNAL').map(([k]) => k).join(', ')) }
    await page.close()
  }
} finally { await browser?.close(); host.stop() }
process.exit(bad ? 1 : 0)
