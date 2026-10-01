# Launch checklist

Honest state first: this is **early-adopter ready**, not "everyone's terminal" ready. Tick these before
announcing; items marked ☐ are not done.

## Must (a stranger can install it and it works)
- [x] `./install.sh` is idempotent, backs up `kitty.conf`, never overwrites user keys
- [x] `kittymux doctor` explains every failure with the fix
- [x] `kittymux demo` shows everything in an isolated window (your config untouched)
- [x] `kittymux upgrade` (re-link, reload twice, doctor) and `kittymux hooks --remove` (clean undo)
- [x] Unit and shell regression suites, shellcheck `-S error`, CI workflow
- [x] Edge-case guide (`testing.md`) and draft demo/social copy (`social-launch.md`)
- [x] Real-kitty smoke tests: states, spinner frame rate, spacer-row click, upgrade-under-a-running-kitty
- [x] README: states table, privacy note, keys, drag & drop, layout/resizing, upgrade
- [x] Isolated fresh-HOME install → reinstall → config validation → uninstall smoke test
- [ ] First passing GitHub CI run recorded on the release commit (smoke jobs are configured)
- [ ] Per-theme screenshots/GIF (demo currently ships one theme; `assets/` images predate the status redesign)
- [ ] A tagged release + changelog; `packaging/PKGBUILD` checked against the tag

## Should
- [ ] Verify screen markers against live Gemini / Cursor / OpenCode / Amp / Antigravity sessions
- [ ] Test on a second compositor (sway or niri) and on X11 with a real WM
- [ ] Decide the story for macOS (needs a non-`/proc` foreground-process read)
- [ ] 60-second screen recording: spinner, `!` with the question, ⊘ limit, drag a split into a tab

## Do not claim
- "Works everywhere" — see `compatibility.md`.
- "Zero overhead" — measured ≈0.09 ms per tab draw and a 0.5 s scan tick; low, not zero.
- "Zero background processes" — there is no always-on daemon, but overlays, collectors and notifications use bounded workers/processes.
- "All bugs fixed" or "guaranteed viral" — maintain test evidence and honest compatibility limits instead.
