# 013 — Usage dashboard inside kitty

Goal approved by user: a readable persistent Agents/Usage panel inspired by T3 Code and Unixporn, with useful graphs and native kitty support.

Direction: compact provider cards, quiet live-theme surfaces, clear selected navigation, aligned values and text-first status. Filled quota meter and remaining track must look different (current screenshot colors the whole bar identically). Show remaining/used explicitly and retain reset information; elapsed windows are not consumed quota. Word-wrap prose/numeric groups, split long paths only when necessary. Dense at 16/32 columns, use available width without giant decoration.

Add bounded private numeric quota snapshots when existing collectors finish; show genuine historical trend with fixed 0–100% scale and gaps for unavailable samples. Use existing version-2 exact daily counters for a labeled seven-day activity chart; absence is not zero. Never estimate a percentage from Claude token totals. Default overview keeps quotas and main local counters; d toggles source/plan/diagnostic detail. Loading/error/stale states include visible refresh/back/close controls. Charts are static; no new animation, polling rate or runtime.

Read cache/history only on the existing bounded background worker. Usage mode should skip agent snapshot/PR/ports collection it does not display. Verify narrow/normal/light/dark, wide Unicode/control text, empty/loading/errors and real Wayland persistence with focus unchanged. No browser/eww/Bun migration. References: https://www.reddit.com/r/unixporn/comments/wosl44/bspwm_decided_to_finally_learn_how_to_use_eww/ and https://elkowar.github.io/eww/widgets.html (visual inspiration, no dotfile copying).

Implementation complete. Verification and application boundaries: [execution record](../docs/audit-2026-10-07-plan-review.md).
