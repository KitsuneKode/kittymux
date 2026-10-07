#!/usr/bin/env bash
# Regenerates every screenshot the documentation site shows, from the repository's own rigs on synthetic data (nothing of yours appears).
# Slow (a few minutes); run it when the UI changes, then commit site/public/assets/shots.
#   bash tools/build-site-assets.sh
set -euo pipefail
HOME_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT="$HOME_DIR/site/public/assets/shots"
export TMPDIR=${TMPDIR:-$HOME/.cache/kmx}        # a short path: a kitty socket path over ~107 characters silently fails
mkdir -p "$OUT" "$TMPDIR/site-shots"
WORK="$TMPDIR/site-shots"

for theme in dark light; do
  bash "$HOME_DIR/tests/shot_bar.sh" "$theme" "$OUT/bar-$theme.png"
  bash "$HOME_DIR/tests/shot_panel.sh" "$theme" "$WORK/panel-$theme" 38 44
  # the Agents rows come from the made-up tabs of tools/demo_agents.py (the panel rig's own Agents view lists the worktree it runs in)
  bash "$HOME_DIR/tests/shot_agents.sh" "$theme" "$WORK/agents-$theme.png" 38 30
  convert "$WORK/agents-$theme.png" -trim +repage -bordercolor "$(convert "$WORK/agents-$theme.png" -format '%[pixel:p{2,2}]' info:)" -border 6 "$OUT/panel-agents-$theme.png"
  # the cards, without the empty rest of a tall panel
  convert "$WORK/panel-$theme/usage-codex.png" -crop "x500+0+0" +repage "$OUT/panel-usage-$theme.png"
  convert "$WORK/panel-$theme/inbox-needs.png" -crop "x500+0+0" +repage "$OUT/panel-inbox-$theme.png"
  bash "$HOME_DIR/tests/shot_plain_tabs.sh" "$theme" "$OUT/plain-tabs-$theme.png"
  bash "$HOME_DIR/tests/shot_panes.sh" "$theme" "$WORK/panes-$theme"
  for n in layout numbers resized equalized; do
    [ -f "$WORK/panes-$theme/panes-$n-$theme.png" ] && cp "$WORK/panes-$theme/panes-$n-$theme.png" "$OUT/panes-$n-$theme.png"
  done
done

python3 - "$OUT" <<'PY'
import json, os, struct, sys
out = sys.argv[1]
def size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])
files = {n: dict(zip(("width", "height"), size(os.path.join(out, n)))) for n in sorted(os.listdir(out)) if n.endswith(".png")}
json.dump(files, open(os.path.join(out, "manifest.json"), "w"), indent=2)
print(f"{len(files)} screenshots in {out}")
PY
