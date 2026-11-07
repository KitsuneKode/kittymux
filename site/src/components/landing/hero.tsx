import { Link } from '@tanstack/react-router';
import { DocLink } from '../doc-link';
import KittymuxHero from '@/stageshow/kittymux-hero';
import { WeaveBand } from '../weave-band';
import { GitHubStars } from '../github-stars';
import { SponsorButton } from '../sponsor-button';
import { Logo, Mascot } from '../logo';
import { REPO, stars } from '@/lib/links';

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
          <div className="flex items-center gap-2 sm:gap-5">
          <nav aria-label="Primary" className="flex items-center text-sm font-medium sm:gap-5">
            <DocLink className="inline-flex min-h-11 items-center px-2 hover:underline">Docs</DocLink>
            <Link to="/keys" className="hidden min-h-11 items-center px-2 hover:underline min-[400px]:inline-flex">Keys</Link>
            <Link to="/changelog" className="hidden min-h-11 items-center px-2 hover:underline sm:inline-flex">Changelog</Link>
          </nav>
          <SponsorButton collapse />
          </div>
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
                <GitHubStars repo={REPO} stargazersCount={stars} tone="brand" className="min-h-12 sm:min-h-12" />
              </div>
            </div>
            <figure data-rise="" className="kh-host relative m-0 mt-16 w-full [animation-delay:240ms] lg:col-span-6 lg:mt-20">
              {/* the kitten peeks over the window's top edge; the window is drawn above it */}
              <Mascot priority width={132} className="pointer-events-none absolute -top-[62px] right-10 z-0" />
              {/* kitty with kittymux's bar, drawn as an illustration (stageshow): an agent comes to need you, you jump, you answer.
                  The stage's ground is transparent so the brand band is the ground; under reduced motion it holds the frame
                  where the agent is asking. */}
              <div className="relative z-10"><KittymuxHero /></div>
              <figcaption className="mt-3 text-sm text-onbrand-soft">Made-up tabs in kitty&apos;s own bar: one agent stops to ask, you jump there and answer.</figcaption>
            </figure>
          </section>
        </div>
        <WeaveBand id="hero-end" />
    </>
  );
}
