import { expect, test } from 'bun:test'
import { FEATURED_KEYS, GLANCE_TEXT, facts, featuredGroups, featuredRows } from './facts'

test('every key the front page features still exists in the generated facts', () => {
  const all = new Set(facts.keys.flatMap((s) => s.rows.map((r) => r.key)))
  expect(FEATURED_KEYS.filter((k) => !all.has(k))).toEqual([])
  expect(featuredRows().map((r) => r.key)).toEqual(FEATURED_KEYS)
})

test('a featured key that was removed from the product is skipped, never invented', () => {
  const trimmed = { ...facts, keys: facts.keys.map((s) => ({ ...s, rows: s.rows.filter((r) => r.key !== 'ctrl+alt+y') })) }
  const keys = featuredRows(trimmed).map((r) => r.key)
  expect(keys).not.toContain('ctrl+alt+y')
  expect(keys.length).toBe(FEATURED_KEYS.length - 1)
})

test('the facts are not empty and every row has words', () => {
  expect(facts.chords).toBe(facts.keys.reduce((n, s) => n + s.rows.length, 0))
  expect(facts.chords).toBeGreaterThan(50)
  for (const s of facts.keys) for (const r of s.rows) expect(r.desc.trim().length, `${r.key} has no description`).toBeGreaterThan(2)
})

test('every featured chord has front-page wording, and no wording is left for a chord that is not featured', () => {
  expect(FEATURED_KEYS.filter((k) => !(k in GLANCE_TEXT))).toEqual([])
  expect(Object.keys(GLANCE_TEXT).filter((k) => !FEATURED_KEYS.includes(k))).toEqual([])
  for (const text of Object.values(GLANCE_TEXT)) expect(text).not.toMatch(/[`]|\(.*·.*\)/)
})

test('the three groups hold every featured chord once, in a sensible number', () => {
  const g = featuredGroups()
  expect(g.length).toBe(3)
  expect(g.flatMap((x) => x.rows.map((r) => r.key))).toEqual(FEATURED_KEYS)
  expect(new Set(FEATURED_KEYS).size).toBe(FEATURED_KEYS.length)
})
