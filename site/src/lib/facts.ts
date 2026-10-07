import raw from '../generated/facts.json'

export type KeyRow = { key: string; desc: string }
export type Facts = {
  version: string
  keys: { section: string; rows: KeyRow[] }[]
  chords: number
  agents: { id: string; name: string; resumable: boolean }[]
  states: { id: string; glyph: string; title: string; meaning: string }[]
  features: { id: string; default: boolean; live: boolean; summary: string }[]
}
export const facts = raw as Facts

/** Chords worth showing on the front page, in this order; any that no longer exist are skipped (the list never invents a key). */
export const FEATURED_KEYS = [
  'ctrl+alt+b', 'ctrl+alt+shift+b', 'ctrl+alt+shift+space', 'ctrl+alt+y', 'ctrl+alt+e', 'ctrl+alt+1…9',
  'alt+1…9', 'alt+shift+h', 'ctrl+alt+shift+q', 'ctrl+alt+v', 'ctrl+alt+shift+o', 'ctrl+alt+/',
]

export function featuredRows(f: Facts = facts): KeyRow[] {
  const all = f.keys.flatMap((s) => s.rows)
  return FEATURED_KEYS.flatMap((k) => all.filter((r) => r.key === k).slice(0, 1))
}
