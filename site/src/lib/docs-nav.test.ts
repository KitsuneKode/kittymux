import { expect, test } from 'bun:test'
import { arrivedByHistory, neighbourUrls, splatOf } from './docs-nav'

const tree = {
  name: 'Docs',
  children: [
    { type: 'page', name: 'Overview', url: '/docs' },
    { type: 'folder', name: 'Guides', children: [{ type: 'page', name: 'A', url: '/docs/users/a' }, { type: 'page', name: 'B', url: '/docs/users/b' }, { type: 'page', name: 'C', url: '/docs/users/c' }] },
  ],
} as never

test('splatOf takes the part after /docs/ and nothing for /docs itself', () => {
  expect(splatOf('/docs/users/shortcuts')).toBe('users/shortcuts')
  expect(splatOf('/docs/users/shortcuts/')).toBe('users/shortcuts')
  expect(splatOf('/docs')).toBe('')                      // the overview is the empty splat of the same route: it is preloaded too
  expect(splatOf('/docs/')).toBe('')
  expect(splatOf('/keys')).toBeNull()
  expect(splatOf('/docsx/y')).toBeNull()
})

test('the pager neighbours are the pages before and after, in sidebar order', () => {
  expect(neighbourUrls(tree, '/docs/users/b')).toEqual(['/docs/users/a', '/docs/users/c'])
  expect(neighbourUrls(tree, '/docs/users/c')).toEqual(['/docs/users/b'])
  expect(neighbourUrls(tree, '/docs/users/a')).toEqual(['/docs', '/docs/users/b'])
})

test('an address that is not in the tree has no neighbours and does not throw', () => {
  expect(neighbourUrls(tree, '/docs/nope')).toEqual([])
  expect(neighbourUrls(null as never, '/docs/x')).toEqual([])
})

test('arriving by history is reported once and only soon after the pop', () => {
  expect(arrivedByHistory()).toBe(false)                    // no pop has happened
  expect(arrivedByHistory(Date.now() + 5000)).toBe(false)
})
