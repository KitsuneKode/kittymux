import { createFileRoute } from '@tanstack/react-router';
import { HomeLayout } from 'fumadocs-ui/layouts/home';
import { SiteFooter } from '@/components/site-footer';
import { Inline } from '@/components/inline';
import { baseOptions } from '@/lib/layout.shared';
import { parseChangelog } from '@/lib/inline';
import raw from '../generated/CHANGELOG.md?raw';

const releases = parseChangelog(raw);

export const Route = createFileRoute('/changelog')({
  head: () => ({
    meta: [
      { title: 'Changelog — kittymux' },
      { name: 'description', content: 'What changed in kittymux, newest first.' },
    ],
  }),
  component: Changelog,
});

function Changelog() {
  return (
    <HomeLayout {...baseOptions()}>
      <main id="main" className="mx-auto w-full max-w-[860px] px-5 py-12 md:px-8">
        <h1 className="text-balance text-4xl font-bold tracking-[-0.03em] sm:text-5xl">Changelog</h1>
        <p className="mt-4 max-w-[60ch] text-pretty text-lg text-mute">What changed, newest first. Until the first tagged release, everything is listed under “Unreleased”.</p>
        {releases.map((r) => (
          <section key={r.heading} aria-labelledby={`r-${r.heading}`} className="mt-12">
            <h2 id={`r-${r.heading}`} className="border-b border-line pb-2 text-2xl font-semibold tracking-[-0.02em]">{r.heading}</h2>
            {r.groups.map((g) => (
              <div key={g.name} className="mt-8">
                <h3 className="text-sm font-semibold uppercase tracking-[0.08em] text-link">{g.name}</h3>
                <ul className="mt-3 flex flex-col gap-4">
                  {g.items.map((item, i) => (
                    <li key={i} className="max-w-[72ch] text-pretty leading-relaxed [text-wrap:pretty]">
                      <Inline text={item} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        ))}
      </main>
      <SiteFooter />
    </HomeLayout>
  );
}
