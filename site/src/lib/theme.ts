export const THEMES = ['system', 'light', 'dark'] as const
export type Theme = (typeof THEMES)[number]

/** Anything but the three known values (a stale or hand-edited localStorage entry) counts as System. */
export function resolveTheme(stored: string | undefined | null): Theme {
  return (THEMES as readonly string[]).includes(stored ?? '') ? (stored as Theme) : 'system'
}
