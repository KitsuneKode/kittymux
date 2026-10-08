import { expect, test } from 'bun:test'
import { buildLabel } from './site-footer'

test('a version tag stays as it is, a bare commit becomes "build …", dirty is dropped', () => {
  expect(buildLabel('v1.2.0')).toBe('v1.2.0')
  expect(buildLabel('v1.2.0-3-gabc1234')).toBe('v1.2.0-3-gabc1234')
  expect(buildLabel('adac42e')).toBe('build adac42e')
  expect(buildLabel('adac42e-dirty')).toBe('build adac42e')
  expect(buildLabel('unknown')).toBe('unknown')
})
