import { expect, test } from 'bun:test'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pagePaths, robots, siteBase, sitemap } from './gen-seo.mjs'

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

test('sitemap and robots', () => {
  const xml = sitemap(['/', '/docs', '/a&b'], 'https://x.test')
  expect(xml).toContain('<loc>https://x.test/</loc>')
  expect(xml).toContain('<loc>https://x.test/docs</loc>')
  expect(xml).toContain('a&amp;b')
  expect(robots('https://x.test')).toContain('Sitemap: https://x.test/sitemap.xml')
  expect(robots('')).not.toContain('Sitemap')
  expect(robots('')).toContain('Allow: /')
})
