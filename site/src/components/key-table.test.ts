import { expect, test } from 'bun:test'
import { filterKeys } from './key-table'

const keys = [
  { section: 'TABS', rows: [{ key: 'alt+1…9', desc: 'session-scoped tab nav' }, { key: 'alt+0', desc: 'jump to the LAST tab' }] },
  { section: 'PANES', rows: [{ key: 'ctrl+alt+1…9', desc: 'focus pane' }] },
]

test('an empty filter shows everything', () => expect(filterKeys(keys, '  ')).toEqual(keys))
test('every word must match, in any of section, key or description', () => {
  expect(filterKeys(keys, 'tab last').flatMap((s) => s.rows.map((r) => r.key))).toEqual(['alt+0'])
  expect(filterKeys(keys, 'panes ctrl')[0].rows).toHaveLength(1)
})
test('no match yields no sections, and the filter is case-insensitive', () => {
  expect(filterKeys(keys, 'zzzz')).toEqual([])
  expect(filterKeys(keys, 'LAST')).toHaveLength(1)
})
