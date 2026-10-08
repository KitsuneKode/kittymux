import { facts } from '@/lib/facts';
import { IconChevronDown } from '@tabler/icons-react';

export const FAQ = [
  ['Does it send my data anywhere?', 'No. There is no server, no network listener and no always-on daemon. It reads pane text and agent state locally and never transmits it. Live usage quotas are opt-in.'],
  ['Will it type into my agents?', 'Notifications, the inbox and the panel never do: Jump moves focus, Dismiss hides a card. Only a key you press for it sends text, such as the one that sends a prompt to an agent pane.'],
  ['Which agents does it recognise?', `${facts.agents.length} agent CLIs are in its table. Claude Code, Codex and Devin have been checked against live sessions. Some others follow each tool's documented hints, and a few get only their logo and what their hooks or window title report. The platforms page says which is which.`],
  ['Do I have to leave tmux?', 'No. tmux stays for remote work. kittymux is for the terminal in front of you.'],
  ['Does it need Wayland?', 'Only the docked panel does (it needs wlr-layer-shell). The tab bar, the scanner and the deck were tested on X11 in a virtual display.'],
] as const;

export function Faq() {
  return (
    <section aria-labelledby="faq" className="mx-auto w-full max-w-[880px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="faq" className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">Questions people ask first</h2>
      <div className="mt-8 divide-y divide-line border-y border-line">
        {FAQ.map(([q, a]) => (
          <details key={q} className="group">
            <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 py-3 text-lg font-semibold marker:hidden [&::-webkit-details-marker]:hidden">
              {q}
              <IconChevronDown aria-hidden="true" className="size-5 shrink-0 text-mute transition-transform duration-150 group-open:rotate-180 motion-reduce:transition-none" stroke={1.75} />
            </summary>
            <p className="max-w-[60ch] text-pretty pb-4 text-base text-mute">{a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
