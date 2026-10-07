// bun scripts/shoot.mjs <build dir> [paths...]: screenshots of key pages at three widths in light and dark (headless Chrome) into .shots/.
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import puppeteer from 'puppeteer-core'

const dir = process.argv[2]
const CHROME = process.env.CHROME ?? '/usr/bin/google-chrome-stable'
const PAGES = process.argv.slice(3).length ? process.argv.slice(3) : ['/', '/docs/users/getting-started', '/docs/users/agent-status', '/keys', '/changelog']
const WIDTHS = (process.env.WIDTHS ?? '1440,768,390').split(',').map(Number)
const SCHEMES = (process.env.SCHEMES ?? 'light,dark').split(',')
const out = new URL('../.shots/', import.meta.url).pathname
mkdirSync(out, { recursive: true })

const server = Bun.spawn(['bun', new URL('./serve.mjs', import.meta.url).pathname, dir, '4175'], { stdout: 'ignore' })
await Bun.sleep(800)
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
try {
  for (const scheme of SCHEMES) {
    for (const path of PAGES) {
      for (const width of WIDTHS) {
        const page = await browser.newPage()
        await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
        await page.setViewport({ width, height: 900 })
        await page.goto(`http://localhost:4175${path}`, { waitUntil: 'networkidle0' })
        // lazy images only load once scrolled into view: walk the page so a full-page shot is not full of holes
        await page.evaluate(async () => {
          for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)) }
          window.scrollTo(0, 0)
        })
        await Bun.sleep(400)
        const slug = (path === '/' ? 'home' : path.slice(1).replace(/[/#]/g, '-')) + `-${width}-${scheme}.png`
        await page.screenshot({ path: join(out, slug), fullPage: process.env.FULL === '1' })
        console.log(join(out, slug))
        await page.close()
      }
    }
  }
} finally { await browser.close(); server.kill() }
