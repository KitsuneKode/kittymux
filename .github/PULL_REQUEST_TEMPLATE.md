## What and why
<!-- the problem in a sentence or two, then how this fixes it -->

## How it was verified
<!-- which tests you ran (unit / smoke rigs). Say what you did NOT verify: live provider, other compositor, other kitty version. -->

- [ ] `python3 -m unittest discover -s tests` and the shell tests pass
- [ ] real-kitty rig(s) for anything a human can feel (clicks, keys, drags), with real events
- [ ] docs / README key table / CHANGELOG updated where a user would look
- [ ] hostile-input test if this touches terminal text, files, sockets or anything we execute
