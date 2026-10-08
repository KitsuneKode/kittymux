import { Link } from '@tanstack/react-router';
import { featuredGroups } from '@/lib/facts';

/** Twelve keys in three groups by what you are doing. No lines between rows: the groups carry the structure. */
export function KeysGlance() {
  const groups = featuredGroups();
  return (
    <section aria-labelledby="keys" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h2 id="keys" className="t-h2">The keys you will use</h2>
        <Link to="/keys" className="inline-flex min-h-11 items-center font-semibold text-link underline underline-offset-4">All keys</Link>
      </div>
      <div className="mt-12 grid gap-12 md:grid-cols-3 md:gap-10">
        {groups.map((g) => (
          <div key={g.title}>
            <h3 className="t-h3">{g.title}</h3>
            <dl className="mt-5 flex flex-col gap-5">
              {g.rows.map((r) => (
                <div key={r.key} className="flex flex-col gap-1.5">
                  <dt>
                    <kbd className="t-mono inline-block max-w-full rounded-md bg-card-hi px-2 py-0.5 [overflow-wrap:anywhere]">{r.key}</kbd>
                  </dt>
                  <dd className="t-small text-mute">{r.desc}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}
