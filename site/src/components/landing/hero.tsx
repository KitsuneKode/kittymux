import { IconHeart } from '@tabler/icons-react';
import { Link } from '@tanstack/react-router';
import { DocLink } from '../doc-link';
import { Shot, TerminalWindow } from '../terminal-window';
import { WeaveBand } from '../weave-band';
import { GitHubStars } from '../github-stars';
import { Logo, Mascot } from '../logo';
import { REPO, SPONSOR_URL, stars } from '@/lib/links';

/** The weave band and the top bar: outside <main>, so "Skip to content" skips them. */
export function LandingHeader() {
  return (
    <>
      <WeaveBand id="top" />
      <header data-brand="" className="bg-brand text-onbrand">
        <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center justify-between gap-4 px-5 md:px-8 lg:h-[72px]">
          <Link to="/" data-press="" className="flex min-h-11 items-center gap-3 rounded-lg font-semibold">
            <Logo size={40} textClassName="text-xl" />
          </Link>
          <nav aria-label="Primary" className="flex items-center text-sm font-medium sm:gap-5">
            <DocLink className="inline-flex min-h-11 items-center px-2 hover:underline">Docs</DocLink>
            <Link to="/keys" className="hidden min-h-11 items-center px-2 hover:underline min-[400px]:inline-flex">Keys</Link>
            <Link to="/changelog" className="hidden min-h-11 items-center px-2 hover:underline sm:inline-flex">Changelog</Link>
            <GitHubStars repo={REPO} stargazersCount={stars} className="text-onbrand hover:bg-onbrand/15 hover:text-onbrand aria-expanded:bg-onbrand/15" />
            <a href={SPONSOR_URL} target="_blank" rel="noopener" className="hidden min-h-11 items-center gap-1.5 px-2 hover:underline min-[380px]:inline-flex">
              <IconHeart aria-hidden="true" className="size-4" stroke={1.75} />
              <span className="max-[479px]:sr-only">Sponsor</span>
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
        <div data-brand="" className="bg-brand text-onbrand">
          <section aria-labelledby="hero-title" className="mx-auto grid w-full max-w-[1280px] gap-10 px-5 pb-12 pt-8 md:px-8 lg:grid-cols-12 lg:items-center lg:gap-10 lg:pb-24 lg:pt-10">
            <div className="lg:col-span-6">
              <h1 id="hero-title" data-rise="" className="t-display max-w-[14ch] sm:max-w-[16ch]">
                Know which agent needs you.
              </h1>
              <p data-rise="" className="t-lead mt-6 max-w-[36ch] text-onbrand-soft [animation-delay:80ms]">
                Turn kitty into a multiplexer for AI coding agents. See who is working, waiting or done, and jump straight there.
              </p>
              <div data-rise="" className="mt-8 flex flex-col gap-3 [animation-delay:160ms] sm:flex-row sm:items-center">
                <a href="#install" data-cta="" data-press="" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 text-base font-semibold">Try the demo</a>
                <DocLink data-press="" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-full border border-onbrand px-6 text-base font-semibold hover:bg-onbrand hover:text-brand">Read the docs</DocLink>
              </div>
            </div>
            <div data-rise="" className="relative mx-auto mt-20 w-full max-w-[460px] [animation-delay:240ms] lg:col-span-6 lg:mt-24">
              {/* the kitten sits on the window's top edge: its cropped bottom is hidden behind the frame */}
              <Mascot priority width={160} className="absolute -inset-bs-[100px] inset-e-6 z-0 lg:inset-e-10" />
              <TerminalWindow className="relative z-10" captionClassName="text-onbrand-soft" caption="The docked panel on made-up tabs: one needs you, one has a usage limit that resets in 42 minutes.">
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
