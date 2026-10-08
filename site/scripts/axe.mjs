// bun scripts/axe.mjs <build dir>: axe-core in headless Chrome on key pages, in light and dark, horizontal overflow at four widths,
// and the search dialog (it must find a page from the prebuilt index).
import { readFileSync } from 'node:fs'
import puppeteer from 'puppeteer-core'
import { serve } from './_host.mjs'

const dir = process.argv[2]
const CHROME = process.env.CHROME ?? '/usr/bin/google-chrome-stable'
const PAGES = ['/', '/docs', '/docs/users/getting-started', '/docs/users/shortcuts', '/docs/users/cli-reference', '/docs/users/agent-status', '/keys', '/changelog']
const WIDTHS = [320, 390, 768, 1440]
const axeSource = readFileSync(new URL('../node_modules/axe-core/axe.min.js', import.meta.url), 'utf8')

const host = serve(dir)
const ORIGIN = host.origin
let browser
let bad = 0
try {
  browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
  for (const scheme of ['light', 'dark']) {
    for (const path of PAGES) {
      const page = await browser.newPage()
      await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
      await page.setViewport({ width: 1280, height: 900 })
      await page.goto(`${ORIGIN}${path}`, { waitUntil: 'networkidle0' })
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
        await narrow.goto(`${ORIGIN}${path}`, { waitUntil: 'networkidle0' })
        const over = await narrow.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        if (over > 0) { bad++; console.error(`overflow [${scheme}] ${path} @${width}px: the page is ${over}px wider than the window`) }
        await narrow.close()
      }
    }
  }
  // the build's security headers (CSP above all) must not block anything the pages do: load pages with a console listener and fail on a violation or an uncaught error.
  // (/_vercel/... only exists on Vercel: a 404 for it here is expected and ignored.)
  for (const path of ['/', '/docs/users/getting-started', '/keys', '/changelog']) {
    const pg = await browser.newPage()
    const problems = []
    pg.on('console', (m) => { if (m.type() === 'error' && !/_vercel|Failed to load resource/.test(m.text() + (m.location()?.url ?? ''))) problems.push(m.text()) })
    pg.on('pageerror', (e) => problems.push(String(e)))
    const res = await pg.goto(`${ORIGIN}${path}`, { waitUntil: 'networkidle0' })
    if (!res.headers()['content-security-policy']?.includes("default-src 'self'")) { bad++; console.error(`headers: ${path} has no content-security-policy`) }
    if (res.headers()['x-content-type-options'] !== 'nosniff') { bad++; console.error(`headers: ${path} has no x-content-type-options: nosniff`) }
    for (const t of problems) { bad++; console.error(`console [${path}]: ${t.slice(0, 200)}`) }
    await pg.close()
  }
  // search: open with the hotkey, type a word from the docs, a result must appear
  const page = await browser.newPage()
  await page.setViewport({ width: 1280, height: 900 })
  await page.goto(`${ORIGIN}/docs`, { waitUntil: 'networkidle0' })
  await page.keyboard.down('Control'); await page.keyboard.press('KeyK'); await page.keyboard.up('Control')
  await page.waitForSelector('input[type="search"], input[placeholder*="earch"], [role="dialog"] input', { timeout: 5000 })
  await page.keyboard.type('palette')
  const found = await page.waitForFunction(() => document.querySelectorAll('[role="dialog"] [role="option"], [role="dialog"] a[href^="/docs"]').length > 0, { timeout: 8000 }).then(() => true, () => false)
  if (!found) { bad++; console.error('search: typing "palette" found nothing') }
  await page.close()
  // the landing page's own search field loads the search code on its first click
  const home = await browser.newPage()
  await home.setViewport({ width: 1280, height: 900 })
  await home.goto(`${ORIGIN}/`, { waitUntil: 'networkidle0' })
  const [btn] = await home.$$('xpath/.//button[contains(., "Search the docs")]')
  if (!btn) { bad++; console.error('landing: no "Search the docs" button') } else {
    await btn.click()
    const opened = await home.waitForSelector('[role="dialog"] input', { timeout: 8000 }).then(() => true, () => false)
    if (!opened) { bad++; console.error('landing: the search button did not open the search dialog') }
  }
  await home.close()
  // search on a phone: the docs header has a search button (there is no Ctrl K on a touch screen); it opens the dialog and finds a page
  const phone = await browser.newPage()
  await phone.setViewport({ width: 390, height: 800, isMobile: true, hasTouch: true })
  await phone.goto(`${ORIGIN}/docs/users/getting-started`, { waitUntil: 'networkidle0' })
  const trigger = await phone.$('button[aria-label*="earch" i], [data-search-full], [data-search]')
  if (!trigger) { bad++; console.error('phone: no search button on a docs page') } else {
    await trigger.tap()
    const dialog = await phone.waitForSelector('[role="dialog"] input', { timeout: 8000 }).then(() => true, () => false)
    if (!dialog) { bad++; console.error('phone: tapping search did not open the dialog') } else {
      await phone.keyboard.type('palette')
      const hit = await phone.waitForFunction(() => document.querySelectorAll('[role="dialog"] [role="option"], [role="dialog"] a[href^="/docs"]').length > 0, { timeout: 8000 }).then(() => true, () => false)
      if (!hit) { bad++; console.error('phone: searching on a phone found nothing') }
    }
  }
  await phone.close()
  // client-side navigation, on a host with NO server (this one): a click must not call an endpoint that only a server has
  const nav = await browser.newPage()
  await nav.setViewport({ width: 1280, height: 900 })
  await nav.goto(`${ORIGIN}/docs/users/getting-started`, { waitUntil: 'networkidle0' })
  const before = await nav.$eval('h1', (h) => h.textContent)
  await nav.click('a[href="/docs/users/shortcuts"]')
  const moved = await nav.waitForFunction((b) => document.querySelector('h1') && document.querySelector('h1').textContent !== b && location.pathname === '/docs/users/shortcuts', { timeout: 8000 }, before).then(() => true, () => false)
  const broke = await nav.evaluate(() => /Something went wrong/i.test(document.body.innerText))
  if (!moved || broke) { bad++; console.error(`navigation: clicking a docs link ${broke ? 'showed an error page' : 'did not change the page'}`) }
  await nav.close()
  const hub = await browser.newPage()
  await hub.setViewport({ width: 1280, height: 900 })
  await hub.goto(`${ORIGIN}/`, { waitUntil: 'networkidle0' })
  const [read] = await hub.$$('xpath/.//a[contains(., "Read the docs")]')
  await read.click()
  const reached = await hub.waitForFunction(() => location.pathname.startsWith('/docs') && document.querySelector('h1'), { timeout: 8000 }).then(() => true, () => false)
  const broke2 = await hub.evaluate(() => /Something went wrong/i.test(document.body.innerText))
  if (!reached || broke2) { bad++; console.error('navigation: "Read the docs" on the landing page did not reach a docs page') }
  await hub.close()
} finally { await browser?.close(); host.stop() }
if (bad) { console.error(`${bad} problem(s)`); process.exit(1) }
console.log('axe ok: no violations; no horizontal overflow at 320, 390, 768, 1440; light and dark; search finds a page')
