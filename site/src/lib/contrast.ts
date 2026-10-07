/** WCAG 2.x relative luminance and contrast ratio for #RRGGBB colours. */
const channel = (c: number) => {
  const s = c / 255
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) throw new Error(`contrast: not a #RRGGBB colour: ${hex}`)
  const n = parseInt(m[1], 16)
  return 0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

/** The `--name: #hex` declarations of one top-level rule (`:root` or `.dark`). Other value forms are ignored. */
export function readTokens(css: string, selector: ':root' | '.dark'): Record<string, string> {
  const escaped = selector.replace(/[.:]/g, '\\$&')
  const block = new RegExp(`(?:^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(css)
  if (!block) return {}
  const out: Record<string, string> = {}
  for (const m of block[1].matchAll(/(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)) out[m[1]] = m[2]
  return out
}
