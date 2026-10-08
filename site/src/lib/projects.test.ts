import { expect, test } from 'bun:test'
import { PROJECTS } from './projects'

test('every project has a distinct name, an https address, a short plain blurb and a repository', () => {
  expect(new Set(PROJECTS.map((p) => p.name)).size).toBe(PROJECTS.length)
  expect(new Set(PROJECTS.map((p) => p.url)).size).toBe(PROJECTS.length)
  for (const p of PROJECTS) {
    expect(p.url.startsWith('https://')).toBe(true)
    expect(p.blurb.length).toBeGreaterThan(20)
    expect(p.blurb.length).toBeLessThanOrEqual(95)
    expect(p.blurb).not.toMatch(/!|\.\.\./)
    expect(p.repo).toMatch(/^[A-Za-z0-9._-]+$/)
  }
})
