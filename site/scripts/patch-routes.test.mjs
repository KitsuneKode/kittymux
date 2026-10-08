import { expect, test } from 'bun:test'
import { HASHED, UNHASHED, patchRoutes } from './patch-routes.mjs'

const base = { routes: [{ headers: { 'cache-control': 'public, max-age=31536000, immutable' }, src: '/assets/(.*)' }, { handle: 'filesystem' }, { src: '/(.*)', dest: '/__server' }] }

test('immutable caching narrows to content-hashed files; other assets get a short rule', () => {
  const { config, changed } = patchRoutes(base)
  expect(changed).toBe(true)
  expect(config.routes[0].src).toBe(HASHED)
  expect(config.routes[1].headers['cache-control']).toContain('max-age=86400')
  expect(config.routes[1].continue).toBe(true)
  expect(config.routes[2]).toEqual({ handle: 'filesystem' })
  const hashed = new RegExp(`^${HASHED}$`)
  for (const yes of ['/assets/index-CPW22bKk.js', '/assets/app-CLHtRzcl.css', '/assets/epilogue-latin-wght-normal-Ab12_xyZ.woff2', '/assets/docs._-DtSUn0-s.js']) expect(hashed.test(yes)).toBe(true)
  const unhashed = new RegExp(`^${UNHASHED}$`)
  for (const yes of ['/assets/index-CPW22bKk.js', '/assets/docs._-DtSUn0-s.js']) expect(unhashed.test(yes)).toBe(false)
  for (const yes of ['/assets/status.png', '/assets/where-is-this-tab.png', '/assets/shots/manifest.json']) expect(unhashed.test(yes)).toBe(true)
  for (const no of ['/assets/status.png', '/assets/shots/panel-agents-light.png', '/assets/panes-layout-dark.png', '/assets/shots/manifest.json', '/assets/where-is-this-tab.png', '/assets/shots/panes-equalized-dark.png']) expect(hashed.test(no)).toBe(false)
})

test('header-only rules continue to the next rule; routes that serve things do not', () => {
  const { config } = patchRoutes({ routes: [{ headers: { 'cache-control': 'public, max-age=31536000, immutable' }, src: '/assets/(.*)' }, { src: '/x', headers: { a: 'b' } }, { handle: 'filesystem' }, { src: '/(.*)', dest: '/__server' }] })
  for (const r of config.routes.filter((r) => r.headers)) expect(r.continue).toBe(true)
  expect(config.routes.at(-1).continue).toBeUndefined()
  expect(config.routes.find((r) => r.handle).continue).toBeUndefined()
})

test('a preset that no longer writes the rule is an error, not a silent pass', () => {
  expect(patchRoutes({ routes: [{ handle: 'filesystem' }] }).changed).toBe(false)
})
