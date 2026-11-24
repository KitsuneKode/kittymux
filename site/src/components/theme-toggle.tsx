import { useTheme } from 'next-themes'
import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { resolveTheme } from '@/lib/theme'

const CHOICES = [
  { value: 'system', label: 'System', d: 'M3 5a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5Zm4 15h10m-8-4v4m6-4v4' },
  { value: 'light', label: 'Light', d: 'M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0M3 12h1m8-9v1m8 8h1m-9 8v1M5.6 5.6l.7.7m12.1-.7-.7.7m0 11.4.7.7m-12.1-.7-.7.7' },
  { value: 'dark', label: 'Dark', d: 'M12 3h.393a7.5 7.5 0 0 0 7.92 12.446A9 9 0 1 1 12 2.992Z' },
] as const

/** System / Light / Dark. Nothing is marked until mounted, so the server HTML and the first client render agree. */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const current = resolveTheme(theme)
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    const to = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (i + 1) % CHOICES.length : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? (i + CHOICES.length - 1) % CHOICES.length : e.key === 'Home' ? 0 : e.key === 'End' ? CHOICES.length - 1 : -1
    if (to < 0) return
    e.preventDefault()
    setTheme(CHOICES[to].value)
    refs.current[to]?.focus()
  }
  return (
    <div role="radiogroup" aria-label="Colour theme" className={cn(!className?.includes('hidden') && 'inline-flex', 'rounded-full bg-card-hi p-1', className)}>
      {CHOICES.map(({ value, label, d }, i) => {
        const on = mounted && current === value
        return (
          <button
            key={value}
            ref={(el) => { refs.current[i] = el }}
            tabIndex={(mounted ? current : 'system') === value ? 0 : -1}
            onKeyDown={(e) => onKeyDown(e, i)}
            type="button"
            role="radio"
            aria-checked={on}
            aria-label={label}
            title={label}
            onClick={() => setTheme(value)}
            data-press=""
            className={cn(
              'grid size-9 place-items-center rounded-full text-mute sm:size-8',
              on
                ? 'bg-card text-ink shadow-[0_0_0_1px_color-mix(in_oklch,var(--fg)_8%,transparent),0_1px_2px_color-mix(in_oklch,var(--fg)_12%,transparent)] dark:bg-[color-mix(in_oklch,var(--fg)_16%,var(--surface-hi))] dark:shadow-[0_0_0_0.5px_color-mix(in_oklch,var(--fg)_30%,transparent),0_1px_2px_rgb(0_0_0/0.5)]'
                : 'hover:text-ink',
            )}
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className="size-4">
              <path d={d} />
            </svg>
          </button>
        )
      })}
    </div>
  )
}
