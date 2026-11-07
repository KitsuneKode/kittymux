// Only the parts this scene uses, imported from their own modules: the kit's index would bring every part (phones, charts, brands)
import { Stage } from '../kit/stage'
import { Window, Bar } from '../kit/window'
import { Collapse } from '../kit/motion/Collapse'
import type { Act } from '../kit/act'
// served as files, never inlined as data: URLs (the site's budget counts those as requests that leave it)
import claude from './claude.svg?no-inline'
import openai from './openai.svg?no-inline'
import './hero.css'

// kittymux's hero: kitty's own vertical tab bar, drawn the way kittymux draws
// it, with one agent that comes to need you. Beats:
//   1. Three agents are working or done; you are in "og tags".
//   2. "api" stops: its second line turns to Needs you, the orange stripe
//      draws down its edge, the question opens under it, and the header
//      says "1 needs you".
//   3. The pointer goes to that row and clicks: the pane on the right is now
//      api's, asking "Allow edit to src/parser.rs?".
//   4. "1" is typed. The answer lands in the pane, the row goes back to
//      Working, the question and the stripe leave, the header count goes.
//   5. A hold on the result, then a click back on "og tags" (the loop's
//      cause), which is where it began.
//
// Real strings: the header count, three tab titles with their state words,
// the question, and the answer. Panes and the fourth row are filler.

type S = { asks: boolean; tab: 'og' | 'api'; answered: boolean }

const initial: S = { asks: false, tab: 'og', answered: false }

// where the pointer rests between loops: it starts here and comes back here, so the loop's seam is invisible
const REST = { wide: { x: 598, y: 328 }, compact: { x: 308, y: 285 } }

async function script(a: Act<S>) {
  await a.wait(1400)
  a.mark('asks')
  a.put({ asks: true })
  await a.wait(1300)
  await a.move({ at: 'row-api', x: 0.32, y: 0.22 })        // aim at the title, never on the branch glyph
  await a.click({ at: 'row-api', x: 0.32, y: 0.22 })
  a.mark('jump')
  a.put({ tab: 'api' })
  await a.wait(1100)
  await a.key('1')
  a.mark('answer')
  a.put({ answered: true, asks: false })
  await a.wait(2400)
  await a.move({ at: 'row-og', x: 0.32, y: 0.3 })
  await a.click({ at: 'row-og', x: 0.32, y: 0.3 })
  a.put({ tab: 'og' })
  await a.wait(500)
  await a.move(REST)
  await a.wait(400)
  await a.snap({ answered: false })
}

const WORD = {
  working: 'Working',
  waiting: 'Needs you',
  done: 'Finished',
} as const

type State = keyof typeof WORD

function Mark({ src }: { src: string }) {
  // the agent's real mark (assets/icons), tinted the way the bar tints its glyph
  return <i className="kh-mark" style={{ WebkitMaskImage: `url("${src}")`, maskImage: `url("${src}")` }} aria-hidden />
}

function Tab({ id, title, mark, brand, state, words = state ? [state] : [], branch, active, asks, question }: {
  id: string; title: string; mark?: string; brand?: string; state?: State; words?: State[]; branch: string; active: boolean; asks?: boolean; question?: string
}) {
  return (
    <div className="kh-tab" data-target={`row-${id}`} data-cursor="pointer" data-active={active || undefined} data-asks={asks || undefined}>
      <span className="kh-stripe" />
      <div className="kh-line">
        <span className="kh-glyph" style={brand ? ({ '--brand': brand } as React.CSSProperties) : undefined}>
          {mark ? <Mark src={mark} /> : <span className="kh-shell">›</span>}
        </span>
        <span className="kh-title">{title}</span>
      </div>
      <div className="kh-line kh-sub">
        {state ? (
          // every word the row can say sits in one cell and crossfades; the cell holds the widest, so the branch never moves
          <span className="kh-words">
            {words.map(w => (
              <span key={w} className="kh-word" data-state={w} data-on={w === state || undefined}>{WORD[w]}</span>
            ))}
          </span>
        ) : null}
        <span className="kh-branch">⑂ {branch}</span>
      </div>
      {question ? (
        <Collapse open={!!asks}>
          <div className="kh-line kh-question">{question}</div>
        </Collapse>
      ) : null}
    </div>
  )
}

export default function KittymuxHero() {
  return (
    <Stage<S>
      width={720}
      height={380}
      compact={{ below: 520, width: 358, height: 330 }}
      theme="dark"
      initial={initial}
      poster={{ asks: true, tab: 'og', answered: false }}
      script={script}
      cursor={{ at: REST, style: 'real' }}
      keys="bottom-right"
      className="kh"
    >
      {(s, _rect, layout) => (
        <Window chrome="terminal" lights="grey" title="kitty — website" className="kh-win" data-layout={layout}>
          <div className="kh-body">
            <nav className="kh-bar" aria-label="Tabs">
              <div className="kh-head">
                <div className="kh-session">website</div>
                <div className="kh-count">
                  6 tabs
                  <span className="kh-count-ask" data-open={s.asks || undefined}>
                    <span className="kh-ask"><span className="kh-sep">·</span> 1 needs you</span>
                  </span>
                </div>
              </div>
              <Tab id="og" title="og tags" mark={claude} brand="#d97757" state="working" branch="main" active={s.tab === 'og'} />
              <Tab
                id="api"
                title="api"
                mark={openai}
                brand="#e8e8ea"
                state={s.asks ? 'waiting' : 'working'}
                words={['working', 'waiting']}
                branch="fix/auth"
                active={s.tab === 'api'}
                asks={s.asks}
                question="Allow edit to parser.rs?"
              />
              <Tab id="mig" title="migrations" mark={claude} brand="#d97757" state="done" branch="release/2.4" active={false} />
              {[[64, 92], [48, 110], [72, 84]].map(([a, b], i) => (
                <div key={i} className="kh-tab kh-tab--filler">
                  <div className="kh-line"><Bar w={12} h={12} r={3} tone={2} /><Bar w={a} h={7} tone={2} /></div>
                  <div className="kh-line kh-sub"><Bar w={b} h={6} tone={1} /></div>
                </div>
              ))}
            </nav>
            <div className="kh-divider" />
            <section className="kh-pane" aria-label="Pane">
              <div className="kh-panes" data-tab={s.tab}>
                <div className="kh-pane-og">
                  <div className="kh-out"><Bar w={210} h={7} tone={2} /></div>
                  <div className="kh-out"><Bar w={160} h={7} tone={1} /></div>
                  <div className="kh-out"><Bar w={240} h={7} tone={1} /></div>
                  <div className="kh-out"><Bar w={190} h={7} tone={1} /></div>
                  <div className="kh-out"><Bar w={120} h={7} tone={1} /></div>
                  <div className="kh-out kh-gap"><Bar w={220} h={7} tone={2} /></div>
                  <div className="kh-out"><Bar w={150} h={7} tone={1} /></div>
                  <div className="kh-out kh-dim">Thinking · 3m 8s</div>
                </div>
                <div className="kh-pane-api">
                  <div className="kh-out"><Bar w={180} h={7} tone={2} /></div>
                  <div className="kh-out"><Bar w={230} h={7} tone={1} /></div>
                  <div className="kh-out"><Bar w={140} h={7} tone={1} /></div>
                  <div className="kh-out kh-gap"><Bar w={200} h={7} tone={2} /></div>
                  <div className="kh-out"><Bar w={170} h={7} tone={1} /></div>
                  <div className="kh-out kh-q">Allow edit to src/parser.rs?</div>
                  <div className="kh-out kh-opt" data-picked={s.answered || undefined}>❯ 1. Yes</div>
                  <div className="kh-out kh-opt kh-opt--no" data-answered={s.answered || undefined}>  2. No</div>
                  <Collapse open={s.answered}>
                    <div className="kh-out kh-ok">Editing src/parser.rs</div>
                  </Collapse>
                </div>
              </div>
            </section>
          </div>
        </Window>
      )}
    </Stage>
  )
}
