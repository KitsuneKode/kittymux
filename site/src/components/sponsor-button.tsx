import { SPONSOR_URL } from '@/lib/links';
import { cn } from '@/lib/utils';

/** Sponsor, always the same pink pill (the mascot's pink, with dark text that clears 4.5:1), so it reads as one thing wherever it sits: top right of every page, the end of each docs page, the footer. */
export function SponsorButton({ className, label = 'Sponsor', collapse = false }: { className?: string; label?: string; collapse?: boolean }) {
  return (
    <a
      href={SPONSOR_URL}
      target="_blank"
      rel="noopener"
      data-press=""
      className={cn(
        'inline-flex min-h-11 items-center gap-2 rounded-full bg-pink px-4 text-sm font-semibold text-onpink sm:min-h-10',
        collapse && 'max-[419px]:px-3',
        '[@media(hover:hover)_and_(pointer:fine)]:hover:bg-[color-mix(in_oklch,var(--pink),white_14%)]',
        className,
      )}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="h-[1.2cap] w-auto shrink-0">
        <path d="M6.979 3.074a6 6 0 0 1 4.988 1.425l.037.033.034-.03a6 6 0 0 1 4.733-1.44l.246.036a6 6 0 0 1 3.364 10.008l-.18.185-.048.041-7.45 7.379a1 1 0 0 1-1.313.082l-.094-.082-7.493-7.422A6 6 0 0 1 6.979 3.074Z" />
      </svg>
      <span className={collapse ? 'max-[419px]:sr-only' : undefined}>{label}</span>
    </a>
  );
}
