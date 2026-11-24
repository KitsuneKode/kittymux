import { DocLink } from '../doc-link';
import { SearchLauncher } from './search-launcher';

const ArrowRight = ({ className }: { className?: string }) => (
  <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M5 12h14m-6 6 6-6-6-6" /></svg>
);

const HUB = [
  { slug: 'users/getting-started', title: 'Getting started', text: 'Run the demo, install into kitty, enable hooks, and verify with doctor.' },
  { slug: 'users/the-tab-bar', title: 'The tab bar and pixel mode', text: 'Vertical cell bar, opt-in Cairo/Slang pixel bar, rail mode, and OSC 9;4 progress.' },
  { slug: 'users/the-client', title: 'The Quickshell client', text: 'Native Wayland sidebar, Hyprland attach mode, and live tabs.json feeds.' },
  { slug: 'users/cli-reference', title: 'CLI reference', text: 'Every kittymux subcommand, settings switch, and workflow action.' },
  { slug: 'users/troubleshooting', title: 'Troubleshooting', text: 'A key does nothing, a state looks stale, or a graphics probe timed out.' },
] as const;

export function DocsHub() {
  return (
    <section id="docs" aria-labelledby="docs-title" className="border-y border-line py-20 lg:py-28">
      <div className="mx-auto grid w-full max-w-[1220px] gap-12 px-5 md:px-8 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <h2 id="docs-title" className="t-h2">Looking for something?</h2>
          <p className="t-body mt-4 max-w-[38ch] text-mute">
            Search every user guide, key chord, and changelog entry from here, or open the full documentation.
          </p>
          <div className="mt-6"><SearchLauncher tone="page" /></div>
          <div className="mt-6">
            <DocLink className="inline-flex min-h-11 items-center gap-2 font-semibold text-link underline underline-offset-4">
              Read the docs
              <ArrowRight className="size-4" />
            </DocLink>
          </div>
        </div>
        <ul className="divide-y divide-line border-t border-line lg:col-span-6 lg:col-start-7">
          {HUB.map(({ slug, title, text }) => (
            <li key={slug} className="group relative py-5 has-[a:focus-visible]:outline has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-offset-4 has-[a:focus-visible]:outline-ink">
              <DocLink slug={slug} className="t-h3 inline-flex items-center gap-2 text-ink underline-offset-4 outline-2 outline-transparent after:absolute after:inset-0 group-hover:underline focus-visible:outline-transparent">
                {title}
                <ArrowRight className="size-4 text-link motion-safe:transition-transform motion-safe:duration-150 group-hover:translate-x-1" />
              </DocLink>
              <span className="t-body mt-1 block max-w-[48ch] text-mute">{text}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
