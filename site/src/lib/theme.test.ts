import { expect, test } from 'bun:test'
import { resolveTheme } from './theme'

test('an unknown or missing stored theme falls back to System', () => {
  expect(resolveTheme('purple')).toBe('system')
  expect(resolveTheme(undefined)).toBe('system')
  expect(resolveTheme(null)).toBe('system')
  expect(resolveTheme('')).toBe('system')
})
test('the three real values pass through', () => {
  for (const t of ['system', 'light', 'dark']) expect(resolveTheme(t)).toBe(t as never)
})
