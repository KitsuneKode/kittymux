import { Shot, TerminalWindow } from '../terminal-window';

const COMMANDS = `kittymux sessions save
kittymux sessions restore
kittymux sessions history`;

export function Ideas() {
  return (
    <section aria-labelledby="ideas" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="ideas" className="text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl lg:text-5xl">Three things it does</h2>
      <div className="mt-12 grid gap-16">
        <div className="grid items-start gap-8 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-5">
            <p className="text-sm font-semibold uppercase tracking-[0.08em] text-link">01</p>
            <h3 className="mt-2 text-3xl font-bold tracking-[-0.02em]">See</h3>
            <p className="mt-3 max-w-[44ch] text-pretty text-lg text-mute">The bar names every tab by its task, marks the one that needs you with a stripe, and says how long it has waited. The usage view shows each provider’s limits, a notch where an even pace would be, and when each window resets.</p>
          </div>
          <div className="mx-auto w-full max-w-[460px] lg:col-span-7">
            <TerminalWindow caption="Made-up data.">
              <Shot name="panel-usage" alt="The usage view: four provider tiles, and a card with a five-hour and a weekly limit, each with a gauge, a notch for even pace and the time to reset." />
            </TerminalWindow>
          </div>
        </div>
        <div className="grid items-start gap-8 lg:grid-cols-12 lg:gap-12">
          <div className="lg:order-2 lg:col-span-5">
            <p className="text-sm font-semibold uppercase tracking-[0.08em] text-link">02</p>
            <h3 className="mt-2 text-3xl font-bold tracking-[-0.02em]">Act</h3>
            <p className="mt-3 max-w-[44ch] text-pretty text-lg text-mute">The inbox collects every question, permission request, limit and finished run as a card with Jump and Dismiss. A command palette finds a tab, an agent or an action by typing. Jump moves focus to the pane that is asking; it never types into it.</p>
          </div>
          <div className="mx-auto w-full max-w-[460px] lg:order-1 lg:col-span-7">
            <TerminalWindow caption="Made-up data.">
              <Shot name="panel-inbox" alt="Inbox cards: a question with Jump and Dismiss buttons, a permission request, and a chart of how long agents waited on you." />
            </TerminalWindow>
          </div>
        </div>
        <div className="grid items-start gap-8 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-5">
            <p className="text-sm font-semibold uppercase tracking-[0.08em] text-link">03</p>
            <h3 className="mt-2 text-3xl font-bold tracking-[-0.02em]">Come back</h3>
            <p className="mt-3 max-w-[44ch] text-pretty text-lg text-mute">Save a workspace and restore it later. Each agent window asks whether to resume its own conversation. It asks first; it never resumes by itself.</p>
          </div>
          <div className="lg:col-span-7">
            <pre tabIndex={0} className="overflow-x-auto rounded-xl bg-[var(--code-bg)] p-5 font-mono text-sm leading-relaxed text-[var(--code-fg)] outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10"><code>{COMMANDS}</code></pre>
          </div>
        </div>
      </div>
    </section>
  );
}
