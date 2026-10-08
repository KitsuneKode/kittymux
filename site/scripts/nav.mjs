// bun scripts/nav.mjs <build dir>: moving between docs pages the way a hand does it, on a static host, with real clicks.
// Every click that goes to another page must end at the TOP of THAT page (its own <h1>, scroll 0), also on a slow network; back/forward restore the old
// position; a link with #heading lands on the heading; the pager's neighbours are preloaded while the browser is idle; a slow load shows the progress bar.
import puppeteer from 'puppeteer-core'
import { serve } from './_host.mjs'

const dir = process.argv[2]
if (!dir) { console.error('usage: bun scripts/nav.mjs <build dir>'); process.exit(2) }
const host = serve(dir)
const browser = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/usr/bin/google-chrome-stable', headless: 'new', args: ['--no-sandbox'] })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let bad = 0
const check = (ok, what, detail = '') => { if (!ok) bad++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}${detail && !ok ? '  ' + detail : ''}`) }
const where = (p) => p.evaluate(() => ({ path: location.pathname + location.hash, y: Math.round(scrollY), h1: document.querySelector('h1')?.textContent ?? '' }))
const FROM = '/docs/users/getting-started'

async function open({ delay = 0, width = 1440 } = {}) {
  const page = await browser.newPage()
  await page.setViewport({ width, height: 900 })
  const seen = []
  if (delay) {
    await page.setRequestInterception(true)
    page.on('request', async (r) => { if (page.__slow && /staticServerFnCache|assets\/.*mdx/.test(r.url())) await sleep(delay); r.continue().catch(() => {}) })
  }
  page.on('request', (r) => seen.push(r.url()))
  await page.goto(host.origin + FROM, { waitUntil: 'networkidle0' })
  page.__seen = seen
  return page
}
async function clickLink(page, selector, pick = (all) => all[0]) {
  await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight)); await sleep(200)
  const el = pick(await page.$$(selector))
  await el.evaluate((e) => e.scrollIntoView({ block: 'center' })); await sleep(150)
  await el.click()
}
const last = (all) => all[all.length - 1]

for (const [label, selector, pick, expectH1] of [
  ['the pager\'s Next', 'a[href="/docs/users/install-and-update"]', last, 'Install and update'],
  ['a link in the text', 'article a[href="/docs/users/install-and-update"], main a[href="/docs/users/install-and-update"]', undefined, 'Install and update'],
  ['a sidebar link', '#nd-sidebar a[href="/docs/users/troubleshooting"], aside a[href="/docs/users/troubleshooting"]', undefined, 'Troubleshooting'],
]) {
  const page = await open()
  await clickLink(page, selector, pick); await sleep(900)
  const w = await where(page)
  check(w.y === 0 && w.h1 === expectH1, `${label} ends at the top of "${expectH1}"`, JSON.stringify(w))
  await page.close()
}

{
  const page = await open({ delay: 900 })
  page.__slow = true
  await clickLink(page, '#nd-sidebar a[href="/docs/users/troubleshooting"], aside a[href="/docs/users/troubleshooting"]')   // not a pager neighbour, so it is NOT preloaded
  await sleep(550)
  const bar = await page.evaluate(() => !!document.querySelector('.nav-progress'))
  const mid = await where(page)
  await sleep(3500)
  const w = await where(page)
  check(bar, 'a slow load shows the progress bar after a moment', JSON.stringify(mid))
  check(w.y === 0 && w.h1 === 'Troubleshooting', 'a slow load still ends at the top of the new page', JSON.stringify(w))
  check(!(await page.evaluate(() => !!document.querySelector('.nav-progress'))), 'the progress bar is gone when the page is there')
  await page.close()
}

{
  const page = await open()
  await clickLink(page, 'a[href="/docs/users/install-and-update"]', last); await sleep(900)
  await page.goBack(); await sleep(900)
  const w = await where(page)
  check(w.path === FROM && w.y > 800, 'back returns to the old page at the old position', JSON.stringify(w))
  await page.goForward(); await sleep(900)
  const f = await where(page)
  check(f.h1 === 'Install and update', 'forward shows the next page again', JSON.stringify(f))
  await page.close()
}

{
  const page = await open()
  const id = await page.evaluate(() => document.querySelector('h2[id]')?.id)
  await page.evaluate((id) => { document.querySelector('main')?.insertAdjacentHTML('beforeend', `<a id="probe" href="/docs/users/shortcuts#${id}">probe</a>`) }, 'x')   // a probe link placed in the page
  const target = await (async () => { const p2 = await browser.newPage(); await p2.goto(host.origin + '/docs/users/shortcuts', { waitUntil: 'networkidle0' }); const t = await p2.evaluate(() => [...document.querySelectorAll('h2[id]')].map((h) => h.id)[3]); await p2.close(); return t })()
  await page.evaluate((t) => { const a = document.getElementById('probe'); a.setAttribute('href', `/docs/users/shortcuts#${t}`) }, target)
  await page.evaluate(() => scrollTo(0, 400)); await sleep(150)
  await (await page.$('#probe')).click(); await sleep(1200)
  const w = await page.evaluate((t) => ({ path: location.pathname + location.hash, top: Math.round(document.getElementById(t)?.getBoundingClientRect().top ?? -1) }), target)
  check(w.top >= 0 && w.top < 260, `a link to a heading of another page puts the heading in view (#${target})`, JSON.stringify(w))
  await page.close()
}

{
  const page = await open()
  await sleep(4500)
  const jsons = page.__seen.filter((u) => /staticServerFnCache/.test(u)).length
  check(jsons >= 2, 'the previous and next pages are preloaded while idle (no click)', `${jsons} data files requested`)
  await page.close()
}

{
  const page = await open({ width: 390 })
  await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight)); await sleep(200)
  const all = await page.$$('a[href="/docs/users/install-and-update"]'); const el = last(all)
  await el.evaluate((e) => e.scrollIntoView({ block: 'center' })); await sleep(150)
  await el.click(); await sleep(1100)
  const w = await where(page)
  check(w.y === 0 && w.h1 === 'Install and update', 'on a phone the pager\'s Next also ends at the top', JSON.stringify(w))
  await page.close()
}

await browser.close(); host.stop()
if (bad) { console.error(`${bad} navigation check(s) failed`); process.exit(1) }
console.log('nav ok: every click ends at the top of its page, back/forward/anchors/slow loads behave')
