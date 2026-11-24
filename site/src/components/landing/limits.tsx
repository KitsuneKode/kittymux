import { DocLink } from '../doc-link';

const ROWS = [
  [
    'Where it is verified',
    'Tested in continuous integration across kitty 0.49.1, 0.49.2, and 0.50.0 with 1,990+ unit tests and private Xvfb graphics and pointer rigs. Daily driven on Arch Linux with Hyprland (Wayland).',
  ],
  [
    'What is not verified yet',
    'macOS (agent detection reads /proc, which is Linux-only), Wayland compositors other than Hyprland for the docked panel and attach mode, and live cloud provider APIs inside CI. Windows is unsupported because kitty has no Windows build.',
  ],
  [
    'What it never does',
    'It runs no always-on background daemon and sends nothing off your machine. Live usage quotas are opt-in, remote control uses socket-only permissions, and notifications or expanded inbox cards never steal focus or type into a pane.',
  ],
] as const;

/** Warm apricot full-bleed editorial field band: distinct structural honesty with high-contrast indigo ink. */
export function Limits() {
  return (
    <section data-field="" aria-labelledby="limits" className="bg-field text-onfield">
      <div className="mx-auto grid w-full max-w-[1220px] gap-10 px-5 py-20 md:px-8 lg:grid-cols-12 lg:py-28">
        <div className="lg:col-span-5">
          <h2 id="limits" className="t-h2 text-onfield">What it is, and what it is not</h2>
          <p className="t-body mt-4 max-w-[38ch] text-field-muted">
            Clear boundaries about what has run on real hardware versus virtual displays, and what stays strictly off-limits.
          </p>
        </div>
        <div className="lg:col-span-6 lg:col-start-7">
          <dl className="divide-y divide-[color-mix(in_oklch,#15172E_18%,transparent)] border-t border-[color-mix(in_oklch,#15172E_18%,transparent)]">
            {ROWS.map(([title, desc]) => (
              <div key={title} className="py-5">
                <dt className="t-h3 text-onfield">{title}</dt>
                <dd className="t-body mt-2 text-field-muted">{desc}</dd>
              </div>
            ))}
          </dl>
          <p className="t-body mt-6 text-field-muted">
            Per-agent verification details live on <DocLink slug="users/platforms" className="font-semibold text-onfield underline decoration-2 underline-offset-4">Platforms and compatibility</DocLink>.
          </p>
        </div>
      </div>
    </section>
  );
}
