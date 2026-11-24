import { DocLink } from '../doc-link';

const IN_PROGRESS = [
  {
    title: 'Answer permission prompts from your desktop shell',
    detail: 'mux-ask and kittymux answer let a desktop shell approve or deny Claude Code and Codex permission hooks directly through the hook decision channel, staying out of the way whenever kitty is already focused or a command is too long to inspect whole.',
  },
  {
    title: 'Real-compositor qualification for the docked panel',
    detail: 'Verifying Wayland layer-shell geometry, multi-output placement, and startup latency across Hyprland and a second Wayland compositor so the docked panel graduates from beta.',
  },
  {
    title: 'Quickshell attach geometry and fractional scaling',
    detail: 'Hardening experimental attach mode on fractional-scale outputs and expanding live tabs.json and agents.json integrations for desktop shells.',
  },
] as const;

const PLANNED_NEXT = [
  {
    title: 'Workspace switcher with live agent states',
    detail: 'A recent-first overlay listing named sessions and OS windows grouped by desktop workspace, sorted with waiting agents first.',
  },
  {
    title: 'Safe session rename',
    detail: 'One command that renames a session and keeps kitty tab titles, saved session files, and the agent journal aligned.',
  },
  {
    title: 'Broadcast input across split panes',
    detail: 'Send one keystroke stream to every pane of a tab like tmux synchronize-panes, with an unmistakable bar indicator while active.',
  },
  {
    title: 'Side sheet and wider platform verification',
    detail: 'A richer hover-ready inspector inside the panel, live-verified markers for more CLIs, and non-/proc agent detection for macOS.',
  },
] as const;

/** Honest roadmap anchored in docs/feature-status.yaml and docs/developer/roadmap.mdx. */
export function Roadmap() {
  return (
    <section id="roadmap" aria-labelledby="roadmap-title" className="border-y border-line bg-page py-20 lg:py-28">
      <div className="mx-auto w-full max-w-[1220px] px-5 md:px-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-[54ch]">
            <h2 id="roadmap-title" className="t-h2">Where kittymux goes next</h2>
            <p className="t-body mt-4 text-mute">
              Ordered by value to people who live in kitty all day. Nothing here carries a fake release date, and every planned item is tracked openly in the repository.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-6">
            <DocLink slug="developer/roadmap" className="inline-flex min-h-11 items-center font-semibold text-link underline underline-offset-4">
              Read the full roadmap
            </DocLink>
            <DocLink slug="users/what-you-can-do" className="inline-flex min-h-11 items-center font-semibold text-ink underline underline-offset-4">
              Feature status table
            </DocLink>
          </div>
        </div>

        <div className="mt-14 grid gap-12 lg:grid-cols-2 lg:gap-16">
          <div className="tactile rounded-2xl p-6 sm:p-8">
            <h3 className="t-h3 text-ink">In progress and beta</h3>
            <dl className="mt-6 divide-y divide-line border-t border-line">
              {IN_PROGRESS.map((item) => (
                <div key={item.title} className="py-5">
                  <dt className="t-h3 text-ink">{item.title}</dt>
                  <dd className="t-body mt-1.5 text-mute">{item.detail}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="tactile rounded-2xl p-6 sm:p-8">
            <h3 className="t-h3 text-ink">Planned next</h3>
            <dl className="mt-6 divide-y divide-line border-t border-line">
              {PLANNED_NEXT.map((item) => (
                <div key={item.title} className="py-5">
                  <dt className="t-h3 text-ink">{item.title}</dt>
                  <dd className="t-body mt-1.5 text-mute">{item.detail}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
