import { DocLink } from '../doc-link';

const ROWS = [
  ['Where it has run', 'Tested on kitty 0.49.1 and 0.49.2, on Arch Linux with Hyprland (Wayland). That is the author’s daily setup, including the docked panel.'],
  ['What is not verified', 'macOS (agent detection reads /proc, which is Linux-only), kitty 0.48 and other compositors for the docked panel. Windows is not supported: kitty has no Windows build.'],
  ['What it never does', 'It sends nothing off your machine and runs no server or always-on daemon. Live usage quotas are opt-in. Notifications and the inbox never type into an agent.'],
] as const;

/** Plain prose: the honest list reads best as sentences, not as three boxes. */
export function Limits() {
  return (
    <section aria-labelledby="limits" className="mx-auto grid w-full max-w-[1280px] gap-10 px-5 py-16 md:px-8 lg:grid-cols-12 lg:py-24">
      <h2 id="limits" className="t-h2 lg:col-span-5">What it is not, yet</h2>
      <div className="lg:col-span-6 lg:col-start-7">
        <dl className="flex flex-col gap-7">
          {ROWS.map(([t, d]) => (
            <div key={t}>
              <dt className="t-h3">{t}</dt>
              <dd className="t-body mt-2 text-mute">{d}</dd>
            </div>
          ))}
        </dl>
        <p className="t-body mt-8 text-mute">
          What each agent CLI has been checked against is on <DocLink slug="users/platforms" className="font-semibold text-link underline underline-offset-4">Platforms and compatibility</DocLink>.
        </p>
      </div>
    </section>
  );
}
