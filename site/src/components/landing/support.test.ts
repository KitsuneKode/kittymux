import { expect, test } from 'bun:test'
import { sinceLabel } from './support'

test('the last-commit label is relative to the build day and says nothing for a date it cannot read', () => {
  const now = Date.parse('2026-10-10T12:00:00Z')
  expect(sinceLabel('2026-10-10T01:00:00Z', now)).toBe('today')
  expect(sinceLabel('2026-10-09T01:00:00Z', now)).toBe('yesterday')
  expect(sinceLabel('2026-10-05T12:00:00Z', now)).toBe('5 days ago')
  expect(sinceLabel(null, now)).toBeNull()
  expect(sinceLabel('nonsense', now)).toBeNull()
  expect(sinceLabel('2027-01-01T00:00:00Z', now)).toBeNull()   // a date in the future is a clock problem, not news
})
