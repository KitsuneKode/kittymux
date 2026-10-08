import { cn } from '@/lib/utils';

/** The mascot as the app-icon tile (its own blue field, rounded like an app icon) and the name in the brand's mono face, the way the social card sets it. */
export function Logo({ size = 36, className, textClassName }: { size?: number; className?: string; textClassName?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <img src={size > 40 ? '/brand/mascot-avatar-128.png' : '/brand/mascot-avatar-64.png'} width={size} height={size} alt="" decoding="async" className="shrink-0 rounded-[24%] ring-1 ring-black/10 dark:ring-white/15" style={{ width: size, height: size }} />
      <span className={cn('font-mono text-[1.0625rem] font-extrabold tracking-[-0.02em]', textClassName)}>kittymux</span>
    </span>
  );
}

/**
 * The kitten without its background, for sitting on an edge: the image is cropped at its left and bottom (it grows out of a corner, as on the social card),
 * so put it where that edge meets the edge of a window or a section. Decorative: no alt text, ignored by assistive technology.
 */
export function Mascot({ className, priority = false, width = 200 }: { className?: string; priority?: boolean; width?: number }) {
  return (
    <img
      src="/brand/mascot-cutout.webp"
      width={640}
      height={640}
      alt=""
      aria-hidden="true"
      decoding="async"
      loading={priority ? 'eager' : 'lazy'}
      fetchPriority={priority ? 'high' : 'auto'}
      draggable={false}
      className={cn('pointer-events-none h-auto select-none', className)}
      style={{ width }}
    />
  );
}
