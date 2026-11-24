import { expect, test } from 'bun:test'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pagePaths, parseChangelogFeed, robots, rss, siteBase, sitemap } from './gen-seo.mjs'

test('the base address is https only, without a trailing slash', () => {
  expect(siteBase(undefined)).toBe('')
  expect(siteBase('http://x.test')).toBe('')
  expect(siteBase('nonsense')).toBe('')
  expect(siteBase('https://x.test/')).toBe('https://x.test')
})

test('pages are found from the built files, error pages left out', () => {
  const dir = mkdtempSync(join(tmpdir(), 'kmx-seo-'))
  try {
    for (const f of ['index.html', 'docs/index.html', 'docs/users/a/index.html', 'keys/index.html', '404.html', 'assets/x.js']) { mkdirSync(join(dir, f, '..'), { recursive: true }); writeFileSync(join(dir, f), 'x') }
    expect(pagePaths(dir)).toEqual(['/', '/docs', '/docs/users/a', '/keys'])
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('sitemap and robots include lastmod, priority, and XML escaping', () => {
  const xml = sitemap(['/', '/docs', '/docs/users/guide', '/a&b'], 'https://x.test', '2026-11-24')
  expect(xml).toContain('<loc>https://x.test/</loc>')
  expect(xml).toContain('<priority>1.0</priority>')
  expect(xml).toContain('<loc>https://x.test/docs</loc>')
  expect(xml).toContain('<priority>0.9</priority>')
  expect(xml).toContain('<priority>0.8</priority>')
  expect(xml).toContain('<lastmod>2026-11-24</lastmod>')
  expect(xml).toContain('a&amp;b')
  expect(robots('https://x.test')).toContain('Sitemap: https://x.test/sitemap.xml')
  expect(robots('')).not.toContain('Sitemap')
  expect(robots('')).toContain('Allow: /')
})

test('rss feed parses changelog bullets into valid escaped RSS 2.0 XML', () => {
  const md = `## [Unreleased]\n### Added\n- **Pixel tab bar:** renders with Cairo & Slang (\`pxbar\`).\n### Fixed\n- Escape <angle> brackets in feeds.\n`
  const items = parseChangelogFeed(md, 10)
  expect(items).toHaveLength(2)
  expect(items[0].title).toBe('Pixel tab bar')
  expect(items[0].group).toBe('Added')
  const feed = rss(items, 'https://x.test', 'Tue, 24 Nov 2026 12:00:00 GMT')
  expect(feed).toContain('<rss version="2.0"')
  expect(feed).toContain('href="https://x.test/rss.xml"')
  expect(feed).toContain('<title>Pixel tab bar</title>')
  expect(feed).toContain('&amp; Slang')
  expect(feed).toContain('&lt;angle&gt;')
})
