import { expect, test } from 'bun:test'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { changelogIndex, keysIndex, pageIndexes } from './search-index'
import { SUGGESTIONS } from './suggestions'
import { facts } from './facts'
import raw from '@/generated/CHANGELOG.md?raw'

const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

test('every key chord is searchable and lands on its section', () => {
  const idx = keysIndex(facts.keys)
  const total = facts.keys.reduce((n, s) => n + s.rows.length, 0)
  expect(idx.structuredData.contents).toHaveLength(total)
  const ids = new Set(idx.structuredData.headings.map((h) => h.id))
  for (const c of idx.structuredData.contents) expect(ids.has(c.heading ?? '')).toBe(true)
  expect(idx.structuredData.contents[0].content).toContain(facts.keys[0].rows[0].key)
})

test('the changelog entries land on release headings that exist, with no markdown left in the text', () => {
  const idx = changelogIndex(raw)
  expect(idx.structuredData.contents.length).toBeGreaterThan(10)
  const ids = new Set(idx.structuredData.headings.map((h) => h.id))
  for (const c of idx.structuredData.contents) {
    expect(ids.has(c.heading ?? '')).toBe(true)
    expect(c.content).not.toMatch(/\*\*|`|\]\(/)
  }
  expect(idx.structuredData.headings.every((h) => h.id === `r-${slug(h.content)}`)).toBe(true)
})

test('the page entries point at anchors the front page has, and every entry has text', () => {
  for (const p of pageIndexes()) {
    expect(p.url).toMatch(/^\/#(faq|support|more-projects)$/)
    expect(p.structuredData.contents.length).toBeGreaterThan(0)
    for (const c of p.structuredData.contents) expect(c.content.trim().length).toBeGreaterThan(10)
  }
})

test('every suggested page exists', () => {
  for (const s of SUGGESTIONS) {
    const m = /^\/docs\/(.+)$/.exec(s.url)
    if (m) expect(existsSync(join(import.meta.dir, '../../content/docs', `${m[1]}.mdx`))).toBe(true)
    else expect(['/keys', '/changelog']).toContain(s.url)
  }
})
