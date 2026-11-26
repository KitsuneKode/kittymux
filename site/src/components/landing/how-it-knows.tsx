import { facts } from '@/lib/facts';

const STATE_TONE: Record<string, string> = {
  waiting: '#F6C453',
  working: '#60A5FA',
  done: '#4ADE80',
  error: '#FB7185',
  limited: '#F59E0B',
  idle: '#A4A6BF',
};

export function HowItKnows() {
  return (
    <section aria-labelledby="how" className="mx-auto w-full max-w-[1220px] px-5 py-20 md:px-8 lg:py-28">
      <div className="max-w-[58ch]">
        <h2 id="how" className="t-h2">How it knows, and why you can trust it</h2>
        <p className="t-body mt-4 text-mute">
          kittymux combines direct agent hooks, the OpenCode event plugin, and the OSC 7501 status relay with live-buffer screen reads that stay accurate even when you scroll up. A state needs <strong className="font-semibold text-ink">evidence</strong>: silence is never waiting, and an error is never marked finished.
        </p>
      </div>
      <div tabIndex={0} className="tactile mt-10 overflow-x-auto rounded-2xl">
        <table className="w-full min-w-[34rem] border-collapse text-start">
          <thead className="bg-card-hi text-[0.875rem] font-semibold text-ink">
            <tr>
              <th scope="col" className="px-5 py-3.5 text-start">Shown as</th>
              <th scope="col" className="px-5 py-3.5 text-start">State</th>
              <th scope="col" className="px-5 py-3.5 text-start">Meaning</th>
            </tr>
          </thead>
          <tbody>
            {facts.states.map((s) => (
              <tr key={s.id} className="border-t border-line">
                <td className="px-5 py-3.5" aria-label={`glyph for ${s.title}`}>
                  <span
                    className="inline-flex min-w-10 items-center justify-center rounded-lg bg-[var(--code-bg)] px-2.5 py-1 font-mono text-[1rem] font-bold"
                    style={{ color: STATE_TONE[s.id] ?? '#F4EDE1' }}
                  >
                    {s.glyph || '—'}
                  </span>
                </td>
                <th scope="row" className="px-5 py-3.5 text-start font-semibold text-ink">{s.title}</th>
                <td className="t-body px-5 py-3.5 text-mute">{s.meaning}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
