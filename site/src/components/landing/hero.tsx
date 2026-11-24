import { Link } from '@tanstack/react-router';
import { useEffect, useRef, useState } from 'react';
import { DocLink } from '../doc-link';
import { Logo, Mascot } from '../logo';
import { SponsorButton } from '../sponsor-button';
import { Shot } from '../terminal-window';
import { ThemeToggle } from '../theme-toggle';

const VIEWS = [
  {
    id: 'workspace',
    label: 'Workspace',
    shot: 'workspace',
    alt: 'A full kitty window running kittymux: pixel Agents panel on the left showing five tabs and two needing you, beside split Codex and OpenCode panes with pane title bars and an attention divider.',
    caption: 'Opt-in pixel Agents panel beside split Codex and OpenCode panes, with state pills in pane title bars and an attention divider on the waiting split.',
    cmd: 'kittymux settings preset pixel',
    wide: true,
  },
  {
    id: 'pxbar',
    label: 'Pixel bar',
    shot: 'pxbar',
    alt: 'The kittymux pixel tab bar rendered inside kitty: project groups, lit brand tiles for Claude, Codex, and Goose, Needs you chips, an animated working wave, OSC 9;4 progress hairlines, and a usage limit countdown.',
    caption: 'Opt-in pixel tab bar drawn inside kitty with Cairo and Slang shaders: lit brand tiles, project groups, animated working wave, OSC 9;4 progress, and reset countdowns.',
    cmd: 'kittymux settings on pxbar',
    wide: false,
  },
  {
    id: 'usage',
    label: 'Usage',
    shot: 'px-usage',
    alt: 'The graphical Usage view inside the kittymux pixel panel showing Codex Personal at 70 percent left and Work at 0 percent left across five-hour and weekly windows with pace notches and reset countdowns.',
    caption: 'Multi-account quota meters in the pixel panel: separate Personal and Work windows, pace notches, reset countdowns, and honest sample age.',
    cmd: 'kittymux usage',
    wide: false,
  },
  {
    id: 'inbox',
    label: 'Inbox',
    shot: 'px-inbox',
    alt: 'The graphical Inbox view listing unread agent questions, permission prompts, build failures, completions, and quota limits with Jump and Dismiss controls.',
    caption: 'Every question, permission request, error body, and quota limit collected in one keyboard-and-pointer inbox with Jump, Dismiss, and Undo.',
    cmd: 'kittymux inbox',
    wide: false,
  },
  {
    id: 'client',
    label: 'Native client',
    shot: 'client-attach',
    alt: 'The Quickshell kittymux client attached directly over kitty’s vertical sidebar on Hyprland, displaying state rings around Claude and Codex marks with a gliding selection bar.',
    caption: 'Optional Quickshell sidebar with proportional type and calm state rings, docked on Wayland or attached over kitty’s own vertical bar on Hyprland.',
    cmd: 'kittymux client',
    wide: false,
  },
] as const;

type ViewId = (typeof VIEWS)[number]['id'];

/** Borderless floating top bar over the hero canvas; gains frosted surface separation once the visitor scrolls. */
export function LandingHeader() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 18);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className="site-header" data-scrolled={scrolled ? 'true' : 'false'}>
      <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center justify-between gap-4 px-5 md:px-8 lg:h-[72px]">
        <Link to="/" data-press="" className="flex min-h-11 items-center gap-3 rounded-lg font-semibold text-ink">
          <Logo size={38} textClassName="text-xl tracking-[-0.03em]" />
        </Link>
        <nav aria-label="Primary" className="flex items-center gap-4 text-[0.9375rem] font-medium text-ink/85 md:gap-6">
          <DocLink className="inline-flex min-h-11 items-center transition-colors duration-150 hover:text-ink">Docs</DocLink>
          <a href="#upgrades" className="hidden min-h-11 items-center transition-colors duration-150 hover:text-ink md:inline-flex">Upgrades</a>
          <a href="#roadmap" className="hidden min-h-11 items-center transition-colors duration-150 hover:text-ink md:inline-flex">Roadmap</a>
          <Link to="/keys" className="hidden min-h-11 items-center transition-colors duration-150 hover:text-ink sm:inline-flex">Keys</Link>
          <Link to="/changelog" className="hidden min-h-11 items-center transition-colors duration-150 hover:text-ink md:inline-flex">Changelog</Link>
        </nav>
        <div className="flex items-center gap-2 sm:gap-3">
          <ThemeToggle className="hidden sm:inline-flex" />
          <SponsorButton collapse />
        </div>
      </div>
    </header>
  );
}

/** Centered monumental hero over full-bleed curated print art from imageory.in, rising directly into an interactive docked stage. */
export function Hero() {
  const [active, setActive] = useState<ViewId>('workspace');
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = VIEWS.find((v) => v.id === active) ?? VIEWS[0];

  const onTabKeyDown = (e: React.KeyboardEvent, idx: number) => {
    const next =
      e.key === 'ArrowRight' ? (idx + 1) % VIEWS.length :
      e.key === 'ArrowLeft' ? (idx + VIEWS.length - 1) % VIEWS.length :
      e.key === 'Home' ? 0 :
      e.key === 'End' ? VIEWS.length - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    setActive(VIEWS[next].id);
    tabRefs.current[next]?.focus();
  };

  return (
    <section aria-labelledby="hero-title" className="hero-canvas pb-16 pt-28 md:pb-24 md:pt-36 lg:pt-40">
      {/* Full-bleed atmospheric prints from imageory.in: warm canyon by day, glowing lantern camp by night */}
      <img
        src="/brand/art/horizon-canyon.webp"
        width={1672}
        height={941}
        alt=""
        aria-hidden="true"
        decoding="async"
        loading="eager"
        className="hero-art opacity-85 dark:hidden"
      />
      <img
        src="/brand/art/hero-night.webp"
        width={1672}
        height={941}
        alt=""
        aria-hidden="true"
        decoding="async"
        loading="eager"
        className="hero-art hidden opacity-90 dark:block"
      />
      <div className="hero-veil" aria-hidden="true" />

      <div className="mx-auto flex w-full max-w-[1220px] flex-col items-center px-5 text-center md:px-8">
        <h1 id="hero-title" data-rise="" className="t-hero max-w-[15ch] text-ink">
          Know which agent <span className="signal-word">needs you.</span>
        </h1>
        <p data-rise="" className="t-body mt-6 max-w-[50ch] text-ink/90 [animation-delay:80ms]">
          Turn kitty into an agent cockpit. See every waiting question, quota meter, and finished run at one glance without leaving your terminal.
        </p>
        <p data-rise="" className="t-mono mt-3 text-[0.8125rem] text-ink/75 [animation-delay:115ms]">
          Linux (Wayland &amp; X11) · zero daemon · socket-only · never steals focus
        </p>
        <div data-rise="" className="mt-7 [animation-delay:150ms]">
          <a
            href="#install"
            data-cta=""
            data-press=""
            className="inline-flex min-h-12 items-center justify-center rounded-full px-8 text-[0.9375rem] font-semibold shadow-md"
          >
            Try the demo
          </a>
        </div>

        {/* Interactive docked workspace stage rising above the fold */}
        <div data-rise="" className="relative mt-14 w-full min-w-0 max-w-[1120px] [animation-delay:220ms] lg:mt-16">
          <div className="mb-5 flex w-full min-w-0 justify-center">
            <div role="tablist" aria-label="Explore kittymux views" className="seg-track">
              {VIEWS.map((view, idx) => {
                const selected = view.id === active;
                return (
                  <button
                    key={view.id}
                    ref={(el) => { tabRefs.current[idx] = el; }}
                    id={`stage-tab-${view.id}`}
                    role="tab"
                    type="button"
                    aria-selected={selected}
                    aria-controls={`stage-panel-${view.id}`}
                    tabIndex={selected ? 0 : -1}
                    data-press=""
                    onClick={() => setActive(view.id)}
                    onKeyDown={(e) => onTabKeyDown(e, idx)}
                    className="seg-tab"
                  >
                    {view.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="relative">
            <Mascot
              priority
              width={132}
              className="absolute -inset-bs-[84px] inset-e-6 z-0 hidden md:block lg:inset-e-10"
            />
            <div
              id={`stage-panel-${current.id}`}
              role="tabpanel"
              aria-labelledby={`stage-tab-${current.id}`}
              className="stage-frame relative z-10 overflow-clip rounded-2xl border border-line bg-card/95 dark:bg-[var(--code-bg)]"
            >
              <div className="relative flex min-h-[260px] items-center justify-center overflow-clip bg-[var(--surface-hi)] p-3 dark:bg-[var(--code-bg)] sm:min-h-[420px] sm:p-5 lg:min-h-[540px] lg:p-6">
                {/* Persistent full workspace canvas; dims gently when a narrow panel view docks over the left edge */}
                <Shot
                  name="workspace"
                  alt={current.wide ? current.alt : ''}
                  priority
                  className={
                    current.wide
                      ? 'mx-auto max-h-[560px] w-full rounded-xl object-contain transition-[opacity,filter,transform] duration-200'
                      : 'mx-auto max-h-[560px] w-full rounded-xl object-contain opacity-30 blur-[1.5px] transition-[opacity,filter,transform] duration-200'
                  }
                />
                {!current.wide && (
                  <div
                    key={current.id}
                    className="stage-dock absolute inset-y-3 inset-s-3 z-20 flex max-w-[calc(100%-1.5rem)] items-center sm:inset-y-5 sm:inset-s-6 lg:inset-y-6 lg:inset-s-8"
                  >
                    <Shot
                      name={current.shot}
                      alt={current.alt}
                      className="h-full max-h-[528px] w-auto max-w-full rounded-xl object-contain shadow-2xl ring-1 ring-black/15 dark:ring-white/15"
                    />
                  </div>
                )}
              </div>
              <div className="flex flex-col items-start justify-between gap-3 border-t border-line bg-card px-5 py-4 text-start dark:border-white/10 dark:bg-[var(--code-bg)] sm:flex-row sm:items-center">
                <p className="t-caption max-w-[68ch] text-mute dark:text-[var(--code-fg)]/85">{current.caption}</p>
                <code className="t-mono shrink-0 rounded-lg bg-card-hi px-3 py-1.5 text-[0.8125rem] text-ink dark:bg-white/8 dark:text-[var(--code-fg)]">{current.cmd}</code>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
