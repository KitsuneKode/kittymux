import { facts } from '@/lib/facts';
import { Shot, TerminalWindow } from '../terminal-window';

export function HowItKnows() {
  return (
    <section aria-labelledby="how" className="border-y border-line bg-card py-16 lg:py-24">
      <div className="mx-auto w-full max-w-[1280px] px-5 md:px-8">
        <h2 id="how" className="t-h2 max-w-[20ch]">How it knows, and why you can trust it</h2>
        <p className="t-lead mt-4 max-w-[58ch] text-mute">
          kittymux reads the bottom of each agent’s screen twice a second and combines it with the agent’s own hooks. A state needs <strong className="font-semibold text-ink">evidence</strong>. A quiet screen is never “waiting”, and an interrupted turn is never “finished”.
        </p>
        <p className="mt-4 max-w-[58ch] text-mute">
          Agents that speak the <a className="text-link underline" href="https://www.superlogical.com/rex/docs/build/program-status">Program Status Protocol</a> (OSC 7501: Claude Code, Pi, Crush) say for themselves when they are working, blocked on a question or done. kitty 0.50 keeps those reports, and kittymux reads them first, for every window, however the agent was started. The screen is the fallback for agents that don’t report.
        </p>
        <div className="mt-10 grid gap-10 lg:grid-cols-12 lg:items-start">
        <TerminalWindow className="lg:col-span-5" caption="The real panel, docked, on made-up tabs: one needs you, one has a usage limit that resets in 42 minutes.">
          <Shot name="panel-agents" alt="The kittymux panel listing seven made-up tabs: one needs you and says so, one is done, and one hit a usage limit and shows when it resets." />
        </TerminalWindow>
        <div tabIndex={0} className="tactile overflow-x-auto rounded-xl lg:col-span-7">
          <table className="w-full min-w-[34rem] border-collapse text-start">
            <thead className="bg-card-hi text-sm">
              <tr>
                <th scope="col" className="px-4 py-3 text-start">Shown as</th>
                <th scope="col" className="px-4 py-3 text-start">State</th>
                <th scope="col" className="px-4 py-3 text-start">Meaning</th>
              </tr>
            </thead>
            <tbody>
              {facts.states.map((s) => (
                <tr key={s.id} className="border-t border-line">
                  <td className="px-4 py-3 font-mono text-lg" aria-label={`glyph for ${s.title}`}>{s.glyph || 'none'}</td>
                  <th scope="row" className="px-4 py-3 text-start font-semibold">{s.title}</th>
                  <td className="px-4 py-3 text-mute">{s.meaning}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </div>
      </div>
    </section>
  );
}
