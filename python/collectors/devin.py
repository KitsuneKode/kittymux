"""devin.py — Devin CLI session/token activity from ATIF transcripts.

~/.local/share/devin/cli/transcripts/*.json carry final_metrics token
totals and agent model names. No account quota exists locally — we show
totals for sessions modified today, not exact daily burn or a fabricated percentage.

live(): real daily/weekly quota via the same Connect-RPC the CLI's /usage
command calls — SeatManagementService/GetUserStatus on server.codeium.com,
authenticated with the windsurf_api_key in credentials.toml.
"""

import json

import time
import tomllib

from _common import (HOME, LiveError, curl_json, fmt_ago, fmt_tokens, fmt_wait,
                     live_failure, live_fresh, live_success, local_day, safe_mtime)


def collect() -> dict:
    transcripts = HOME / ".local" / "share" / "devin" / "cli" / "transcripts"
    if not transcripts.is_dir():
        return {"name": "devin", "rows": [], "note": "not installed"}
    now = time.time()
    _, midnight = local_day(now)
    files = sorted(transcripts.glob("*.json"),
                   key=safe_mtime, reverse=True)
    if not files:
        return {"name": "devin", "rows": [], "note": "—"}
    toks, sess, model = 0, 0, ""
    for f in files:
        try:
            mtime = f.stat().st_mtime
            if mtime < midnight:
                break
            if mtime > now:
                continue
            d = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sess += 1
        fm = d.get("final_metrics") or {}
        toks += (fm.get("total_prompt_tokens") or 0) \
            + (fm.get("total_completion_tokens") or 0)
        model = model or (d.get("agent") or {}).get("model_name") or ""
    if sess:
        # Transcript totals are cumulative across resumed sessions. Mtime is
        # activity evidence, not a timestamp for each token: never persist as daily burn.
        return {"name": "devin", "note": "session totals · modified today", "rows": [
            {"label": "today", "text": f"{sess} sess · {fmt_tokens(toks)} tok", "tok": toks, "sess": sess},
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
    if live_fresh(cached_live):
        return cached_live
    cred = HOME / ".local" / "share" / "devin" / "credentials.toml"
    try:
        tok = tomllib.loads(cred.read_text()).get("windsurf_api_key")
    except (OSError, tomllib.TOMLDecodeError):
        return live_failure(cached_live, "credentials unavailable")
    if not isinstance(tok, str) or not tok:
        return live_failure(cached_live, "credentials unavailable")
    body = json.dumps({"metadata": {
        "apiKey": tok, "ideName": "devin_cli", "ideVersion": "1.0",
        "extensionName": "devin", "extensionVersion": "0.0.0"}})
    try:
        data = curl_json(
            "https://server.codeium.com/exa.seat_management_pb.SeatManagementService/GetUserStatus",
            headers=["Content-Type: application/json", "connect-protocol-version: 1"],
            body=body)
    except LiveError as e:
        return live_failure(cached_live, str(e))
    status = data.get("userStatus") or {}
    plan = status.get("planStatus") if isinstance(status, dict) else None
    if not isinstance(plan, dict) or not plan:
        return live_failure(cached_live, "usage unavailable")
    rows = []
    for rem_key, reset_key, label in (
            ("dailyQuotaRemainingPercent", "dailyQuotaResetAtUnix", "day"),
            ("weeklyQuotaRemainingPercent", "weeklyQuotaResetAtUnix", "wk")):
        rem = plan.get(rem_key)
        # proto3 JSON omits zero-valued fields: a present reset timestamp with an
        # absent remaining-percent means the quota is exhausted (0% left =
        # 100% used) — exactly the state that must surface, not be skipped.
        if rem is None and plan.get(reset_key):
            rem = 0.0
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
    return live_success(rows) if rows else live_failure(cached_live, "usage unavailable")
