// bun scripts/gen-og.mjs: renders a crisp 1200x630 /og.png social preview card in the Lantern cobalt/cream/amber palette.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import puppeteer from 'puppeteer-core'

const ROOT = new URL('..', import.meta.url).pathname
const pub = join(ROOT, 'public')
const b64 = (rel, mime) => `data:${mime};base64,${readFileSync(join(ROOT, rel)).toString('base64')}`

const bricolage = b64('node_modules/@fontsource-variable/bricolage-grotesque/files/bricolage-grotesque-latin-wght-normal.woff2', 'font/woff2')
const geist = b64('node_modules/@fontsource-variable/geist/files/geist-latin-wght-normal.woff2', 'font/woff2')
const mono = b64('node_modules/@fontsource-variable/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2', 'font/woff2')
const cosmos = b64('public/brand/art/cosmos-rays.webp', 'image/webp')
const mascot = b64('public/brand/mascot-cutout.webp', 'image/webp')
const avatar = b64('public/brand/mascot-avatar-128.png', 'image/png')
const workspace = b64('public/assets/shots/workspace-dark.png', 'image/png')
const agents = ['claude', 'codex', 'devin', 'cursor', 'opencode', 'gemini', 'antigravity', 'goose'].map((id) =>
  b64(`public/brand/agents/${id}.png`, 'image/png'),
)

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>
  @font-face { font-family: 'Bricolage'; src: url('${bricolage}') format('woff2-variations'); font-weight: 200 800; }
  @font-face { font-family: 'Geist'; src: url('${geist}') format('woff2-variations'); font-weight: 100 900; }
  @font-face { font-family: 'JBMono'; src: url('${mono}') format('woff2-variations'); font-weight: 100 800; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1200px; height: 630px; overflow: hidden;
    background: #1C3A8E; color: #FFF6E8;
    font-family: 'Geist', sans-serif;
    position: relative;
  }
  .bg {
    position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover;
    opacity: 0.72; filter: saturate(1.08);
  }
  .veil {
    position: absolute; inset: 0;
    background:
      linear-gradient(96deg, rgba(11, 13, 28, 0.94) 0%, rgba(11, 13, 28, 0.84) 46%, rgba(28, 58, 142, 0.38) 100%);
  }
  .wrap {
    position: relative; z-index: 2; height: 100%;
    display: grid; grid-template-columns: 560px 1fr; align-items: center;
    padding: 46px 52px; gap: 36px;
  }
  .brand {
    display: flex; align-items: center; gap: 14px;
  }
  .brand img {
    width: 48px; height: 48px; border-radius: 12px;
    box-shadow: 0 0 0 1px rgba(255,246,232,0.2), 0 8px 20px rgba(0,0,0,0.45);
  }
  .brand span {
    font-family: 'JBMono', monospace; font-size: 28px; font-weight: 800; letter-spacing: -0.03em; color: #FFF6E8;
  }
  .brand .mux { color: #FF8FAB; }
  h1 {
    font-family: 'Bricolage', sans-serif;
    font-size: 64px; line-height: 1.02; letter-spacing: -0.04em; font-weight: 780;
    margin-top: 26px; color: #FFF6E8;
  }
  .sig {
    display: inline-block; padding: 2px 12px 6px; border-radius: 12px;
    background: #F6C453; color: #15172E;
  }
  .sub {
    margin-top: 20px; font-size: 21px; line-height: 1.48; color: #F2D6AC; max-width: 480px;
  }
  .agents {
    display: flex; align-items: center; gap: 10px; margin-top: 28px;
  }
  .agents img {
    width: 40px; height: 40px; border-radius: 9px;
    box-shadow: 0 0 0 1px rgba(255,246,232,0.16), 0 4px 12px rgba(0,0,0,0.45);
  }
  .url {
    margin-top: 24px; font-family: 'JBMono', monospace; font-size: 16px; color: #FF8FAB; letter-spacing: -0.01em;
  }
  .stage {
    position: relative; height: 492px;
    display: flex; align-items: center;
  }
  .mascot {
    position: absolute; bottom: -26px; right: -22px; width: 132px; height: auto; z-index: 4;
    filter: drop-shadow(0 12px 26px rgba(0,0,0,0.55));
  }
  .shot-frame {
    width: 630px; height: 430px; overflow: hidden; border-radius: 18px;
    background: #0B0D1C;
    border: 1px solid rgba(255, 246, 232, 0.22);
    box-shadow: 0 28px 70px rgba(0,0,0,0.68), 0 0 0 1px rgba(255,255,255,0.08);
    position: relative; z-index: 2;
  }
  .shot-frame img {
    width: 112%; height: 100%; object-fit: cover; object-position: left top; display: block;
  }
</style>
</head>
<body>
  <img class="bg" src="${cosmos}" alt="" />
  <div class="veil"></div>
  <div class="wrap">
    <div>
      <div class="brand">
        <img src="${avatar}" alt="" />
        <span>kitty<span class="mux">mux</span></span>
      </div>
      <h1>Know which agent <span class="sig">needs you.</span></h1>
      <p class="sub">Pixel tab bar, multi-account usage, inbox, and live hooks inside kitty.</p>
      <div class="agents">
        ${agents.map((src) => `<img src="${src}" alt="" />`).join('')}
      </div>
      <div class="url">kittymux.kitsunekode.in</div>
    </div>
    <div class="stage">
      <div class="shot-frame">
        <img src="${workspace}" alt="" />
      </div>
      <img class="mascot" src="${mascot}" alt="" />
    </div>
  </div>
</body>
</html>`

const CHROME = process.env.CHROME ?? '/usr/bin/google-chrome-stable'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
try {
  const page = await browser.newPage()
  await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 1 })
  await page.setContent(html, { waitUntil: 'networkidle0' })
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({ path: join(pub, 'og.png'), type: 'png' })
  console.log('wrote', join(pub, 'og.png'))
} finally {
  await browser.close()
}
