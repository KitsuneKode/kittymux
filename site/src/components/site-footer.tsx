import { IconArrowUpRight, IconHeart } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import { GitHubStars } from './github-stars';
import { buttonVariants } from './ui/button';
import { Separator } from './ui/separator';
import { ThemeToggle } from './theme-toggle';
import { WeaveBand } from './weave-band';
import { facts } from '@/lib/facts';
import { cn } from '@/lib/utils';
import { ALL_PROJECTS_URL, AUTHOR_URL, ISSUES_URL, REPO, REPO_URL, SPONSOR_URL, stars } from '@/lib/links';
import { PROJECTS } from '@/lib/projects';

/** A tag reads as a version ("v1.2.0"); a bare commit id says what it is, and a dirty tree is not worth announcing. */
export function buildLabel(v: string): string {
  const clean = v.replace(/-dirty$/, '');
  return /^[0-9a-f]{7,40}$/.test(clean) ? `build ${clean}` : clean;
}

const linkClass = 'inline-flex min-h-11 items-center py-1 text-mute hover:text-ink hover:underline sm:min-h-9';

function Ext({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener" className={linkClass}>
      {children}
      <IconArrowUpRight aria-hidden="true" className="ms-0.5 size-3.5 shrink-0" stroke={1.75} />
    </a>
  );
}

export function SiteFooter({ themeToggle = false }: { themeToggle?: boolean }) {
  return (
    <footer className="mt-24">
      <WeaveBand id="foot" />
      <div className="mx-auto w-full max-w-[1280px] px-5 py-12 md:px-8">
        <div className="grid gap-10 md:grid-cols-12">
          <div className="md:col-span-5">
            <p className="flex items-center gap-3 text-lg font-semibold">
              <span aria-hidden="true" className="grid size-9 place-items-center rounded-lg bg-brand text-lg font-bold text-onred">k</span>
              kittymux
            </p>
            <p className="mt-3 max-w-[40ch] text-pretty text-mute">Kitty as a multiplexer for AI coding agents. Free, MIT-licensed, and tested on the author’s own desktop.</p>
            <div className="mt-5 flex flex-wrap items-center gap-2">
              <GitHubStars repo={REPO} stargazersCount={stars} className="border border-line text-ink hover:bg-card-hi" />
              <a href={SPONSOR_URL} target="_blank" rel="noopener" className={cn(buttonVariants({ variant: 'outline' }), 'min-h-11 border-line text-ink hover:bg-card-hi sm:min-h-8')}>
                <IconHeart aria-hidden="true" data-icon="inline-start" className="text-link" stroke={2} />
                Sponsor
              </a>
            </div>
          </div>
          <nav aria-label="Footer" className="grid grid-cols-2 gap-8 md:col-span-7">
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-ink">Read</h2>
              <ul className="mt-3 flex flex-col">
                <li><Link to="/docs/$" params={{ _splat: '' }} className={linkClass}>Documentation</Link></li>
                <li><Link to="/docs/$" params={{ _splat: 'users/getting-started' }} className={linkClass}>Getting started</Link></li>
                <li><Link to="/keys" className={linkClass}>Keys</Link></li>
                <li><Link to="/changelog" className={linkClass}>Changelog</Link></li>
                <li><a href="/llms.txt" className={linkClass}>llms.txt</a></li>
              </ul>
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-ink">Project</h2>
              <ul className="mt-3 flex flex-col">
                <li><Ext href={REPO_URL}>Source on GitHub</Ext></li>
                <li><Ext href={ISSUES_URL}>Report an issue</Ext></li>
                <li><Ext href={SPONSOR_URL}>Sponsor</Ext></li>
                <li><Ext href={`${REPO_URL}/blob/main/LICENSE`}>MIT license</Ext></li>
                <li><Ext href={AUTHOR_URL}>KitsuneKode</Ext></li>
              </ul>
            </div>
          </nav>
        </div>

        <Separator className="my-10 bg-line" />

        <section aria-labelledby="more-projects">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="more-projects" className="text-xl font-semibold tracking-[-0.02em]">More from KitsuneKode</h2>
            <Ext href={ALL_PROJECTS_URL}>All projects on GitHub</Ext>
          </div>
          <ul className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {PROJECTS.map((p) => (
              <li key={p.name} className="min-w-0">
                <a href={p.url} target="_blank" rel="noopener" className="group flex h-full flex-col gap-2 rounded-xl border border-line bg-card p-4 transition-colors duration-150 hover:bg-card-hi motion-reduce:transition-none">
                  <span className="flex items-start justify-between gap-2">
                    <span className="text-base font-semibold group-hover:underline">{p.name}</span>
                    <span className="mt-0.5 shrink-0 rounded-full border border-line px-2 py-0.5 text-xs text-mute">{p.kind}</span>
                  </span>
                  <span className="text-pretty text-sm text-mute">{p.blurb}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>

        <Separator className="my-10 bg-line" />

        <div className="flex flex-col gap-4 text-sm text-mute sm:flex-row sm:items-center sm:justify-between">
          <p>kittymux <span className="tabular">{buildLabel(facts.version)}</span> · MIT license · made by KitsuneKode</p>
          {themeToggle && <ThemeToggle className="self-start" />}
        </div>
      </div>
    </footer>
  );
}
