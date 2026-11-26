import { describe, expect, test } from 'bun:test'
import { readFileSync } from 'node:fs'
import { contrast, readTokens } from './contrast'

const css = readFileSync(new URL('../styles/tokens.css', import.meta.url), 'utf8')

// [foreground, background, minimum ratio, what it is]
const PAIRS: [string, string, number, string][] = [
  ['--fg', '--bg', 4.5, 'body text on the page'],
  ['--muted', '--bg', 4.5, 'secondary text on the page'],
  ['--fg', '--surface', 4.5, 'text on a card'],
  ['--muted', '--surface', 4.5, 'secondary text on a card'],
  ['--muted', '--surface-hi', 4.5, 'secondary text on a raised card'],
  ['--link', '--bg', 4.5, 'links on the page'],
  ['--link', '--surface', 4.5, 'links on a card'],
  ['--link', '--surface-hi', 4.5, 'links on a raised card'],
  ['--on-brand', '--brand', 4.5, 'text on the brand (cobalt) field'],
  ['--on-brand-soft', '--brand', 4.5, 'secondary text on the brand field'],
  ['--brand', '--on-brand', 4.5, 'brand-coloured text on a cream button'],
  ['--on-pink', '--pink', 4.5, 'text on a pink button'],
  ['--link', '--code-bg', 3, 'a link-coloured mark on code'],
  ['--code-fg', '--code-bg', 4.5, 'code'],
  ['--on-signal', '--signal', 4.5, 'text on a lantern-amber action'],
  ['--signal-ink', '--bg', 4.5, 'amber signal text on the page'],
  ['--signal-ink', '--surface', 4.5, 'amber signal text on a card'],
  ['--signal-ink', '--surface-hi', 4.5, 'amber signal text on a raised card'],
  ['--on-field', '--field', 4.5, 'text on the warm apricot field'],
  ['--field-muted', '--field', 4.5, 'secondary text on the warm apricot field'],
]

describe('theme contrast', () => {
  for (const selector of [':root', '.dark'] as const) {
    const tokens = readTokens(css, selector)
    test(`${selector} defines every token the pairs use`, () => {
      for (const [fg, bg] of PAIRS) {
        expect(tokens[fg], `${selector} ${fg}`).toBeDefined()
        expect(tokens[bg], `${selector} ${bg}`).toBeDefined()
      }
    })
    for (const [fg, bg, min, what] of PAIRS) {
      test(`${selector}: ${what} (${fg} on ${bg}) is at least ${min}:1`, () => {
        expect(contrast(tokens[fg], tokens[bg])).toBeGreaterThanOrEqual(min)
      })
    }
  }
  test('an unknown selector reads as empty, not as the other theme', () => {
    expect(readTokens(css, '.nope' as never)).toEqual({})
  })
})
