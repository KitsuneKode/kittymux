import { IconArrowUpRight } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import { DocLink } from '../doc-link';
import { SearchLauncher } from './search-launcher';
import { Shot, TerminalWindow } from '../terminal-window';
import { WeaveBand } from '../weave-band';
import { gitConfig } from '@/lib/shared';

/** The weave band and the top bar: outside <main>, so "Skip to content" skips them. */
export function LandingHeader() {
  return (
    <>
      <WeaveBand id="top" />
      <header data-red="" className="bg-brand text-onred">
        <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center justify-between gap-4 px-5 md:px-8 lg:h-[72px]">
          <Link to="/" data-press="" className="flex min-h-11 items-center gap-3 rounded-lg font-semibold">
            <span aria-hidden="true" className="grid size-9 place-items-center rounded-lg bg-onred text-lg font-bold text-brand">k</span>
            kittymux
          </Link>
          <nav aria-label="Primary" className="flex items-center text-sm font-medium sm:gap-5">
            <DocLink className="inline-flex min-h-11 items-center px-2 hover:underline">Docs</DocLink>
            <Link to="/keys" className="inline-flex min-h-11 items-center px-2 hover:underline">Keys</Link>
            <Link to="/changelog" className="hidden min-h-11 items-center px-2 hover:underline sm:inline-flex">Changelog</Link>
            <a href={`https://github.com/${gitConfig.user}/${gitConfig.repo}`} className="inline-flex min-h-11 items-center gap-1 px-2 hover:underline">
              <span className="max-[359px]:sr-only">GitHub</span><IconArrowUpRight aria-hidden="true" className="size-4" stroke={1.75} />
            </a>
          </nav>
        </div>
      </header>
    </>
  );
}

export function Hero() {
  return (
    <>
        <div data-red="" className="bg-brand text-onred">
          <section aria-labelledby="hero-title" className="mx-auto grid w-full max-w-[1280px] gap-10 px-5 pb-12 pt-8 md:px-8 lg:grid-cols-12 lg:items-center lg:gap-10 lg:pb-24 lg:pt-14">
            <div className="lg:col-span-6">
              <h1 id="hero-title" data-rise="" className="max-w-[12ch] text-balance text-[2.75rem] font-bold leading-[1.02] tracking-[-0.03em] sm:max-w-[16ch] sm:text-6xl lg:text-[4.25rem]">
                Know which agent needs you.
              </h1>
              <p data-rise="" className="mt-6 max-w-[40ch] text-pretty text-lg leading-snug text-onred-soft [animation-delay:80ms] sm:text-xl">
                kittymux turns kitty into a multiplexer for AI coding agents. One glance at the tab bar says who is working, who is waiting for you and who has finished, and one click takes you there.
              </p>
              <div data-rise="" className="mt-8 flex flex-col gap-3 [animation-delay:160ms] sm:flex-row sm:items-center">
                <a href="#install" data-cta="" data-press="" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 text-base font-semibold">Try the demo</a>
                <DocLink data-press="" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-onred px-6 text-base font-semibold hover:bg-onred hover:text-brand">Read the docs</DocLink>
              </div>
              <p data-rise="" className="mt-4 text-sm text-onred-soft [animation-delay:200ms]">The demo opens its own window. Your configuration is never read or changed.</p>
              <SearchLauncher />
            </div>
            <div data-rise="" className="mx-auto w-full max-w-[460px] [animation-delay:240ms] lg:col-span-6">
              <TerminalWindow captionClassName="text-onred-soft" caption="The docked panel on made-up tabs: one needs you, one has a usage limit that resets in 42 minutes.">
                <Shot
                  name="panel-agents"
                  alt="The kittymux panel listing seven made-up tabs: one needs you and says so, one is done, and one hit a usage limit and shows when it resets."
                  priority
                />
              </TerminalWindow>
            </div>
          </section>
        </div>
        <WeaveBand id="hero-end" />
    </>
  );
}
