import { useDeferredValue, useMemo, useState } from 'react';
import type { Facts } from '@/lib/facts';

export function filterKeys(keys: Facts['keys'], query: string): Facts['keys'] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return keys;
  return keys
    .map((s) => ({ ...s, rows: s.rows.filter((r) => words.every((w) => `${s.section} ${r.key} ${r.desc}`.toLowerCase().includes(w))) }))
    .filter((s) => s.rows.length);
}

export function KeyTable({ keys }: { keys: Facts['keys'] }) {
  const [query, setQuery] = useState('');
  const deferred = useDeferredValue(query);
  const shown = useMemo(() => filterKeys(keys, deferred), [keys, deferred]);
  const count = shown.reduce((n, s) => n + s.rows.length, 0);
  return (
    <div>
      <label className="block">
        <span className="sr-only">Filter keys</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter: type a key, a word, a section"
          className="min-h-12 w-full max-w-xl rounded-full border border-line bg-card px-5 text-base text-ink outline-none placeholder:text-mute focus-visible:border-ink"
        />
      </label>
      <p className="mt-3 text-sm text-mute" aria-live="polite">
        <span className="tabular">{count}</span> keys shown
      </p>
      {shown.length === 0 && <p className="mt-8 text-lg">No key matches “{query}”. Clear the filter to see all of them.</p>}
      {shown.map((s) => {
        const id = `k-${s.section.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
        return (
          <section key={s.section} aria-labelledby={id} className="mt-10">
            <h2 id={id} className="text-sm font-semibold uppercase tracking-[0.08em] text-link">
              {s.section}
            </h2>
            <div role="region" aria-label={`${s.section} keys`} tabIndex={0} className="mt-3 overflow-x-auto rounded-xl border border-line">
              <table className="w-full min-w-[28rem] border-collapse">
                <tbody>
                  {s.rows.map((r) => (
                    <tr key={r.key + r.desc} className="border-t border-line first:border-t-0">
                      <th scope="row" className="w-[16rem] px-4 py-3 text-start align-top">
                        <kbd className="rounded-md border border-line bg-card px-2 py-1 font-mono text-sm">{r.key}</kbd>
                      </th>
                      <td className="px-4 py-3 text-mute">{r.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
