import { Link } from '@tanstack/react-router';
import { featuredRows } from '@/lib/facts';

export function KeysGlance() {
  const rows = featuredRows();
  return (
    <section aria-labelledby="keys" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h2 id="keys" className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl lg:text-5xl">The keys you will use</h2>
        <Link to="/keys" className="inline-flex min-h-11 items-center font-semibold text-link underline underline-offset-4">All keys</Link>
      </div>
      <dl className="mt-10 grid gap-x-10 gap-y-3 md:grid-cols-2">
        {rows.map((r) => (
          <div key={r.key} className="flex flex-col gap-1 border-b border-line py-3 sm:flex-row sm:items-baseline sm:gap-4">
            <dt className="shrink-0 max-w-full">
              <kbd className="rounded-md border border-line bg-card px-2 py-1 font-mono text-sm">{r.key}</kbd>
            </dt>
            <dd className="min-w-0 text-pretty text-mute">{r.desc}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
