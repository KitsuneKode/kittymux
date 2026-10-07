import { parseInline } from '@/lib/inline';

/** Renders the few inline forms the changelog uses; links open in the same tab, external ones say so to assistive technology. */
export function Inline({ text }: { text: string }) {
  return (
    <>
      {parseInline(text).map((p, i) => {
        if (p.t === 'bold') return <strong key={i} className="font-semibold">{p.v}</strong>;
        if (p.t === 'code') return <code key={i} className="rounded bg-card-hi px-1.5 py-0.5 font-mono text-[0.875em] [overflow-wrap:anywhere]">{p.v}</code>;
        if (p.t === 'link') return <a key={i} href={p.href} className="text-link underline underline-offset-4">{p.v}</a>;
        return <span key={i}>{p.v}</span>;
      })}
    </>
  );
}
