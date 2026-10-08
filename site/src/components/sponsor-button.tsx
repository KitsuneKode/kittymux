import { IconHeartFilled } from '@tabler/icons-react';
import { SPONSOR_URL } from '@/lib/links';
import { cn } from '@/lib/utils';

/** Sponsor, always the same pink pill (the mascot's pink, with dark text that clears 4.5:1), so it reads as one thing wherever it sits: top right of every page, the end of each docs page, the footer. */
export function SponsorButton({ className, label = 'Sponsor' }: { className?: string; label?: string }) {
  return (
    <a
      href={SPONSOR_URL}
      target="_blank"
      rel="noopener"
      data-press=""
      className={cn(
        'inline-flex min-h-11 items-center gap-2 rounded-full bg-pink px-4 text-sm font-semibold text-onpink max-[419px]:px-3 sm:min-h-10',
        '[@media(hover:hover)_and_(pointer:fine)]:hover:bg-[color-mix(in_oklch,var(--pink),white_14%)]',
        className,
      )}
    >
      <IconHeartFilled aria-hidden="true" className="h-[1.2cap] w-auto shrink-0" />
      <span className="max-[419px]:sr-only">{label}</span>
    </a>
  );
}
