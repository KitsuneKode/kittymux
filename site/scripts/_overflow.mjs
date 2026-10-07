import puppeteer from 'puppeteer-core'
const [,, base, ...paths] = process.argv
const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome-stable', headless: 'new', args: ['--no-sandbox'] })
for (const path of paths) {
  const page = await browser.newPage()
  await page.setViewport({ width: 320, height: 800 })
  await page.evaluateOnNewDocument(() => { window.__ALL = true }); await page.goto(base + path, { waitUntil: 'networkidle0' })
  const out = await page.evaluate(() => {
    const w = window.innerWidth, res = []
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect()
      if (r.width && r.right > w + 1) {
        // skip if an ancestor clips/scrolls it
        let p = el.parentElement, clipped = false
        while (p && p !== document.body) { const cs = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(cs.overflowX)) { clipped = true; break } p = p.parentElement }
        if (!clipped || window.__ALL) res.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 70)} right=${Math.round(r.right)} w=${Math.round(r.width)}`)
      }
    }
    return [document.documentElement.scrollWidth, getComputedStyle(document.documentElement).overflowX, getComputedStyle(document.body).overflowX, ...res.slice(0, 10)]
  })
  console.log(path, out)
  await page.close()
}
await browser.close()
