import { IconDeviceDesktop, IconMoon, IconSun } from '@tabler/icons-react'
import { useTheme } from 'next-themes'
import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/cn'
import { resolveTheme } from '@/lib/theme'

const CHOICES = [
  { value: 'system', label: 'System', Icon: IconDeviceDesktop },
  { value: 'light', label: 'Light', Icon: IconSun },
  { value: 'dark', label: 'Dark', Icon: IconMoon },
] as const

/** System / Light / Dark. Nothing is marked until mounted, so the server HTML and the first client render agree. */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const current = resolveTheme(theme)
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  // a radio group is one tab stop; the arrow keys move between its choices (and choose them), Home and End jump to the ends
  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    const to = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (i + 1) % CHOICES.length : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? (i + CHOICES.length - 1) % CHOICES.length : e.key === 'Home' ? 0 : e.key === 'End' ? CHOICES.length - 1 : -1
    if (to < 0) return
    e.preventDefault()
    setTheme(CHOICES[to].value)
    refs.current[to]?.focus()
  }
  return (
    <div role="radiogroup" aria-label="Colour theme" className={cn('inline-flex rounded-full border border-line p-0.5', className)}>
      {CHOICES.map(({ value, label, Icon }, i) => {
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
            className={cn(
              'grid size-9 place-items-center rounded-full text-mute transition-colors duration-150 [transition-timing-function:var(--ease)] sm:size-8',
              on ? 'bg-ink text-page' : 'hover:text-ink',
            )}
          >
            <Icon aria-hidden="true" className="size-4" stroke={1.75} />
          </button>
        )
      })}
    </div>
  )
}
