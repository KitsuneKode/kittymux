// bun scripts/tour.mjs <build dir> <out dir> [path] [width]: full-page screenshots of one page, light and dark, for reading the design with your own eyes.
import { mkdirSync } from 'node:fs'
import puppeteer from 'puppeteer-core'
import { serve } from './_host.mjs'

const [dir, out, path = '/', width = '1440'] = process.argv.slice(2)
if (!dir || !out) { console.error('usage: bun scripts/tour.mjs <build dir> <out dir> [path] [width]'); process.exit(2) }
mkdirSync(out, { recursive: true })
const host = serve(dir)
const browser = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/usr/bin/google-chrome-stable', headless: 'new', args: ['--no-sandbox'] })
try {
  for (const scheme of ['light', 'dark']) {
    const page = await browser.newPage()
    await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
    await page.setViewport({ width: Number(width), height: 900 })
    await page.goto(`${host.origin}${path}`, { waitUntil: 'networkidle0' })
    await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 80)) } window.scrollTo(0, 0) })
    await Bun.sleep(500)
    const name = `${path === '/' ? 'home' : path.slice(1).replace(/\//g, '-')}-${width}-${scheme}.png`
    await page.screenshot({ path: `${out}/${name}`, fullPage: true })
    console.log(`${out}/${name}`)
    await page.close()
  }
} finally { await browser.close(); host.stop() }
