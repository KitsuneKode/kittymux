"""devin.py — Devin CLI session/token activity from ATIF transcripts.

~/.local/share/devin/cli/transcripts/*.json carry final_metrics token
totals and agent model names. No account quota exists locally — we show
today's session/token burn, not a fabricated percentage.

live(): real daily/weekly quota via the same Connect-RPC the CLI's /usage
command calls — SeatManagementService/GetUserStatus on server.codeium.com,
authenticated with the windsurf_api_key in credentials.toml.
"""

import json
import subprocess
import time
import tomllib

from _common import HOME, LIVE_TTL, fmt_ago, fmt_tokens, fmt_wait


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


def live(cached_live: dict) -> dict:
    """Opt-in real quota via SeatManagementService/GetUserStatus — the RPC
    behind `devin /usage`. Returns remaining-percent quotas, so the bars
    show used = 100 - remaining. Cached 5min like the other live()s."""
    if cached_live and time.time() - cached_live.get("ts", 0) < LIVE_TTL:
        return cached_live
    cred = HOME / ".local" / "share" / "devin" / "credentials.toml"
    try:
        tok = tomllib.loads(cred.read_text()).get("windsurf_api_key")
    except (OSError, tomllib.TOMLDecodeError):
        return cached_live
    if not tok:
        return cached_live
    body = json.dumps({"metadata": {
        "apiKey": tok, "ideName": "devin_cli", "ideVersion": "1.0",
        "extensionName": "devin", "extensionVersion": "0.0.0"}})
    try:
        out = subprocess.run(
            ["curl", "-fsS", "--max-time", "4", "-X", "POST",
             "-H", "Content-Type: application/json",
             "-H", "connect-protocol-version: 1",
             "-d", body,
             "https://server.codeium.com/exa.seat_management_pb.SeatManagementService/GetUserStatus"],
            capture_output=True, text=True, timeout=6)
        data = json.loads(out.stdout) if out.returncode == 0 else {}
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return cached_live
    plan = (data.get("userStatus") or {}).get("planStatus") or {}
    if not plan:
        return cached_live
    rows = []
    for rem_key, reset_key, label in (
            ("dailyQuotaRemainingPercent", "dailyQuotaResetAtUnix", "day"),
            ("weeklyQuotaRemainingPercent", "weeklyQuotaResetAtUnix", "wk")):
        rem = plan.get(rem_key)
        if isinstance(rem, (int, float)):
            reset = plan.get(reset_key)
            try:
                reset_ts = float(reset) if reset else 0
            except (TypeError, ValueError):
                reset_ts = 0
            rows.append({"label": label, "pct": min(100.0, 100.0 - float(rem)),
                         "reset": f"resets {fmt_wait(reset_ts)}" if reset_ts else "",
                         "rem_s": reset_ts - time.time() if reset_ts else 0})
    name = (plan.get("planInfo") or {}).get("planName")
    if name:
        rows.append({"label": "plan", "text": name})
    try:
        over = float(plan.get("overageBalanceMicros") or 0) / 1e6
    except (TypeError, ValueError):
        over = 0
    if over:
        rows.append({"label": "over", "text": f"balance ${over:.2f}"})
    return {"ts": time.time(), "rows": rows} if rows else cached_live
