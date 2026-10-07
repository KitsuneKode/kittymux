import { cn } from '@/lib/cn';

/** The woven border: a row of diamonds between two threads. One SVG pattern; decorative only. */
export function WeaveBand({ id, className }: { id: string; className?: string }) {
  const pid = `weave-${id}`;
  return (
    <svg aria-hidden="true" focusable="false" className={cn('block h-3 w-full', className)}>
      <defs>
        <pattern id={pid} width="12" height="12" patternUnits="userSpaceOnUse">
          <path d="M6 2 L10 6 L6 10 L2 6 Z" fill="var(--red)" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="var(--bg)" />
      <rect width="100%" height="100%" fill={`url(#${pid})`} />
      <rect width="100%" height="1" fill="var(--red)" />
      <rect y="11" width="100%" height="1" fill="var(--red)" />
    </svg>
  );
}
