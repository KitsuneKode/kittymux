# Launch kit: prove the benefit, not the hype

## Positioning

**Run several coding agents in kitty. Know which one needs you. Jump there.**

The audience is developers who already use kitty on Linux, especially tiling-WM users.
Lead with one recognizable interruption: two agents are working, a third needs approval,
and the user should not have to search every tab. Do not pitch a universal terminal replacement.

## A 25–35 second recording

Use isolated demo state and fake prompts, not live work:

1. **0–5 s:** show a few agent tabs and a split. Caption: “Which agent is waiting on me?”
2. **5–12 s:** a permission question appears; the tab and header attention count update.
3. **12–20 s:** one attention-jump shortcut lands on the asking pane. Show the actual question.
4. **20–27 s:** open the deck and hover a pane to show its preview; briefly collapse the bar.
5. **27–35 s:** show the mascot, repo name and `kittymux demo`. End on a readable URL.

Keep cursor movement deliberate and text legible on a phone. Export one clean landscape clip;
make a tighter crop only if it still shows the relationship between the status and the target pane.
Use the same theme throughout; a separate second-theme still can demonstrate theme inheritance.
The recording is not proof of unverified agent markers or cross-platform support.

## Suggested X post

> I kept checking every terminal tab to see which coding agent needed me.
>
> So I built kittymux: agent-aware tabs and pane previews for kitty, with one shortcut to jump to the agent asking for approval.
>
> Linux + kitty. No extra multiplexer daemon. Try it without changing your config:
> `kittymux demo`
>
> https://github.com/KitsuneKode/kittymux

Attach the short clip. Keep installation details in the repo, not in the first frame.
A follow-up can explain that the screen scanner and hooks share one status resolver, with
“done” clearing after focus. Link the compatibility page rather than claiming every agent works.

## Before posting

- [ ] The branch is reconciled, merged safely and verified; release notes explain behavior changes.
- [ ] GitHub CI has actually run on the release commit (a workflow file is not a passing run).
- [ ] The private demo command and install/uninstall instructions work from a clean checkout.
- [ ] Clip contains no personal paths, real questions, credentials or usage/account data.
- [ ] Demo shows the current UI; no staged feature is presented as implemented.
- [ ] Brand attribution/trademark note and supported Linux/kitty versions are visible in the README.
- [ ] Capture device/version/theme and the commands used so the demo can be recreated.

## What to learn after launch

Ask early users which agent/compositor they run and what happened on first use. Prioritize
reproducible installation failures, false attention states and missed jumps over adding more
features. Watch demo-to-first-use friction and useful issue reports, not just impressions.
Record bugs as sanitized screen fixtures or isolated CLI cases, then add a regression test.

A strong demo and a reliable first run improve the odds of sharing. Neither guarantees virality.
Do not push, publish a release, or post this copy without the maintainer's approval.
