import { expect, test } from 'bun:test'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { forSite, syncDocs, validateDocs } from './sync-docs.mjs'

function fixture(files) {
  const root = mkdtempSync(join(tmpdir(), 'kmx-docs-'))
  for (const [rel, text] of Object.entries(files)) {
    const p = join(root, rel)
    mkdirSync(join(p, '..'), { recursive: true })
    writeFileSync(p, text)
  }
  return root
}
const page = (title, body = 'text') => `---\ntitle: ${title}\ndescription: about ${title}\n---\n\n${body}\n`

test('a valid tree yields the site URLs of its pages', () => {
  const root = fixture({
    'docs/index.mdx': page('Home'),
    'docs/users/index.mdx': page('Users'),
    'docs/users/a.mdx': page('A', 'see [home](/docs) and [b](/docs/users#top)'),
    'docs/meta.json': '{"pages":["index","users"]}',
    'docs/users/meta.json': '{"pages":["index","a"]}',
    'assets/x.png': 'png',
  })
  const { errors, pages } = validateDocs(join(root, 'docs'), join(root, 'assets'))
  expect(errors).toEqual([])
  expect(pages.sort()).toEqual(['/docs', '/docs/users', '/docs/users/a'])
})

test('a link to a page that does not exist names the file and line', () => {
  const root = fixture({ 'docs/index.mdx': page('Home', 'one\n\nbroken [x](/docs/gone)') })
  const { errors } = validateDocs(join(root, 'docs'), join(root, 'assets'))
  expect(errors.join('\n')).toContain('docs/index.mdx:8')
  expect(errors.join('\n')).toContain('/docs/gone')
})

test('a meta.json that lists a missing page fails', () => {
  const root = fixture({ 'docs/index.mdx': page('Home'), 'docs/meta.json': '{"pages":["index","renamed"]}' })
  expect(validateDocs(join(root, 'docs'), join(root, 'assets')).errors.join('\n')).toContain('renamed')
})

test('missing title, missing description and a missing image each fail', () => {
  const root = fixture({
    'docs/index.mdx': '---\ndescription: d\n---\n\nbody ![a](/assets/none.png)\n',
    'docs/b.mdx': '---\ntitle: B\n---\n\nbody\n',
  })
  const msg = validateDocs(join(root, 'docs'), join(root, 'assets')).errors.join('\n')
  expect(msg).toContain('title')
  expect(msg).toContain('description')
  expect(msg).toContain('/assets/none.png')
})

test('links inside fenced code blocks are not checked', () => {
  const root = fixture({ 'docs/index.mdx': page('Home', '```md\n[x](/docs/gone)\n```') })
  expect(validateDocs(join(root, 'docs'), join(root, 'assets')).errors).toEqual([])
})

test('links shown as inline code are not checked', () => {
  const root = fixture({ 'docs/index.mdx': page('Home', 'write `![alt](/assets/<file>)` or `[x](/docs/gone)`') })
  expect(validateDocs(join(root, 'docs'), join(root, 'assets')).errors).toEqual([])
})

test('sync copies pages, meta files and referenced assets, and throws on errors', () => {
  const root = fixture({ 'docs/index.mdx': page('Home', '![a](/assets/x.png)'), 'docs/meta.json': '{"pages":["index"]}', 'assets/x.png': 'png', 'assets/unused.gif': 'gif' })
  const out = join(root, 'out'), pub = join(root, 'pub')
  const { pages } = syncDocs({ docsDir: join(root, 'docs'), assetsDir: join(root, 'assets'), outDir: out, publicDir: pub })
  expect(pages).toEqual(['/docs'])
  expect(readFileSync(join(out, 'index.mdx'), 'utf8')).toContain('title: Home')
  expect(existsSync(join(out, 'meta.json'))).toBe(true)
  expect(existsSync(join(pub, 'assets', 'x.png'))).toBe(true)
  const bad = fixture({ 'docs/index.mdx': page('Home', '[x](/docs/gone)') })
  expect(() => syncDocs({ docsDir: join(bad, 'docs'), assetsDir: join(bad, 'assets'), outDir: join(bad, 'o'), publicDir: join(bad, 'p') })).toThrow(/gone/)
})

test('conf fences become ini in the site copy only, and only as a fence language', () => {
  expect(forSite('```conf\nx=1\n```\n  ```conf\n')).toBe('```ini\nx=1\n```\n  ```ini\n')
  expect(forSite('```config\n```conf-extra')).toBe('```config\n```conf-extra')
  expect(forSite('say conf here')).toBe('say conf here')
})
