"""devin.py — Devin CLI session/token activity from ATIF transcripts.

~/.local/share/devin/cli/transcripts/*.json carry final_metrics token
totals and agent model names. No account quota exists locally — we show
today's session/token burn, not a fabricated percentage.
"""

import json
import time

from _common import HOME, fmt_ago, fmt_tokens


def collect() -> dict:
    transcripts = HOME / ".local" / "share" / "devin" / "cli" / "transcripts"
    if not transcripts.is_dir():
        return {"name": "devin", "rows": [], "note": "not installed"}
    files = sorted(transcripts.glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"name": "devin", "rows": [], "note": "—"}
    midnight = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
    toks, sess, model = 0, 0, ""
    for f in files:
        try:
            if f.stat().st_mtime < midnight:
                break
            d = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sess += 1
        fm = d.get("final_metrics") or {}
        toks += (fm.get("total_prompt_tokens") or 0) \
            + (fm.get("total_completion_tokens") or 0)
        model = model or (d.get("agent") or {}).get("model_name") or ""
    if sess:
        return {"name": "devin", "rows": [
            {"label": "today", "text": f"{sess} sess · {fmt_tokens(toks)} tok"},
            *([{"label": "model", "text": model}] if model else [])]}
    try:
        ago = fmt_ago(files[0].stat().st_mtime)
    except OSError:
        ago = ""
    return {"name": "devin", "rows": [
        {"label": "last", "text": f"sess {ago}".strip()}]}
