// bun scripts/axe.mjs <build dir>: axe-core in headless Chrome on key pages, in light and dark, horizontal overflow at four widths,
// and the search dialog (it must find a page from the prebuilt index).
import { readFileSync } from 'node:fs'
import puppeteer from 'puppeteer-core'

const dir = process.argv[2]
const CHROME = process.env.CHROME ?? '/usr/bin/google-chrome-stable'
const PAGES = ['/', '/docs', '/docs/users/getting-started', '/docs/users/shortcuts', '/docs/users/cli-reference', '/docs/users/agent-status', '/keys', '/changelog']
const WIDTHS = [320, 390, 768, 1440]
const axeSource = readFileSync(new URL('../node_modules/axe-core/axe.min.js', import.meta.url), 'utf8')

const server = Bun.spawn(['bun', new URL('./serve.mjs', import.meta.url).pathname, dir, '4174'], { stdout: 'ignore' })
await Bun.sleep(800)
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
let bad = 0
try {
  for (const scheme of ['light', 'dark']) {
    for (const path of PAGES) {
      const page = await browser.newPage()
      await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
      await page.setViewport({ width: 1280, height: 900 })
      await page.goto(`http://localhost:4174${path}`, { waitUntil: 'networkidle0' })
      await page.evaluate(axeSource)
      const result = await page.evaluate(() => axe.run(document, { resultTypes: ['violations'] }))
      // Two moderate best-practice findings come from markup Fumadocs owns and we cannot attribute to: the table of contents sits in a plain <div> beside <main>
      // (region), and every code block's scroll box is a labelled region with the same label (landmark-unique). They are filtered here, by place, and nothing else is.
      const vendor = await page.evaluate((violations) => violations.map((v) => v.nodes.map((n) => {
        try { const el = document.querySelector(n.target.join(' ')); return Boolean(el && el.closest('#nd-toc, figure.shiki')) } catch { return false }
      })), result.violations)
      result.violations.forEach((v, i) => { if (['region', 'landmark-unique'].includes(v.id)) v.nodes = v.nodes.filter((_, j) => !vendor[i][j]) })
      result.violations = result.violations.filter((v) => v.nodes.length)
      for (const v of result.violations) {
        bad++
        console.error(`axe [${scheme}] ${path}: ${v.id} (${v.impact}) ${v.help} — ${v.nodes.length} node(s), e.g. ${v.nodes.slice(0, 4).map((n) => n.target?.join(' ')).join(' | ')}`)
      }
      await page.close()
      for (const width of WIDTHS) {                                     // a visitor on a phone LOADS the page at that width: do the same, never resize one
        const narrow = await browser.newPage()
        await narrow.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
        await narrow.setViewport({ width, height: 900 })
        await narrow.goto(`http://localhost:4174${path}`, { waitUntil: 'networkidle0' })
        const over = await narrow.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        if (over > 0) { bad++; console.error(`overflow [${scheme}] ${path} @${width}px: the page is ${over}px wider than the window`) }
        await narrow.close()
      }
    }
  }
  // search: open with the hotkey, type a word from the docs, a result must appear
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900 })
  await page.goto('http://localhost:4174/docs', { waitUntil: 'networkidle0' })
  await page.keyboard.down('Control'); await page.keyboard.press('KeyK'); await page.keyboard.up('Control')
  await page.waitForSelector('input[type="search"], input[placeholder*="earch"], [role="dialog"] input', { timeout: 5000 })
  await page.keyboard.type('palette')
  const found = await page.waitForFunction(() => document.querySelectorAll('[role="dialog"] [role="option"], [role="dialog"] a').length > 0, { timeout: 8000 }).then(() => true, () => false)
  if (!found) { bad++; console.error('search: typing "palette" found nothing') }
  await page.close()
  // the landing page's own search field loads the search code on its first click
  const home = await browser.newPage()
  await home.setViewport({ width: 1280, height: 900 })
  await home.goto('http://localhost:4174/', { waitUntil: 'networkidle0' })
  const [btn] = await home.$$('xpath/.//button[contains(., "Search the docs")]')
  if (!btn) { bad++; console.error('landing: no "Search the docs" button') } else {
    await btn.click()
    const opened = await home.waitForSelector('[role="dialog"] input', { timeout: 8000 }).then(() => true, () => false)
    if (!opened) { bad++; console.error('landing: the search button did not open the search dialog') }
  }
  await home.close()
} finally { await browser.close(); server.kill() }
if (bad) { console.error(`${bad} problem(s)`); process.exit(1) }
console.log('axe ok: no violations; no horizontal overflow at 320, 390, 768, 1440; light and dark; search finds a page')
