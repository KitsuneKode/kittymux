import { CopyButton } from '../copy-button';

/** The first command: it works before anything is installed, so the final call to action copies it too. */
export const DEMO_CMD = 'git clone https://github.com/KitsuneKode/kittymux ~/kittymux && ~/kittymux/bin/kittymux demo';
/** Look first, then install, in one line for people who are already sure. */
export const INSTALL_CMD = 'git clone https://github.com/KitsuneKode/kittymux ~/kittymux && ~/kittymux/install.sh';

const ROWS = [
  { title: 'Look first', cmd: DEMO_CMD, note: 'Opens its own window with made-up agents. Nothing of yours is read or changed.' },
  { title: 'Install', cmd: '~/kittymux/install.sh', note: 'Checks its dependencies, backs up kitty.conf and adds a few include lines. It never overwrites a key of yours.' },
  { title: 'Check', cmd: 'kittymux doctor', note: 'Lists anything that is off, and how to fix it.' },
  { title: 'Or all at once', cmd: INSTALL_CMD, note: 'Clone and install in one go, for when you already know.' },
] as const;

/** A list of rows, not a set of cards: the commands are the content, so each row is a name and a note on the left and the command, ready to copy, on the right. */
export function Install() {
  return (
    <section id="install" aria-labelledby="install-title" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="install-title" className="t-h2 max-w-[20ch]">Try it, then install it</h2>
      <p className="t-lead mt-4 max-w-[52ch] text-mute">The demo opens its own window and touches nothing of yours. When you like it, install takes one command.</p>
      <ol className="mt-12 flex flex-col gap-10">
        {ROWS.map((r) => (
          <li key={r.title} className="grid gap-4 lg:grid-cols-12 lg:gap-10">
            <div className="lg:col-span-4">
              <h3 className="t-h3">{r.title}</h3>
              <p className="t-small mt-2 max-w-[40ch] text-mute">{r.note}</p>
            </div>
            <div className="flex min-w-0 flex-col items-start gap-3 lg:col-span-8">
              <pre className="t-mono w-full whitespace-pre-wrap rounded-xl bg-[var(--code-bg)] p-4 text-[var(--code-fg)] [overflow-wrap:anywhere]"><code>{r.cmd}</code></pre>
              <CopyButton text={r.cmd} label="Copy command" context={r.title} className="border border-line hover:bg-card-hi" />
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
