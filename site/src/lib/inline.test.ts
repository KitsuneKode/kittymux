import { expect, test } from 'bun:test'
import { parseInline, parseChangelog } from './inline'

test('plain text, bold, code and links become typed parts', () => {
  expect(parseInline('a **b** `c` [d](https://e.test) f')).toEqual([
    { t: 'text', v: 'a ' }, { t: 'bold', v: 'b' }, { t: 'text', v: ' ' }, { t: 'code', v: 'c' }, { t: 'text', v: ' ' },
    { t: 'link', v: 'd', href: 'https://e.test' }, { t: 'text', v: ' f' },
  ])
})

test('an unclosed marker stays literal text', () => {
  expect(parseInline('half **bold and `code')).toEqual([{ t: 'text', v: 'half **bold and `code' }])
})

test('a repo-relative docs link becomes a site link; an unknown relative link becomes plain text', () => {
  expect(parseInline('[guide](docs/users/peek-deck-and-panel.mdx)')).toEqual([{ t: 'link', v: 'guide', href: '/docs/users/peek-deck-and-panel' }])
  expect(parseInline('[x](tests/smoke.sh)')).toEqual([{ t: 'text', v: 'x' }])
})

test('javascript: and other schemes are never links', () => {
  expect(parseInline('[x](javascript:alert(1))')).toEqual([{ t: 'text', v: 'x' }])
})

test('the changelog splits into releases, groups and items, joining wrapped lines', () => {
  const md = '# Changelog\n\nintro\n\n## [Unreleased]\n\n### Added\n- **One.** first\n  continued\n- Two\n\n### Fixed\n- Three\n\n## [1.0.0] - 2026-01-01\n\n### Added\n- Old\n'
  const out = parseChangelog(md)
  expect(out.map((r) => r.heading)).toEqual(['Unreleased', '1.0.0 · 2026-01-01'])
  expect(out[0].groups.map((g) => [g.name, g.items])).toEqual([['Added', ['**One.** first continued', 'Two']], ['Fixed', ['Three']]])
})

test('a file with no releases is an error, not an empty page', () => {
  expect(() => parseChangelog('# Changelog\n\njust prose\n')).toThrow(/no "## " release/)
})
