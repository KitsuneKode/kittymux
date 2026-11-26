import { facts } from '@/lib/facts';

export const FAQ = [
  [
    'Does it send my data anywhere?',
    'No. There is no server, no network listener, and no always-on daemon. It reads pane state locally, stores snapshots at mode 0600, and leaves live usage quotas strictly opt-in.',
  ],
  [
    'Will it type into my agents or steal focus?',
    'Never by itself. Notifications, the inbox, and attention dividers never move focus or send keystrokes. Only an explicit action you trigger, such as Jump or a deliberate send command, targets a pane.',
  ],
  [
    'Do the pixel bar and graphical panel work without extra packages?',
    'Pixel rendering (pxbar and deckpx) is opt-in and uses Cairo, Pango, and rsvg, with Slang shaders for glass cards and hover. If those packages are missing or disabled, kittymux automatically uses the zero-dependency terminal cell bar and panel.',
  ],
  [
    'Which agents does it recognise?',
    `${facts.agents.length} agent CLIs plus T3 Code are in its table. Claude Code, Codex, Devin, Cursor Agent, OpenCode, and Antigravity have live-captured prompt and hook support; the platforms page records exactly what has been verified for each.`,
  ],
  [
    'Do I have to leave tmux or Wayland?',
    'No. tmux remains the right tool for remote SSH sessions, while kittymux runs your local kitty workspace. Only the docked panel and Quickshell client need Wayland layer-shell; the tab bar, scanner, and overlay deck work on X11 too.',
  ],
] as const;

export function Faq() {
  return (
    <section aria-labelledby="faq" className="mx-auto w-full max-w-[920px] px-5 py-20 md:px-8 lg:py-28">
      <h2 id="faq" className="t-h2">Questions people ask first</h2>
      <div className="mt-8 divide-y divide-line border-y border-line">
        {FAQ.map(([q, a]) => (
          <details key={q} className="group">
            <summary className="t-h3 flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-4 text-ink marker:hidden [&::-webkit-details-marker]:hidden">
              {q}
              <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className="size-5 shrink-0 text-mute transition-transform duration-150 group-open:rotate-180 motion-reduce:transition-none"><path d="m6 9 6 6 6-6" /></svg>
            </summary>
            <p className="t-body max-w-[62ch] pb-5 text-mute">{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
