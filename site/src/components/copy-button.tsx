import { IconCheck, IconCopy } from '@tabler/icons-react';
import { useRef, useState } from 'react';
import { cn } from '@/lib/cn';

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    /* fall through to the old way */
  }
  try {
    const el = Object.assign(document.createElement('textarea'), { value: text });
    el.setAttribute('readonly', '');
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand('copy');
    el.remove();
    return ok;
  } catch {
    return false;
  }
}

/** Copies `text`; the label changes to say so (a cue that does not depend on motion or colour). */
export function CopyButton({ text, label = 'Copy', context, className }: { text: string; label?: string; context?: string; className?: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const onClick = async () => {
    setState((await copy(text)) ? 'copied' : 'failed');
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState('idle'), 1800);
  };
  return (
    <button type="button" data-press="" onClick={onClick} className={cn('inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-semibold sm:min-h-10', className)}>
      {state === 'copied' ? <IconCheck aria-hidden="true" className="size-4" stroke={2} /> : <IconCopy aria-hidden="true" className="size-4" stroke={1.75} />}
      <span aria-live="polite">{state === 'copied' ? 'Copied' : state === 'failed' ? 'Press ctrl+c' : label}</span>
      {context && state === 'idle' ? <span className="sr-only">: {context}</span> : null}
    </button>
  );
}
