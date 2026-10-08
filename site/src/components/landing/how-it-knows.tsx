import { facts } from '@/lib/facts';

export function HowItKnows() {
  return (
    <section aria-labelledby="how" className="border-y border-line bg-card py-16 lg:py-24">
      <div className="mx-auto w-full max-w-[1280px] px-5 md:px-8">
        <h2 id="how" className="t-h2 max-w-[20ch]">How it knows, and why you can trust it</h2>
        <p className="t-lead mt-4 max-w-[58ch] text-mute">
          kittymux reads the bottom of each agent’s screen twice a second and combines it with the agent’s own hooks. A state needs <strong className="font-semibold text-ink">evidence</strong>. A quiet screen is never “waiting”, and an interrupted turn is never “finished”.
        </p>
        <div tabIndex={0} className="mt-10 overflow-x-auto rounded-xl border border-line">
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
    </section>
  );
}
