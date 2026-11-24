import manifest from '../../public/assets/shots/manifest.json';
import { cn } from '@/lib/cn';

type Size = { width: number; height: number };
const sizes = manifest as Record<string, Size>;

/**
 * A real screenshot, once per theme; the other theme's is hidden. Width and height come from manifest.json so layout never shifts.
 */
export function Shot({ name, alt, priority = false, className }: { name: string; alt: string; priority?: boolean; className?: string }) {
  const dark = sizes[`${name}-dark.png`];
  const light = sizes[`${name}-light.png`] ?? dark;
  if (!dark) throw new Error(`Shot: no screenshot named ${name}-dark.png in the manifest (run tools/build-site-assets.sh)`);
  const common = { decoding: 'async' as const, alt };
  return (
    <>
      <img {...common} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} src={`/assets/shots/${name}-light.png`} width={light.width} height={light.height} className={cn('h-auto w-full dark:hidden', className)} />
      <img {...common} loading={priority ? 'eager' : 'lazy'} fetchPriority={priority ? 'high' : 'auto'} src={`/assets/shots/${name}-dark.png`} width={dark.width} height={dark.height} className={cn('hidden h-auto w-full dark:block', className)} />
    </>
  );
}

/** Framed terminal capture with layered gallery elevation and an honest synthetic-data caption. */
export function TerminalWindow({ children, caption, className, frameClassName, captionClassName }: { children: React.ReactNode; caption?: string; className?: string; frameClassName?: string; captionClassName?: string }) {
  return (
    <figure className={cn('m-0', className)}>
      <div className={cn('stage-frame overflow-clip rounded-2xl bg-card dark:bg-[var(--code-bg)]', frameClassName)}>
        {children}
      </div>
      {caption ? <figcaption className={cn('t-caption mt-3 text-mute', captionClassName)}>{caption}</figcaption> : null}
    </figure>
  );
}
