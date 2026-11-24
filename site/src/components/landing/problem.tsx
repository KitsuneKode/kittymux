import { useState } from 'react';
import { Shot, TerminalWindow } from '../terminal-window';

const GAINS = [
  ['Lit brand tiles and live states', 'Every tab shows its agent mark, a working wave, a Needs you chip with the exact question, a failure cross, or a reset countdown.'],
  ['Grouped by project and branch', 'Titles stay human-readable and sit under their repo and git branch, with settled groups folding out of your way.'],
  ['OSC 9;4 progress and safe close', 'Build and download progress draws as a crisp hairline. Closing a busy or waiting agent asks once on its row before killing the tab.'],
] as const;

const MODES = [
  {
    id: 'pxbar',
    label: 'Pixel bar (pxbar)',
    plate: 'FIG. 02 — KITTYMUX PIXEL BAR (OPT-IN)',
    shot: 'pxbar',
    alt: 'The kittymux pixel tab bar rendered inside kitty with lit brand tiles, project groups, Needs you chips, an animated working wave, OSC 9;4 progress hairlines, and a usage limit countdown.',
    caption: 'Opt-in pixel bar (kittymux settings on pxbar): Cairo/Pango rendering inside kitty with Slang shader hover, glass cards, and animated working wave.',
  },
  {
    id: 'cell',
    label: 'Cell bar (default)',
    plate: 'FIG. 02 — KITTYMUX CELL BAR (DEFAULT)',
    shot: 'bar',
    alt: 'The zero-dependency kittymux vertical cell bar with nine made-up tabs: one asks Do you want to proceed and carries a stripe, another is working.',
    caption: 'Default terminal-cell vertical bar: works everywhere kitty runs with zero graphics dependencies, live theme colours, and automatic fallback.',
  },
] as const;

const PINS = [
  { idx: 0, label: '01', style: { top: '21%', right: '5%' } },
  { idx: 1, label: '02', style: { top: '12%', left: '6%' } },
  { idx: 2, label: '03', style: { top: '64%', right: '5%' } },
] as const;

export function Problem() {
  const [mode, setMode] = useState<'pxbar' | 'cell'>('pxbar');
  const active = MODES.find((m) => m.id === mode) ?? MODES[0];

  return (
    <section aria-labelledby="problem" className="mx-auto w-full max-w-[1220px] px-5 py-20 md:px-8 lg:py-28">
      <div className="max-w-[54ch]">
        <h2 id="problem" className="t-h2">Nine tabs. Which one is waiting?</h2>
        <p className="t-body mt-4 text-mute">
          Run a few coding agents side by side and a horizontal tab strip stops telling you anything. You end up cycling tabs just to check who is stuck on a permission prompt.
        </p>
      </div>

      <div className="mt-10">
        <p className="plate-label mb-3">FIG. 01 — STOCK KITTY, NINE TABS</p>
        <TerminalWindow
          className="scroll-plate"
          caption="Before: stock kitty horizontal tabs. Truncated titles repeat whatever each agent last printed and hide every waiting prompt."
        >
          <Shot
            name="plain-tabs"
            alt="A stock kitty tab strip with nine tabs titled claude, codex, devin, Claude, zsh, and truncated replies; none shows a state."
          />
        </TerminalWindow>
      </div>

      <div className="problem-grid mt-20 grid items-start gap-12 lg:grid-cols-12 lg:gap-14">
        <div className="min-w-0 lg:col-span-5 lg:pt-4">
          <h3 className="t-h2">The same tabs, with kittymux</h3>
          <p className="t-body mt-4 text-mute">
            Start with the zero-dependency cell bar or turn on the pixel bar for lit brand marks, Slang shader cards, and smooth hover directly inside kitty.
          </p>

          <div className="mt-7 max-w-full min-w-0">
            <div role="tablist" aria-label="Compare tab bar renderers" className="seg-track">
              {MODES.map((m) => (
                <button
                  key={m.id}
                  role="tab"
                  type="button"
                  aria-selected={mode === m.id}
                  data-press=""
                  onClick={() => setMode(m.id)}
                  className="seg-tab"
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          <dl className="mt-10 divide-y divide-line border-t border-line">
            {GAINS.map(([title, desc], idx) => (
              <div key={title} data-gain={idx} tabIndex={0} className="group py-5 outline-offset-4">
                <dt className="flex items-baseline gap-3">
                  <span className="t-mono text-[0.8125rem] font-bold text-signal-ink">0{idx + 1}</span>
                  <span className="t-h3 text-ink">{title}</span>
                </dt>
                <dd className="t-body mt-1.5 ps-7 text-mute">{desc}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="lg:col-span-7 lg:flex lg:flex-col lg:items-end">
          <div className="mx-auto w-full max-w-[400px] lg:mx-0">
            <p className="plate-label mb-3">{active.plate}</p>
            <TerminalWindow
              key={active.id}
              className="stage-swap scroll-plate"
              caption={active.caption}
            >
              <div className="relative">
                <Shot name={active.shot} alt={active.alt} />
                {mode === 'pxbar' && PINS.map((pin) => (
                  <span key={pin.idx} data-pin={pin.idx} aria-hidden="true" className="bar-pin hidden sm:flex" style={pin.style}>
                    {pin.label}
                  </span>
                ))}
              </div>
            </TerminalWindow>
          </div>
        </div>
      </div>
    </section>
  );
}
