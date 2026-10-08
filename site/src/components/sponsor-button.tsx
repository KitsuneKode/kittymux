import { IconHeartFilled } from '@tabler/icons-react';
import { SPONSOR_URL } from '@/lib/links';
import { cn } from '@/lib/utils';

/** Sponsor, always the same pink pill (the mascot's pink, with dark text that clears 4.5:1), so it reads as one thing wherever it sits: top right of every page, the end of each docs page, the footer. `collapse` is for a tight header: under 420 px it shows only the heart (the label stays for screen readers); everywhere else there is room for the word, and a lone heart says nothing. */
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
      <IconHeartFilled aria-hidden="true" className="h-[1.2cap] w-auto shrink-0" />
      <span className={collapse ? 'max-[419px]:sr-only' : undefined}>{label}</span>
    </a>
  );
}
