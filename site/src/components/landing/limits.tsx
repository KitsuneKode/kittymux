import { DocLink } from '../doc-link';

const ROWS = [
  ['Where it has run', 'Tested on kitty 0.49.1 and 0.49.2, on Arch Linux with Hyprland (Wayland). That is the author’s daily setup, including the docked panel.'],
  ['Not verified', 'macOS (agent detection reads /proc, which is Linux-only), kitty 0.48 and other compositors for the docked panel. Windows is not supported: kitty has no Windows build.'],
  ['What it never does', 'It sends nothing off your machine and runs no server or always-on daemon. Live usage quotas are opt-in. Notifications and the inbox never type into an agent.'],
] as const;

export function Limits() {
  return (
    <section aria-labelledby="limits" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="limits" className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl lg:text-5xl">What it is not, yet</h2>
      <dl className="mt-10 grid gap-6 md:grid-cols-3">
        {ROWS.map(([t, d]) => (
          <div key={t} className="rounded-2xl border border-line p-6">
            <dt className="text-lg font-semibold">{t}</dt>
            <dd className="mt-2 text-pretty text-mute">{d}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-6 text-mute">
        The full list, with what each agent CLI has been checked against, is on <DocLink slug="users/platforms" className="font-semibold text-link underline underline-offset-4">Platforms and compatibility</DocLink>.
      </p>
    </section>
  );
}
