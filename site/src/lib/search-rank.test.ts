import { expect, test } from 'bun:test'
import { promoteTitles } from './search-rank'

const page = (id: string, content: string) => ({ id, type: 'page', content })
const text = (id: string, content: string) => ({ id, type: 'text', content })

test('a page whose title is the query goes first, with its own hits, and the rest keep their order', () => {
  const items = [page('a', 'Sessions and restore'), text('a1', 'the <mark>keys</mark> saved'), page('b', 'Shortcuts'), page('k', '<mark>Keys</mark>'), text('k1', 'ctrl+alt+b')]
  expect(promoteTitles(items, 'keys').map((i) => i.id)).toEqual(['k', 'k1', 'a', 'a1', 'b'])
})

test('a title that contains the query comes after an exact one and before the others', () => {
  const items = [page('x', 'Install'), page('y', 'Install and update'), page('z', 'Install')]
  expect(promoteTitles(items, 'install and').map((i) => i.id)).toEqual(['y', 'x', 'z'])
  expect(promoteTitles([page('p', 'Privacy and security'), page('i', 'Install')], 'install').map((i) => i.id)).toEqual(['i', 'p'])
})

test('an empty query, no results, or results that do not start with a page change nothing', () => {
  expect(promoteTitles([], 'a')).toEqual([])
  const items = [text('t', 'x'), page('p', 'P')]
  expect(promoteTitles(items, '')).toBe(items)
  expect(promoteTitles(items, 'zz').map((i) => i.id)).toEqual(['t', 'p'])
})
