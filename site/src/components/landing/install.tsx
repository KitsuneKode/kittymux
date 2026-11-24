import { CopyButton } from '../copy-button';

/** The first command: it works before anything is installed, so the final call to action copies it too. */
export const DEMO_CMD = 'git clone https://github.com/KitsuneKode/kittymux ~/kittymux && ~/kittymux/bin/kittymux demo';
/** Look first, then install, in one line for people who are already sure. */
export const INSTALL_CMD = 'git clone https://github.com/KitsuneKode/kittymux ~/kittymux && ~/kittymux/install.sh';

const ROWS = [
  {
    num: '01',
    title: 'Look first',
    cmd: DEMO_CMD,
    note: 'Opens an isolated kitty window with synthetic agents. Add --px --light to preview the pixel bar in daylight. Nothing in your config is changed.',
  },
  {
    num: '02',
    title: 'Install into kitty',
    cmd: INSTALL_CMD,
    note: 'Checks dependencies, backs up kitty.conf, and adds include lines. Never overwrites your own key bindings.',
  },
  {
    num: '03',
    title: 'Turn on pixel upgrades and hooks',
    cmd: 'kittymux settings preset pixel && kittymux hooks --install',
    note: 'Enables the Cairo/Slang pixel tab bar, graphical Usage and Inbox panel, busy-close guard, and direct agent hooks. Cell fallback stays automatic.',
  },
  {
    num: '04',
    title: 'Verify your setup',
    cmd: 'kittymux doctor',
    note: 'Checks kitty version, socket-only remote control, renderer packages, and window-manager key clashes.',
  },
] as const;

export function Install() {
  return (
    <section id="install" aria-labelledby="install-title" className="mx-auto w-full max-w-[1220px] px-5 py-20 md:px-8 lg:py-28">
      <div className="max-w-[54ch]">
        <h2 id="install-title" className="t-h2">Try it, then install it</h2>
        <p className="t-body mt-4 text-mute">
          Start with the isolated demo window. When you are ready, installation takes one command and every pixel upgrade is opt-in.
        </p>
      </div>

      <ol className="mt-12 divide-y divide-line border-t border-line">
        {ROWS.map((r) => (
          <li key={r.title} className="grid gap-5 py-8 lg:grid-cols-12 lg:items-start lg:gap-10">
            <div className="lg:col-span-4">
              <div className="flex items-baseline gap-3">
                <span className="t-mono text-[0.875rem] font-bold text-signal-ink">{r.num}</span>
                <h3 className="t-h3 text-ink">{r.title}</h3>
              </div>
              <p className="t-body mt-2 max-w-[38ch] ps-7 text-mute">{r.note}</p>
            </div>
            <div className="flex min-w-0 flex-col items-start gap-3 lg:col-span-8">
              <pre className="t-mono w-full whitespace-pre-wrap rounded-xl bg-[var(--code-bg)] px-5 py-4 text-[var(--code-fg)] [overflow-wrap:anywhere]">
                <code>{r.cmd}</code>
              </pre>
              <CopyButton text={r.cmd} label="Copy command" context={r.title} className="raised" />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
