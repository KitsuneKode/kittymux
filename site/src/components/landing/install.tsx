import { CopyButton } from '../copy-button';

/** The first command: it works before anything is installed, so the final call to action copies it too. */
export const DEMO_CMD = 'git clone https://github.com/KitsuneKode/kittymux ~/kittymux && ~/kittymux/bin/kittymux demo';

const STEPS = [
  { n: '1', title: 'Look first', cmd: DEMO_CMD, note: 'Opens its own window with made-up agents. Nothing of yours is read or changed.' },
  { n: '2', title: 'Install', cmd: '~/kittymux/install.sh', note: 'Checks its dependencies, backs up kitty.conf and adds a few include lines. It never overwrites a key of yours.' },
  { n: '3', title: 'Check', cmd: 'kittymux doctor', note: 'Lists anything that is off, and how to fix it.' },
] as const;

export function Install() {
  return (
    <section id="install" aria-labelledby="install-title" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="install-title" className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl lg:text-5xl">Three commands</h2>
      <ol className="mt-10 grid gap-6 lg:grid-cols-3">
        {STEPS.map((s) => (
          <li key={s.n} className="flex min-w-0 flex-col gap-4 rounded-2xl border border-line bg-card p-6">
            <span className="text-5xl font-bold tabular text-link">{s.n}</span>
            <h3 className="text-xl font-semibold">{s.title}</h3>
            <p className="text-pretty text-mute">{s.note}</p>
            <pre className="mt-auto whitespace-pre-wrap rounded-lg bg-[var(--code-bg)] p-4 font-mono text-sm text-[var(--code-fg)] [overflow-wrap:anywhere]"><code>{s.cmd}</code></pre>
            <CopyButton text={s.cmd} label="Copy command" context={s.title} className="self-start border border-line hover:bg-card-hi" />
          </li>
        ))}
      </ol>
    </section>
  );
}
