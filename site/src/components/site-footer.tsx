import { IconArrowUpRight, IconHeart } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import { GitHubStars } from './github-stars';
import { Logo } from './logo';
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
            <Logo size={44} textClassName="text-xl" />
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
              <h2 className="t-h3 !text-base">Read</h2>
              <ul className="mt-3 flex flex-col">
                <li><Link to="/docs/$" params={{ _splat: '' }} className={linkClass}>Documentation</Link></li>
                <li><Link to="/docs/$" params={{ _splat: 'users/getting-started' }} className={linkClass}>Getting started</Link></li>
                <li><Link to="/keys" className={linkClass}>Keys</Link></li>
                <li><Link to="/changelog" className={linkClass}>Changelog</Link></li>
                <li><a href="/llms.txt" className={linkClass}>llms.txt</a></li>
              </ul>
            </div>
            <div>
              <h2 className="t-h3 !text-base">Project</h2>
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
            <h2 id="more-projects" className="t-h3">More from KitsuneKode</h2>
            <Ext href={ALL_PROJECTS_URL}>All projects on GitHub</Ext>
          </div>
          {/* each item is one link (the name's ::after covers it), so a screen reader hears the name, not a paragraph of link text */}
          <ul className="mt-6 grid gap-x-8 gap-y-7 sm:grid-cols-2 lg:grid-cols-4">
            {PROJECTS.map((p) => (
              <li key={p.name} className="group relative min-w-0 rounded-md has-[a:focus-visible]:outline has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-8 has-[a:focus-visible]:outline-ink">
                <span className="flex items-baseline justify-between gap-3">
                  <a href={p.url} target="_blank" rel="noopener" className="font-semibold underline-offset-4 outline-2 outline-transparent after:absolute after:inset-0 group-hover:underline focus-visible:outline-transparent">{p.name}</a>
                  <span className="t-caption shrink-0 text-mute">{p.kind}</span>
                </span>
                <span className="t-small mt-1 block text-mute">{p.blurb}</span>
              </li>
            ))}
          </ul>
        </section>

        <Separator className="my-10 bg-line" />

        <div className="flex flex-col gap-4 text-sm text-mute sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1">
            <p>kittymux <span className="tabular">{buildLabel(facts.version)}</span> · MIT license · made by KitsuneKode</p>
            <p className="max-w-[60ch] text-pretty">This site counts visits with Vercel Web Analytics: no cookies, nothing that identifies you, and nothing at all if your browser sends Do Not Track. <Link to="/docs/$" params={{ _splat: 'users/privacy-and-security' }} className="underline underline-offset-4 hover:text-ink">Read the privacy page</Link></p>
          </div>
          {themeToggle && <ThemeToggle className="self-start" />}
        </div>
      </div>
    </footer>
  );
}
