import { Shot, TerminalWindow } from '../terminal-window';

const GAINS = [
  ['A stripe and the question', 'The tab that needs you is marked, and says what it is asking.'],
  ['A project under every name', 'Titles are whatever the agent last said. The folder and branch say where it is.'],
  ['How long it has waited', 'And, for a usage limit, when it lifts.'],
] as const;

export function Problem() {
  return (
    <section aria-labelledby="problem" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="problem" className="max-w-[18ch] text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl lg:text-5xl">Nine tabs. Which one is waiting?</h2>
      <p className="mt-4 max-w-[52ch] text-pretty text-lg text-mute">Run a few agents side by side and the tab strip stops telling you anything. Is it done? Is it stuck? Is it asking you?</p>
      <TerminalWindow className="mt-10 max-w-[960px]" caption="Before: kitty's own tab strip. Titles are cut off and say whatever each agent last said.">
        <Shot name="plain-tabs" alt="A stock kitty tab strip with nine tabs titled claude, codex, devin, Claude…, zsh, I can'… and so on; none shows a state." />
      </TerminalWindow>
      <div className="mt-16 grid items-center gap-10 lg:grid-cols-12">
        <div className="lg:col-span-6">
          <h3 className="text-2xl font-bold tracking-[-0.02em] sm:text-3xl">The same kind of tabs, with kittymux</h3>
          <dl className="mt-6 flex flex-col gap-5">
            {GAINS.map(([t, d]) => (
              <div key={t}>
                <dt className="font-semibold">{t}</dt>
                <dd className="mt-1 max-w-[46ch] text-pretty text-mute">{d}</dd>
              </div>
            ))}
          </dl>
        </div>
        <TerminalWindow className="mx-auto w-full max-w-[380px] lg:col-span-6" caption="Made-up tabs. The bar lives down the side, so titles have room.">
          <Shot name="bar" alt="The kittymux vertical bar with nine made-up tabs: one asks 'Do you want to proceed?' and carries a stripe, another is working." />
        </TerminalWindow>
      </div>
    </section>
  );
}
