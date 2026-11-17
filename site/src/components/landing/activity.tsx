import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';

/**
 * The panel, drawn live: made-up tabs grouped by what they need from you (Needs you, Working, Finished), changing as
 * agents do. A sketch of kittymux's own panel, not a screenshot: the states, glyphs and order are the real ones
 * (docs/agents/status-contract.md). Idea after Rex's Activity mode, grouped by priority.
 *
 * Cost: one timer step every 2.6 s, only while the hero is on screen and the tab is visible. Reduced motion: the
 * first frame, still. Rows move between groups with a view transition where the browser has one; elsewhere they
 * simply appear in their new place.
 */
type State = 'waiting' | 'working' | 'done' | 'limited';
type Row = { id: string; agent: string; name: string; tab: string; state: State; line: string };

const START: Row[] = [
  { id: 'a', agent: 'claude', name: 'Claude Code', tab: 'api · auth refactor', state: 'working', line: 'Editing session.ts' },
  { id: 'b', agent: 'codex', name: 'Codex', tab: 'web · checkout', state: 'working', line: 'Running the tests' },
  { id: 'c', agent: 'gemini', name: 'Gemini CLI', tab: 'docs · migration', state: 'done', line: '+42 −7 in 3 files' },
  { id: 'd', agent: 'opencode', name: 'OpenCode', tab: 'infra · terraform', state: 'limited', line: 'Limit resets in 42 min' },
  { id: 'e', agent: 'amp', name: 'Amp', tab: 'mobile · onboarding', state: 'working', line: 'Reading 12 files' },
];

// Each step changes one row, as a real afternoon does.
const SCRIPT: [string, State, string][] = [
  ['a', 'waiting', 'Allow git push origin auth-refactor?'],
  ['b', 'done', '14 passed · +118 −40'],
  ['a', 'working', 'Pushing auth-refactor'],
  ['e', 'waiting', 'Which onboarding copy: A or B?'],
  ['c', 'working', 'Writing the upgrade notes'],
  ['e', 'working', 'Using variant B'],
  ['a', 'done', 'Opened PR #214'],
  ['b', 'working', 'Fixing the flaky cart test'],
  ['c', 'done', '+9 −2 in UPGRADING.md'],
];

const GROUPS: { state: State[]; title: string }[] = [
  { state: ['waiting', 'limited'], title: 'Needs you' },
  { state: ['working'], title: 'Working' },
  { state: ['done'], title: 'Finished' },
];

function Mark({ state }: { state: State }) {
  if (state === 'working')
    return <span aria-hidden className="act-spin block size-3.5 rounded-full border-2 border-[#8FB2E6]/30 border-t-[#8FB2E6]" />;
  if (state === 'waiting')
    return <span aria-hidden className="rounded-full bg-[var(--pink)] px-2 py-0.5 text-[11px] font-bold leading-none text-[var(--on-pink)]">needs you</span>;
  if (state === 'limited') return <span aria-hidden className="font-mono text-sm text-[#E8B04B]">⊘</span>;
  return <span aria-hidden className="font-mono text-sm text-[#7FD49B]">✓</span>;
}

export function ActivityDemo() {
  const [rows, setRows] = useState(START);
  const step = useRef(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    let timer: number | undefined;
    let onScreen = false;
    const tick = () => {
      const i = step.current % SCRIPT.length;
      const [id, state, line] = SCRIPT[i];
      const fresh = i === 0 && step.current > 0;            // the script starts over from the first frame
      step.current += 1;
      const apply = () => setRows((rs) => (fresh ? START : rs).map((r) => (r.id === id ? { ...r, state, line } : r)));
      const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown };
      if (doc.startViewTransition) doc.startViewTransition(() => flushSync(apply));
      else apply();
    };
    const sync = () => {
      const run = onScreen && document.visibilityState === 'visible';
      if (run && timer === undefined) timer = window.setInterval(tick, 2600);
      if (!run && timer !== undefined) { window.clearInterval(timer); timer = undefined; }
    };
    const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; sync(); }, { threshold: 0.25 });
    if (box.current) io.observe(box.current);
    document.addEventListener('visibilitychange', sync);
    return () => { io.disconnect(); document.removeEventListener('visibilitychange', sync); if (timer !== undefined) window.clearInterval(timer); };
  }, []);

  const needs = rows.filter((r) => r.state === 'waiting' || r.state === 'limited').length;   // the Needs you group, as the header counts it
  return (
    <div ref={box} className="font-sans text-[var(--code-fg)]">
      <p className="sr-only">
        An illustration of the kittymux panel with made-up tabs, grouped by what they need: some agents need you, some are working, some have finished.
      </p>
      <div aria-hidden className="select-none">
        {/* the panel's header: the session and the machine, and what needs you, in words */}
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div>
            <div className="text-sm font-semibold">work</div>
            <div className="text-xs text-white/70">laptop · {rows.length} tabs</div>
          </div>
          <div className="text-xs font-medium text-white/70">{needs ? `${needs} need${needs === 1 ? 's' : ''} you` : 'nothing needs you'}</div>
        </div>
        {/* a fixed height (all three groups, five rows): rows moving between groups never move the page */}
        <div className="h-[376px] space-y-3 overflow-hidden px-2 py-3">
          {GROUPS.map((g) => {
            const list = rows.filter((r) => g.state.includes(r.state));
            if (!list.length) return null;
            return (
              <div key={g.title}>
                <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-white/70">{g.title} · {list.length}</div>
                <ul className="space-y-1">
                  {list.map((r) => (
                    <li
                      key={r.id}
                      style={{ viewTransitionName: `act-${r.id}`, viewTransitionClass: 'act' } as React.CSSProperties}
                      className={`flex items-center gap-3 rounded-lg px-2 py-2 ${r.state === 'waiting' ? 'bg-white/[0.07]' : ''}`}
                    >
                      <img src={`/brand/agents/${r.agent}.png`} width={28} height={28} alt="" className="size-7 shrink-0 rounded-[22%]" />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{r.tab}</div>
                        <div className={`truncate text-xs ${r.state === 'waiting' ? 'text-white/85' : 'text-white/55'}`}>{r.line}</div>
                      </div>
                      <Mark state={r.state} />
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
