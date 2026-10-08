// bun scripts/og.mjs: draws public/og.png (1200x630, the link preview) and public/apple-touch-icon.png (180x180) with headless Chrome,
// from the site's own screenshot and font. Run it when the headline or the screenshot changes, and commit the PNGs.
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import puppeteer from 'puppeteer-core'

const root = resolve(new URL('..', import.meta.url).pathname)
const font = pathToFileURL(join(root, 'node_modules/@fontsource-variable/epilogue/files/epilogue-latin-wght-normal.woff2')).href
const shot = pathToFileURL(join(root, 'public/assets/shots/panel-agents-light.png')).href
const tmp = mkdtempSync(join(tmpdir(), 'kmx-og-'))
const base = `@font-face{font-family:E;src:url(${font});font-weight:100 900}*{box-sizing:border-box;margin:0}body{font-family:E,system-ui,sans-serif;background:#B3261E;color:#F7F3EA}`
const og = `<!doctype html><meta charset=utf-8><style>${base}
body{width:1200px;height:630px;display:flex;align-items:center;padding:0 72px;gap:48px;position:relative;overflow:hidden}
.band{position:absolute;left:0;right:0;height:14px;background:repeating-linear-gradient(90deg,#F7F3EA 0 6px,transparent 6px 18px);opacity:.55}
.t{top:22px}.b{bottom:22px}
.l{flex:1}.mark{display:inline-grid;place-items:center;width:56px;height:56px;border-radius:14px;background:#F7F3EA;color:#B3261E;font-size:36px;font-weight:700}
h1{font-size:84px;line-height:1.02;letter-spacing:-.03em;margin-top:28px;max-width:11ch}
p{font-size:30px;line-height:1.3;margin-top:26px;color:#F5D6D2;max-width:22ch}
.shot{width:430px;border-radius:16px;box-shadow:0 30px 60px -20px rgba(0,0,0,.5);outline:1px solid rgba(0,0,0,.2)}</style>
<div class="band t"></div><div class="band b"></div>
<div class=l><span class=mark>k</span><h1>Know which agent needs you.</h1><p>kittymux turns kitty into a multiplexer for AI coding agents.</p></div>
<img class=shot src="${shot}" alt="">`
const icon = `<!doctype html><meta charset=utf-8><style>${base}body{width:180px;height:180px;background:#B3261E;display:grid;place-items:center;font-size:124px;font-weight:700;padding-bottom:10px}</style>k`
const browser = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/usr/bin/google-chrome-stable', headless: 'new', args: ['--no-sandbox', '--allow-file-access-from-files'] })
try {
  for (const [name, html, w, h] of [['og.png', og, 1200, 630], ['apple-touch-icon.png', icon, 180, 180]]) {
    const file = join(tmp, name + '.html')
    writeFileSync(file, html)
    const page = await browser.newPage()
    await page.setViewport({ width: w, height: h })
    await page.goto(pathToFileURL(file).href, { waitUntil: 'networkidle0' })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: join(root, 'public', name) })
    console.log(`wrote public/${name}`)
    await page.close()
  }
} finally { await browser.close(); rmSync(tmp, { recursive: true, force: true }) }
