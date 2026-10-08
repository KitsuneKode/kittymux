// bun scripts/cls.mjs <build dir>: cumulative layout shift while a page loads AND while you move between pages, per page, theme and width; names the elements that moved.
// Fails above 0.02 on any load or navigation (Google's "good" is 0.1; this site is mostly static text and has no reason to come close).
import puppeteer from 'puppeteer-core'
import { serve } from './_host.mjs'

const dir = process.argv[2]
const LIMIT = Number(process.env.CLS_LIMIT ?? 0.02)
const host = serve(dir)
let browser
let bad = 0

const OBSERVE = `(() => {
  window.__shifts = []
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.hadRecentInput) continue
      window.__shifts.push({ v: e.value, t: Math.round(e.startTime), nodes: (e.sources || []).map((s) => { const n = s.node; return n ? (n.nodeName.toLowerCase() + (n.id ? '#' + n.id : '') + (n.className && typeof n.className === 'string' ? '.' + n.className.split(' ').slice(0, 2).join('.') : '')) : '?' }) })
    }
  }).observe({ type: 'layout-shift', buffered: true })
})()`

async function measure(page, label, wait = 1200) {
  await new Promise((r) => setTimeout(r, wait))
  const shifts = await page.evaluate(() => window.__shifts)
  const total = shifts.reduce((n, s) => n + s.v, 0)
  const worst = shifts.sort((a, b) => b.v - a.v).slice(0, 3).map((s) => `${s.v.toFixed(3)}@${s.t}ms ${s.nodes.slice(0, 3).join(' ')}`)
  console.log(`${total <= LIMIT ? 'ok ' : 'BAD'} ${total.toFixed(3)}  ${label}${worst.length && total > 0.001 ? '\n      ' + worst.join('\n      ') : ''}`)
  if (total > LIMIT) bad++
}

try {
  browser = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/usr/bin/google-chrome-stable', headless: 'new', args: ['--no-sandbox'] })
  for (const [width, mobile] of [[1440, false], [390, true]]) {
    for (const scheme of ['light', 'dark']) {
      for (const path of ['/', '/docs/users/getting-started', '/keys', '/changelog']) {
        const page = await browser.newPage()
        await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
        await page.setViewport({ width, height: 900, isMobile: mobile, hasTouch: mobile })
        await page.evaluateOnNewDocument(OBSERVE)
        await page.goto(`${host.origin}${path}`, { waitUntil: 'load' })
        await measure(page, `load ${path} ${width}px ${scheme}`)
        await page.close()
      }
      // a slow first visit: nothing cached, ~1.6 Mbit/s and 300 ms latency, so the web fonts and images arrive AFTER the first paint (the swap is where text shifts)
      for (const path of ['/', '/docs/users/getting-started', '/changelog']) {
        const page = await browser.newPage()
        await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
        await page.setViewport({ width, height: 900, isMobile: mobile, hasTouch: mobile })
        const cdp = await page.createCDPSession()
        await cdp.send('Network.enable')
        await cdp.send('Network.setCacheDisabled', { cacheDisabled: true })
        await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 300, downloadThroughput: 200 * 1024, uploadThroughput: 100 * 1024 })
        await page.evaluateOnNewDocument(OBSERVE)
        await page.goto(`${host.origin}${path}`, { waitUntil: 'load', timeout: 60000 })
        await measure(page, `SLOW load ${path} ${width}px ${scheme}`, 5000)
        await page.close()
      }
      // moving between pages in the same tab (client-side): home -> docs -> another docs page -> keys
      const page = await browser.newPage()
      await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: scheme }])
      await page.setViewport({ width, height: 900, isMobile: mobile, hasTouch: mobile })
      await page.evaluateOnNewDocument(OBSERVE)
      await page.goto(`${host.origin}/`, { waitUntil: 'networkidle0' })
      await page.evaluate(() => { window.__shifts.length = 0 })
      const hop = async (selector, label) => {
        await page.evaluate(() => { window.__shifts.length = 0 })
        const el = await page.$(selector)
        if (!el) { console.log(`skip ${label}: no ${selector}`); return }
        await el.click()
        await measure(page, `navigate ${label} ${width}px ${scheme}`)
      }
      await hop('a[href="/docs"]', 'home -> docs')
      await hop('a[href="/docs/users/shortcuts"]', 'docs -> docs')
      await page.close()
    }
  }
} finally { await browser?.close(); host.stop() }
process.exit(bad ? 1 : 0)
