import { Link } from '@tanstack/react-router';
import { featuredGroups } from '@/lib/facts';

/** Featured chords grouped by job, rendered as tactile physical keycaps from kittymux-keys.conf.tpl via facts.json. */
export function KeysGlance() {
  const groups = featuredGroups();
  return (
    <section aria-labelledby="keys" className="border-t border-line bg-card py-20 lg:py-28">
      <div className="mx-auto w-full max-w-[1220px] px-5 md:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 id="keys" className="t-h2">The keys you will use</h2>
          <Link to="/keys" className="inline-flex min-h-11 items-center font-semibold text-link underline underline-offset-4">
            All keys
          </Link>
        </div>
        <div className="mt-12 grid gap-12 md:grid-cols-3 md:gap-10">
          {groups.map((g) => (
            <div key={g.title} className="border-t border-line pt-6">
              <h3 className="t-h3 text-ink">{g.title}</h3>
              <dl className="mt-6 flex flex-col gap-5">
                {g.rows.map((r) => (
                  <div key={r.key} className="flex flex-col gap-1.5">
                    <dt>
                      <kbd className="keycap">{r.key}</kbd>
                    </dt>
                    <dd className="t-caption text-mute">{r.desc}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
