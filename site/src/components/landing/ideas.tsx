import { Shot, TerminalWindow } from '../terminal-window';

const COMMANDS = `kittymux sessions save
kittymux sessions restore
kittymux sessions history`;

/** Two columns of unequal width, each a short text over its own screenshot, then one wide band: a bento rhythm instead of a left-right zigzag. */
export function Ideas() {
  return (
    <section aria-labelledby="ideas" className="mx-auto w-full max-w-[1280px] px-5 py-16 md:px-8 lg:py-24">
      <h2 id="ideas" className="t-h2">What it does</h2>
      <div className="mt-12 grid gap-x-12 gap-y-20 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <h3 className="t-h3 sm:text-[1.75rem]">See</h3>
          <p className="t-body mt-3 max-w-[50ch] text-mute">The bar names every tab by its task, marks the one that needs you with a stripe, and says how long it has waited. The usage view shows each provider’s limits, a notch where an even pace would be, and when each window resets.</p>
          <TerminalWindow className="mt-8 max-w-[460px]" caption="Made-up data.">
            <Shot name="panel-usage" alt="The usage view: four provider tiles, and a card with a five-hour and a weekly limit, each with a gauge, a notch for even pace and the time to reset." />
          </TerminalWindow>
        </div>
        <div className="lg:col-span-5 lg:pt-24">
          <h3 className="t-h3 sm:text-[1.75rem]">Act</h3>
          <p className="t-body mt-3 max-w-[44ch] text-mute">The inbox collects every question, permission request, limit and finished run as a card with Jump and Dismiss. A command palette finds a tab, an agent or an action by typing. Jump moves focus to the pane that is asking; it never types into it.</p>
          <TerminalWindow className="mt-8 max-w-[460px]" caption="Made-up data.">
            <Shot name="panel-inbox" alt="Inbox cards: a question with Jump and Dismiss buttons, a permission request, and a chart of how long agents waited on you." />
          </TerminalWindow>
        </div>
        <div className="lg:col-span-12">
          <h3 className="t-h3 sm:text-[1.75rem]">Come back</h3>
          <p className="t-body mt-3 max-w-[56ch] text-mute">Save a workspace and restore it later. Each agent window asks whether to resume its own conversation. It asks first; it never resumes by itself.</p>
          <pre tabIndex={0} className="t-mono mt-6 overflow-x-auto rounded-xl bg-[var(--code-bg)] p-5 text-[var(--code-fg)] outline outline-1 -outline-offset-1 outline-black/10 dark:outline-white/10"><code>{COMMANDS}</code></pre>
        </div>
      </div>
    </section>
  );
}
