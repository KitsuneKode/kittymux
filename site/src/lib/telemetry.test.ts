import { expect, test } from 'bun:test'
import { wantsNoTracking } from './telemetry'

test('Do Not Track and Global Privacy Control both mean "do not count me"', () => {
  expect(wantsNoTracking(undefined)).toBe(false)
  expect(wantsNoTracking({})).toBe(false)
  expect(wantsNoTracking({ doNotTrack: '0' })).toBe(false)
  expect(wantsNoTracking({ doNotTrack: null })).toBe(false)
  expect(wantsNoTracking({ doNotTrack: '1' })).toBe(true)
  expect(wantsNoTracking({ doNotTrack: 'yes' })).toBe(true)
  expect(wantsNoTracking({ globalPrivacyControl: true })).toBe(true)
  expect(wantsNoTracking({ globalPrivacyControl: false })).toBe(false)
})
