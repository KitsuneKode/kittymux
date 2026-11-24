import { DocLink } from '../doc-link';
import { Shot, TerminalWindow } from '../terminal-window';

const ARCHITECTURE = [
  {
    title: 'Direct agent hooks and OSC 7501 relay',
    body: 'Claude Code and Codex report turns and trailing questions directly through hooks. OpenCode gets an event plugin via kittymux hooks --opencode --install, and mux-pty relays OSC 7501 Program Status Protocol reports for Pi, Crush, and Claude Code. Live screen scanning reads the real buffer even while you scroll back in history.',
    cmd: 'kittymux hooks --opencode --install',
  },
  {
    title: 'Slang custom shaders and calm motion',
    body: 'On kitty 0.49 and newer with slangc, kittymux cards rounds active cards with subtle hover lift and optional compositor glass, while kittymux-pxwave.slang animates the working wave only while an agent runs. Measured at 0.59 ms for Usage rendering, 2.30 ms for a 60-event Inbox, and 0.9 percent idle CPU under Xvfb.',
    cmd: 'kittymux cards glass',
  },
  {
    title: 'One settings catalog and busy close guards',
    body: 'Twenty feature switches live in one catalog across kittymux settings and the panel’s Settings view. Closing a working or waiting agent asks once inline before killing the tab, and kittymux mute silences a pane’s popups while keeping every event recorded in the inbox.',
    cmd: 'kittymux settings',
  },
  {
    title: 'Session restore and plain-terminal prompts',
    body: 'Save and restore kitty workspaces with each agent window asking before resuming its own conversation. Even plain shells get covered: sudo, ssh, git, pacman, apt, and dnf waiting on a password or yes/no prompt in a background pane raise one quiet notification.',
    cmd: 'kittymux sessions restore',
  },
] as const;

/** Real major upgrades shipped across kittymux, laid out with alternating gallery rhythms instead of identical card rows. */
export function Ideas() {
  return (
    <section id="upgrades" aria-labelledby="upgrades-title" className="border-t border-line bg-card py-20 lg:py-28">
      <div className="mx-auto w-full max-w-[1220px] px-5 md:px-8">
        <div className="max-w-[54ch]">
          <h2 id="upgrades-title" className="t-h2">Built for real daily agent sessions</h2>
          <p className="t-body mt-4 text-mute">
            Every upgrade started from real friction while running multiple coding agents across workspaces: pixel panels, multi-account quotas, scoped pane docks, and direct agent state protocols.
          </p>
        </div>

        {/* Band A: Graphical Usage & Inbox side-by-side */}
        <div className="mt-14 grid items-start gap-12 border-t border-line pt-14 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <h3 className="t-h3 text-ink">Graphical Usage and Inbox in one pixel panel</h3>
            <p className="t-body mt-4 text-mute">
              The pixel panel now renders Usage and Inbox alongside Agents. Usage separates Personal and Work accounts, marks remaining quota with even-pace notches and reset countdowns, and reports exact sample ages.
            </p>
            <p className="t-body mt-4 text-mute">
              Inbox preserves unread attention ahead of routine history, keeps full error bodies, expands details with Space without acknowledging or moving focus, and lets you undo a dismissal with z for eight seconds.
            </p>
            <p className="t-small mt-6 text-mute">
              Enable both with <code className="t-mono rounded bg-card-hi px-2 py-0.5 text-ink">kittymux settings on deckpx</code>. Falls back cleanly to terminal cells when graphics packages are absent.
            </p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:col-span-7">
            <TerminalWindow caption="Pixel Usage: separate Personal and Work quota windows, pace markers, and live reset countdowns (synthetic accounts).">
              <Shot
                name="px-usage"
                alt="Graphical Usage panel showing Codex Personal at 70 percent left and Work at 0 percent left for five-hour and weekly windows with pace notches."
              />
            </TerminalWindow>
            <TerminalWindow caption="Pixel Inbox: unread attention ranked first, expandable messages, error bodies, and Jump / Dismiss actions (synthetic events).">
              <Shot
                name="px-inbox"
                alt="Graphical Inbox panel listing agent questions, permission prompts, build failed errors, finished runs, and quota limits."
              />
            </TerminalWindow>
          </div>
        </div>

        {/* Band B: Native Quickshell Client & Kitty 0.50 Pane Controls */}
        <div className="mt-20 grid items-start gap-12 border-t border-line pt-14 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <h3 className="t-h3 text-ink">Native Quickshell sidebar and live shell feeds</h3>
            <p className="t-body mt-4 max-w-[54ch] text-mute">
              Run <code className="t-mono rounded bg-card-hi px-1.5 py-0.5 text-ink">kittymux client</code> for a Wayland sidebar with proportional typography, calm state rings, and an inline mute menu. On Hyprland, experimental attach mode lays it right over kitty’s own vertical bar.
            </p>
            <p className="t-body mt-3 max-w-[54ch] text-mute">
              The same scanner publishes <code className="t-mono rounded bg-card-hi px-1.5 py-0.5 text-ink">tabs.json</code> and <code className="t-mono rounded bg-card-hi px-1.5 py-0.5 text-ink">agents.json</code> (mode 0600, including account names) so desktop shells and Waybar widgets never parse terminal output.{' '}
              <DocLink slug="users/the-client" className="font-semibold text-link underline underline-offset-4">Read the client guide</DocLink>
            </p>
            <TerminalWindow className="mt-8" caption="kittymux client in Hyprland attach mode: state rings, gliding selection mark, and live kitty theme colours.">
              <Shot
                name="client-attach"
                alt="The Quickshell client sitting in kitty’s vertical sidebar with state rings on Claude and Codex tabs beside a working terminal pane."
              />
            </TerminalWindow>
          </div>

          <div className="lg:col-span-5">
            <h3 className="t-h3 text-ink">Kitty 0.50 pane controls and attention rings</h3>
            <p className="t-body mt-4 text-mute">
              On Kitty 0.50 and newer, <code className="t-mono rounded bg-card-hi px-1.5 py-0.5 text-ink">kittymux pane-controls</code> optionally docks Split right, Split down, Zoom, Move to tab, guarded Close, and Hide beside a pane, scoped strictly to its owning window even after focus moves elsewhere.
            </p>
            <p className="t-body mt-3 text-mute">
              In multi-pane tabs, the divider beside a waiting or rate-limited pane lights up in kitty’s bell border colour without ringing a bell or moving focus.
            </p>
            <div className="mt-8 flex flex-col gap-6">
              <TerminalWindow className="max-w-[300px]" caption="Scoped Kitty 0.50 pane dock targeting its parent pane with busy-agent close guard.">
                <Shot
                  name="pane-controls"
                  alt="Kitty 0.50 pane controls dock showing R Right, D Down, Z Zoom, T Tab, X Close, and Hide above a terminal pane."
                />
              </TerminalWindow>
              <TerminalWindow caption="Native split layouts with direct ctrl+alt+1..9 pane focus, drag handles, and attention dividers.">
                <Shot
                  name="panes-layout"
                  alt="Four split panes inside kitty numbered pane 1 through pane 4 with the active pane border highlighted."
                />
              </TerminalWindow>
            </div>
          </div>
        </div>

        {/* Band C: Hairline-divided engineering ledger (no card cages) */}
        <div className="mt-20 border-t border-line pt-12">
          <div className="grid gap-x-12 gap-y-10 md:grid-cols-2">
            {ARCHITECTURE.map((item) => (
              <div key={item.title} className="flex flex-col justify-between gap-4 border-t border-line pt-6 first:border-t-0 md:first:border-t md:pt-6">
                <div>
                  <h3 className="t-h3 text-ink">{item.title}</h3>
                  <p className="t-body mt-2.5 text-mute">{item.body}</p>
                </div>
                <p className="t-mono text-link">{item.cmd}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
