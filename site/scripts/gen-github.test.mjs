import { expect, test } from 'bun:test'
import { parseStars } from './gen-github.mjs'

test('a star count is a non-negative integer, anything else is "unknown"', () => {
  expect(parseStars({ stargazers_count: 41 })).toBe(41)
  expect(parseStars({ stargazers_count: 0 })).toBe(0)
  for (const bad of [undefined, null, {}, { stargazers_count: '41' }, { stargazers_count: -1 }, { stargazers_count: 1.5 }]) expect(parseStars(bad)).toBeNull()
})
