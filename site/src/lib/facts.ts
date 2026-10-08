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
export const GROUPS: { title: string; keys: string[] }[] = [
  { title: 'See what needs you', keys: ['ctrl+alt+b', 'ctrl+alt+shift+b', 'ctrl+alt+y', 'ctrl+alt+shift+q'] },
  { title: 'Find and start', keys: ['ctrl+alt+shift+space', 'ctrl+alt+v', 'ctrl+alt+shift+o', 'ctrl+alt+/'] },
  { title: 'Move around', keys: ['ctrl+alt+e', 'ctrl+alt+1…9', 'alt+1…9', 'ctrl+alt+shift+y', 'alt+shift+h'] },
]
export const FEATURED_KEYS = GROUPS.flatMap((g) => g.keys)

/**
 * The key table on /keys shows each chord's own comment from the key template, which is written for the overlay inside kitty (terse, with
 * `code` and asides). On the front page every line is a sentence for someone who has not installed it yet. The chords still come from the template
 * (a chord that is gone is skipped); only the words are ours.
 */
export const GLANCE_TEXT: Record<string, string> = {
  'ctrl+alt+b': 'Open the sidebar deck: hover a tab to preview it, click to jump.',
  'ctrl+alt+shift+b': 'Dock the panel at the screen edge so it is always in view (Wayland).',
  'ctrl+alt+shift+space': 'Open the command palette: find a tab, an agent or an action by typing.',
  'ctrl+alt+y': 'Jump to the next agent waiting on you, longest wait first.',
  'ctrl+alt+e': 'Number every pane on screen, then press a digit to focus it.',
  'ctrl+alt+1…9': 'Focus pane 1 to 9 of this tab.',
  'alt+1…9': 'Jump to tab 1 to 9.',
  'alt+shift+h': 'Make the pane narrower by 3 columns. alt+shift+l makes it wider.',
  'ctrl+alt+shift+q': 'Take a quick look at the agent that has waited longest, without leaving this tab.',
  'ctrl+alt+v': 'Pick from one list: what needs you, every agent, closed conversations or a new agent.',
  'ctrl+alt+shift+o': 'Start spawn mode, then press c for Claude, x for Codex or d for Devin to open it in a new tab.',
  'ctrl+alt+/': 'Show every key, searchable, without leaving kitty.',
  'ctrl+alt+shift+y': 'Swap two panes: number every pane, then press the digit of the one to swap with.',
}

/** The featured rows in their three groups (a chord that is gone is skipped, and an emptied group disappears). */
export function featuredGroups(f: Facts = facts): { title: string; rows: KeyRow[] }[] {
  const have = new Map(featuredRows(f).map((r) => [r.key, r]))
  return GROUPS.map((g) => ({ title: g.title, rows: g.keys.flatMap((k) => (have.has(k) ? [have.get(k)!] : [])) })).filter((g) => g.rows.length > 0)
}

export function featuredRows(f: Facts = facts): KeyRow[] {
  const all = f.keys.flatMap((s) => s.rows)
  return FEATURED_KEYS.flatMap((k) => all.filter((r) => r.key === k).slice(0, 1)).map((r) => ({ ...r, desc: GLANCE_TEXT[r.key] ?? r.desc }))
}
