import { afterAll, expect, test } from 'bun:test'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { crawl } from './check-site.mjs'

const html = (body, head = '<title>T</title><meta name="description" content="d">') => `<!doctype html><html lang="en"><head>${head}</head><body>${body}</body></html>`
const made = []
afterAll(() => { for (const d of made) rmSync(d, { recursive: true, force: true }) })   // /tmp filled up with 'kmx-' directories
function site(files) {
  const dir = mkdtempSync(join(tmpdir(), 'kmx-site-'))
  made.push(dir)
  for (const [rel, text] of Object.entries(files)) { const p = join(dir, rel); mkdirSync(join(p, '..'), { recursive: true }); writeFileSync(p, text) }
  return dir
}

test('a healthy two-page site passes', () => {
  const dir = site({ 'index.html': html('<h1>Home</h1><a href="/docs">d</a><a href="/docs#x">x</a>'), 'docs/index.html': html('<h1>Docs</h1><h2 id="x">x</h2><img src="/a.png">'), 'a.png': 'png' })
  const r = crawl(dir, 2)
  expect(r.errors).toEqual([])
  expect(r.pages).toBe(2)
})

test('a dead link, a dead anchor, a missing image, two h1, no title and no lang are each reported', () => {
  const dir = site({
    'index.html': '<!doctype html><html><head></head><body><h1>a</h1><h1>b</h1><a href="/gone">g</a><a href="/docs#nope">n</a><img src="/none.png"></body></html>',
    'docs/index.html': html('<h1>Docs</h1>'),
  })
  const msg = crawl(dir, 2).errors.join('\n')
  for (const needle of ['/gone', '#nope', '/none.png', 'h1', '<title>', 'lang']) expect(msg).toContain(needle)
})

test('external links and mailto are not followed', () => {
  const dir = site({ 'index.html': html('<h1>x</h1><a href="https://example.com/x">e</a><a href="mailto:a@b.c">m</a>') })
  expect(crawl(dir, 1).errors).toEqual([])
})

test('the page count must match, so a page that silently stopped being built is caught', () => {
  const dir = site({ 'index.html': html('<h1>x</h1>') })
  expect(crawl(dir, 30).errors.join('\n')).toContain('expected 30 pages')
})

test('an empty h1 in the static html is an error: the page must be readable without JavaScript', () => {
  const dir = site({ 'index.html': html('<h1></h1><p>text</p>') })
  expect(crawl(dir, 1).errors.join('\n')).toContain('h1')
})

test('a link to a static file (llms.txt) is fine', () => {
  const dir = site({ 'index.html': html('<h1>x</h1><a href="/llms.txt">l</a>'), 'llms.txt': 'x' })
  expect(crawl(dir, 1).errors).toEqual([])
})

test('an empty html file is reported by name instead of as four missing tags', () => {
  const dir = site({ 'index.html': html('<h1>x</h1>'), 'docs/index.html': '' })
  const msg = crawl(dir, 2).errors.join('\n')
  expect(msg).toContain('/docs: the file is EMPTY')
  expect(msg).not.toContain('no <title>')
})
