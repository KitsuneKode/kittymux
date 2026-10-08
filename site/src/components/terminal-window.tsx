import manifest from '../../public/assets/shots/manifest.json';
import { cn } from '@/lib/cn';

type Size = { width: number; height: number };
const sizes = manifest as Record<string, Size>;

/**
 * A real screenshot, once per theme; the other theme's is hidden. Width and height are the real ones, so nothing shifts.
 * `priority` (the first screen): the light one loads at once and is preloaded; the dark one stays lazy, so a light visitor never downloads it, and a dark visitor's
 * starts as soon as the page is laid out (it is in view). Marking both eager sent both on every visit.
 */
export function Shot({ name, alt, priority = false, className }: { name: string; alt: string; priority?: boolean; className?: string }) {
  const dark = sizes[`${name}-dark.png`];
  const light = sizes[`${name}-light.png`] ?? dark;
  if (!dark) throw new Error(`Shot: no screenshot named ${name}-dark.png in the manifest (run tools/build-site-assets.sh)`);
  const common = { decoding: 'async' as const, alt };
  return (
    <>
      <img {...common} loading={priority ? 'eager' : 'lazy'} src={`/assets/shots/${name}-light.png`} width={light.width} height={light.height} className={cn('h-auto w-full dark:hidden', className)} />
      <img {...common} loading="lazy" src={`/assets/shots/${name}-dark.png`} width={dark.width} height={dark.height} className={cn('hidden h-auto w-full dark:block', className)} />
    </>
  );
}

/** The frame around a screenshot: a hairline outline, a layered shadow, and a caption that says the data is made up. */
export function TerminalWindow({ children, caption, className, captionClassName }: { children: React.ReactNode; caption: string; className?: string; captionClassName?: string }) {
  return (
    <figure className={cn('m-0', className)}>
      <div className="overflow-clip rounded-xl border border-transparent bg-[var(--code-bg)] shadow-[0_1px_1px_rgb(0_0_0/0.08),0_8px_24px_-6px_rgb(0_0_0/0.28),0_30px_60px_-20px_rgb(0_0_0/0.35)] outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10">
        {children}
      </div>
      <figcaption className={cn('mt-3 text-sm text-mute', captionClassName)}>{caption}</figcaption>
    </figure>
  );
}
